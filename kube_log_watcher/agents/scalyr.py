"""
Scalyr watcher agent for providing config file and variables required to ship logs to Scalyr.
"""
import binascii
import json
import logging
import os
import shutil

from kube_log_watcher.agents.base import BaseWatcher
from kube_log_watcher.template_loader import load_template

TPL_NAME = 'scalyr.json.jinja2'

SCALYR_CONFIG_PATH = '/etc/scalyr-agent-2/agent.json'

# If exists! we expect serialized json str: '[{"container": "my-container", "parser": "my-custom-parser"}]'
SCALYR_ANNOTATION_PARSER = 'kubernetes-log-watcher/scalyr-parser'
# If exists! we expect serialized json str:
# '[{"container": "my-container", "sampling-rules":[{ "match_expression": "<expression here>",
#  "sampling_rate": "0" }]}]'
SCALYR_ANNOTATION_SAMPLING_RULES = 'kubernetes-log-watcher/scalyr-sampling-rules'
# '[{"container": "my-container", "redaction-rules":[{ "match_expression": "<expression here>" }]}]'
SCALYR_ANNOTATION_REDACTION_RULES = 'kubernetes-log-watcher/scalyr-redaction-rules'
JWT_REDACTION_RULE = {
    "match_expression": "eyJ[a-zA-Z0-9/+_=-]{5,}\\.eyJ[a-zA-Z0-9/+_=-]{5,}\\.[a-zA-Z0-9/+_=-]{5,}",
    "replacement": "+++JWT_TOKEN_REDACTED+++"
}
SCALYR_DEFAULT_PARSER = 'json'
SCALYR_DEFAULT_WRITE_RATE = 10000
SCALYR_DEFAULT_WRITE_BURST = 200000

logger = logging.getLogger('kube_log_watcher')


def container_annotation(annotations, container_name, pod_name, annotation_key, result_key, default=None):
    if annotations and annotation_key in annotations:
        try:
            result_candidates = json.loads(annotations[annotation_key])
            if type(result_candidates) is not list:
                logger.warning(
                    ('Scalyr watcher agent found invalid {} annotation in pod: {}. '
                     'Expected `list` found: `{}`').format(
                         annotation_key, pod_name, type(result_candidates)))
            else:
                for candidate in result_candidates:
                    if candidate.get('container') == container_name:
                        return candidate.get(result_key, default)
        except Exception:
            logger.error('Scalyr watcher agent failed to load annotation {}'.format(annotation_key))
    return default


def get_parser(annotations, kwargs):
    return container_annotation(annotations=annotations,
                                container_name=kwargs['container_name'],
                                pod_name=kwargs['pod_name'],
                                annotation_key=SCALYR_ANNOTATION_PARSER,
                                result_key='parser',
                                default=SCALYR_DEFAULT_PARSER)


def get_sampling_rules(annotations, kwargs):
    return container_annotation(annotations=annotations,
                                container_name=kwargs['container_name'],
                                pod_name=kwargs['pod_name'],
                                annotation_key=SCALYR_ANNOTATION_SAMPLING_RULES,
                                result_key='sampling-rules',
                                default=None)


def get_redaction_rules(annotations, kwargs):
    rules = container_annotation(annotations=annotations,
                                 container_name=kwargs['container_name'],
                                 pod_name=kwargs['pod_name'],
                                 annotation_key=SCALYR_ANNOTATION_REDACTION_RULES,
                                 result_key='redaction-rules',
                                 default=[])
    if type(rules) is not list:
        logger.warning(
            ('Scalyr watcher agent found invalid redaction rule annotation in pod/container: {}/{}. '
             'Expected `list` found: `{}`').format(
                 kwargs['pod_name'], kwargs['container_name'], type(rules)))
        rules = []
    rules.append(JWT_REDACTION_RULE)
    return rules


class ScalyrAgent(BaseWatcher):
    def __init__(self, configuration):
        cluster_id = configuration['cluster_id']
        self.scalyr_sampling_rules = self.parse_scalyr_sampling_rules(
            configuration.get('scalyr_sampling_rules') or [],
        )
        self.api_key = os.environ.get('WATCHER_SCALYR_API_KEY')
        self.dest_path = os.environ.get('WATCHER_SCALYR_DEST_PATH')
        self.scalyr_server = os.environ.get('WATCHER_SCALYR_SERVER')
        self.parse_lines_json = os.environ.get('WATCHER_SCALYR_PARSE_LINES_JSON', '').lower() == 'true'
        self.enable_profiling = os.environ.get('WATCHER_SCALYR_ENABLE_PROFILING', '').lower() == 'true'
        cluster_alias = os.environ.get('CLUSTER_ALIAS', 'none')
        cluster_environment = os.environ.get('CLUSTER_ENVIRONMENT', 'production')
        node_name = os.environ.get('CLUSTER_NODE_NAME', 'unknown')

        if not all([self.api_key, self.dest_path]):
            raise RuntimeError('Scalyr watcher agent initialization failed. Env variables WATCHER_SCALYR_API_KEY and '
                               'WATCHER_SCALYR_DEST_PATH must be set.')

        self.config_path = os.environ.get('WATCHER_SCALYR_CONFIG_PATH', SCALYR_CONFIG_PATH)
        if not os.path.exists(os.path.dirname(self.config_path)):
            raise RuntimeError(
                'Scalyr watcher agent initialization failed. {} config path does not exist.'.format(
                    self.config_path))

        if not os.path.exists(self.dest_path):
            raise RuntimeError(
                'Scalyr watcher agent initialization failed. {} destination path does not exist.'.format(
                    self.dest_path))
        else:
            watched_containers = os.listdir(self.dest_path)
            logger.info('Scalyr watcher agent found {} watched containers.'.format(len(watched_containers)))
            logger.debug('Scalyr watcher agent found the following watched containers: {}'.format(watched_containers))

        self.journald = None
        journald_monitor = os.environ.get('WATCHER_SCALYR_JOURNALD', False)

        if journald_monitor:
            attributes_str = os.environ.get('WATCHER_SCALYR_JOURNALD_ATTRIBUTES', '{}')
            extra_fields_str = os.environ.get('WATCHER_SCALYR_JOURNALD_EXTRA_FIELDS', '{}')
            self.journald = {
                'journal_path': os.environ.get('WATCHER_SCALYR_JOURNALD_PATH'),
                'attributes': json.loads(attributes_str),
                'extra_fields': json.loads(extra_fields_str),
                'write_rate': int(os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_RATE', SCALYR_DEFAULT_WRITE_RATE)),
                'write_burst': int(os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_BURST', SCALYR_DEFAULT_WRITE_BURST)),
            }

        self.server_attributes = {
            'serverHost': cluster_id,
            'cluster': cluster_id,
            'cluster_environment': cluster_environment,
            'cluster_alias': cluster_alias,
            'environment': cluster_environment,
            'node': node_name,
            'parser': SCALYR_DEFAULT_PARSER
        }

        self.tpl = load_template(TPL_NAME)
        self.logs = []
        self.kwargs = {}
        self._first_run = True

        logger.info('Scalyr watcher agent initialization complete!')

    def parse_scalyr_sampling_rules(self, scalyr_sampling_rules):
        parsed_scalyr_sampling_rules = []

        for scalyr_sampling_rule in scalyr_sampling_rules:
            try:
                if ('probability' in scalyr_sampling_rule) and not (0 <= scalyr_sampling_rule['probability'] <= 1):
                    raise ValueError('`probability` must be between 0 and 1')

                json.loads(scalyr_sampling_rule['value'])
            except (TypeError, KeyError, ValueError) as error:
                logger.warning('Cannot parse rule `{}`: {}'.format(scalyr_sampling_rule, repr(error)))
            else:
                parsed_scalyr_sampling_rules.append(scalyr_sampling_rule)

        return parsed_scalyr_sampling_rules

    @property
    def name(self):
        return 'Scalyr'

    @property
    def first_run(self):
        return self._first_run

    def get_scalyr_sampling_rule(self, container_data):
        for scalyr_sampling_rule in self.scalyr_sampling_rules:
            if (
                ('application' in scalyr_sampling_rule)
                and (scalyr_sampling_rule['application'] != container_data['application'])
            ):
                continue

            if (
                ('component' in scalyr_sampling_rule)
                and (scalyr_sampling_rule['component'] != container_data['component'])
            ):
                continue

            if 'probability' in scalyr_sampling_rule:
                container_crc = binascii.crc32(container_data['container_id'].encode())
                if ((container_crc % 100) + 1) > scalyr_sampling_rule['probability'] * 100:
                    continue

            return scalyr_sampling_rule['value']

    def add_log_target(self, target: dict):
        """
        Create our log targets, and pick relevant log fields from ``target['kwargs']``
        """
        log_path = self._adjust_target_log_path(target)
        if not log_path:
            logger.error('Scalyr watcher agent skipped log config for container({}) in pod {}.'.format(
                target['kwargs']['container_name'], target['kwargs']['pod_name']))
            return

        kwargs = target['kwargs']
        annotations = kwargs.get('pod_annotations', {})

        attributes = {
            'application': kwargs['application'],
            'component': kwargs['component'],
            'environment': kwargs['environment'],
            'version': kwargs['version'],
            'release': kwargs['release'],
            'pod': kwargs['pod_name'],
            'namespace': kwargs['namespace'],
            'container': kwargs['container_name'],
            'container_id': kwargs['container_id'],
            'parser': get_parser(annotations, kwargs)
        }

        # Keep only attributes that has value not duplicated in server_attributes
        attributes = {
            k: v
            for k, v in attributes.items()
            if v and (self.server_attributes.get(k) != v)
        }

        sampling_rules = self.get_scalyr_sampling_rule(kwargs)
        if sampling_rules is not None:
            logger.warning('Overwriting container {} ({}/{}) sampling annotation'.format(
                kwargs['container_id'],
                kwargs['application'],
                kwargs['component'],
            ))
            annotations[SCALYR_ANNOTATION_SAMPLING_RULES] = sampling_rules

        log = {
            'path': log_path,
            'sampling_rules': get_sampling_rules(annotations, kwargs),
            'redaction_rules': get_redaction_rules(annotations, kwargs),
            'attributes': attributes,
        }

        self.logs.append(log)

    def remove_log_target(self, container_id: str):
        container_dir = os.path.join(self.dest_path, container_id)

        try:
            shutil.rmtree(container_dir)
        except Exception:
            logger.exception('Scalyr watcher agent failed to remove container directory {}'.format(container_dir))

    def flush(self):
        kwargs = {
            'scalyr_key': self.api_key,
            'server_attributes': self.server_attributes,
            'logs': self.logs,
            'monitor_journald': self.journald,
            'scalyr_server': self.scalyr_server,
            'parse_lines_json': self.parse_lines_json,
            'enable_profiling': self.enable_profiling,
        }

        current_paths = self._get_current_log_paths()
        new_paths = {log['path'] for log in self.logs}

        diff_paths = new_paths.symmetric_difference(current_paths)

        if self._first_run or diff_paths:
            logger.debug('Scalyr watcher agent new paths: {}'.format(diff_paths))
            logger.debug('Scalyr watcher agent current paths: {}'.format(current_paths))
            try:
                config = self.tpl.render(**kwargs)

                with open(self.config_path, 'w') as fp:
                    fp.write(config)
            except Exception:
                logger.exception('Scalyr watcher agent failed to write config file.')
            else:
                self._first_run = False
                logger.info('Scalyr watcher agent updated config file {} with {} log targets.'.format(
                    self.config_path, len(diff_paths)))

    def reset(self):
        self.logs = []
        self.kwargs = {}

    def _adjust_target_log_path(self, target):
        try:
            src_log_path = target['kwargs'].get('log_file_path')
            application = target['kwargs'].get('application')
            version = target['kwargs'].get('version') or 'none'
            container_id = target['id']

            if not os.path.exists(src_log_path):
                return None

            dst_name = '{}-{}.log'.format(application, version)
            parent = os.path.join(self.dest_path, container_id)
            dst_log_path = os.path.join(parent, dst_name)

            if not os.path.exists(parent):
                os.makedirs(parent)

            # symlink to have our own friendly log file name!
            if not os.path.exists(dst_log_path):
                os.symlink(src_log_path, dst_log_path)

            return dst_log_path
        except Exception:
            logger.exception('Scalyr watcher agent Failed to adjust log path.')
            return None

    def _get_current_log_paths(self) -> list:
        targets = set()

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path) as fp:
                    config = json.load(fp)
                    targets = {log.get('path') for log in config.get('logs', [])}
                    logger.debug('Scalyr watcher agent loaded existing config {}: {} log targets exist!'.format(
                        self.config_path, len(config.get('logs', []))))
            else:
                logger.warning('Scalyr watcher agent cannot find config file!')
        except Exception:
            logger.exception('Scalyr watcher agent failed to read config!')

        return targets

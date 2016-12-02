"""
Scalyr watcher agent for providing config file and variables required to ship logs to Scalyr.
"""
import os
import shutil
import logging
import json

from k8s_log_watcher.agents.base import BaseWatcher


TPL_NAME = 'scalyr.json.jinja2'

SCALYR_CONFIG_PATH = '/etc/scalyr-agent-2/agent.json'

logger = logging.getLogger('k8s_log_watcher')


class ScalyrAgent(BaseWatcher):
    def __init__(self, cluster_id: str, load_template):
        self.api_key = os.environ.get('WATCHER_SCALYR_API_KEY')
        self.dest_path = os.environ.get('WATCHER_SCALYR_DEST_PATH')

        if not all([self.api_key, self.dest_path]):
            raise RuntimeError('Scalyr watcher agent initialization failed. Env variables WATCHER_SCALYR_API_KEY and '
                               'WATCHER_SCALYR_DEST_PATH must be set.')

        self.scalyr_config_path = os.environ.get('WATCHER_SCALYR_CONFIG_PATH', SCALYR_CONFIG_PATH)
        if not os.path.exists(os.path.dirname(self.scalyr_config_path)):
            raise RuntimeError(
                'Scalyr watcher agent initialization failed. {} config path does not exist.'.format(
                    self.scalyr_config_path))

        self.cluster_id = cluster_id
        self.tpl = load_template(TPL_NAME)
        self.logs = []
        self.kwargs = {}
        self._first_run = True

    @property
    def name(self):
        return 'Scalyr'

    def add_log_target(self, target: dict):
        """
        Create our log targets, and pick relevant log fields from ``target['kwargs']``
        """
        log_path = self._adjust_target_log_path(target)
        if not log_path:
            logger.error('Scalyr watcher agent skipped log config for container({}) in pod {}.'.format(
                target['kwargs']['container_name'], target['kwargs']['pod_name']))
            return

        log = {
            'path': log_path,
            'attributes': {
                'application': target['kwargs']['application_id'],
                'version': target['kwargs']['application_version'],
                'cluster': target['kwargs']['cluster_id'],
                'release': target['kwargs']['release'],
                'pod': target['kwargs']['pod_name'],
                'namespace': target['kwargs']['namespace'],
                'container': target['kwargs']['container_name'],
                'node': target['kwargs']['node_name'],
            }
        }

        self.logs.append(log)

    def remove_log_target(self, container_id: str):
        container_dir = os.path.join(self.dest_path, container_id)

        try:
            shutil.rmtree(container_dir)
        except:
            logger.exception('Scalyr watcher agent failed to remove container directory {}'.format(container_dir))

    def flush(self):
        kwargs = {
            'scalyr_key': self.api_key,
            'cluster_id': self.cluster_id,
            'logs': self.logs,
        }

        current_paths = self._get_current_log_paths()
        new_paths = {log['path'] for log in self.logs}

        if self._first_run or new_paths.symmetric_difference(current_paths):
            try:
                config = self.tpl.render(**kwargs)

                with open(self.scalyr_config_path, 'w') as fp:
                    fp.write(config)
            except:
                logger.exception('Scalyr watcher agent failed to write config file.')
            else:
                self._first_run = False
                logger.info('Scalyr watcher agent updated config file {}'.format(self.scalyr_config_path))

    def reset(self):
        self.logs = []
        self.kwargs = {}

    def _adjust_target_log_path(self, container_info):
        try:
            src_log_path = container_info['kwargs'].get('log_file_path')
            application = container_info['kwargs'].get('application_id')
            version = container_info['kwargs'].get('application_version')
            container_id = container_info['id']

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
        except:
            logger.exception('Scalyr watcher agent Failed to adjust log path.')
            return None

    def _get_current_log_paths(self) -> list:
        targets = set()

        try:
            with open(self.scalyr_config_path) as fp:
                config = json.load(fp)
                targets = {log.get('path') for log in config.get('logs', [])}
        except:
            pass

        return targets

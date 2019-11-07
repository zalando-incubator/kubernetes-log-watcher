import argparse
import json
import logging
import os
import sys
import time
import yaml

from typing import Tuple

import kube_log_watcher.kube as kube

from kube_log_watcher.agents import ScalyrAgent, AppDynamicsAgent, Symlinker


CONTAINERS_PATH = '/mnt/containers/'
DEST_PATH = '/mnt/jobs/'

APP_LABEL = 'application'
COMPONENT_LABEL = 'component'
ENVIRONMENT_LABEL = 'environment'
VERSION_LABEL = 'version'

ANNOTATION_PREFIX = 'annotation.'
KUBERNETES_PREFIX = 'io.kubernetes.'

BUILTIN_AGENTS = {
    'appdynamics': AppDynamicsAgent,
    'scalyr': ScalyrAgent,
    'symlinker': Symlinker,
}

# Set via kubernetes downward API.
CLUSTER_NODE_NAME = os.environ.get('CLUSTER_NODE_NAME')
CLUSTER_ENVIRONMENT = os.environ.get('CLUSTER_ENVIRONMENT', 'production')

logger = logging.getLogger('kube_log_watcher')
logger.addHandler(logging.StreamHandler(stream=sys.stdout))
logger.setLevel(os.environ.get('LOGLEVEL', 'INFO').upper())


def get_container_label_value(config, label) -> str:
    """
    Get label value from container config. Usually those labels are namespaced in the form:
        io.kubernetes.container.name
        io.kubernetes.pod.name
    """
    labels = config['Config']['Labels']
    for l, val in labels.items():
        if l.endswith(label):
            return val

    return None


def get_containers(containers_path: str) -> list:
    """
    Return list of container configs found on mounted ``containers_path``. Container config is loaded from
    ``config.v2.json`` file.

    :param containers_path: Containers dir path. Typically this is ``/var/lib/docker/containers`` mounted from host.
    :type containers_path: str

    :return: List of container configs.
    :rtype: list

    Example:
    {
        'id': 'container-123',
        'config': {'Config': {'Labels':{'io.kubernetes.pod.name': 'pod1'}}, 'State': {'Running': true}},
        'log_file': '/containers/conatiner-123/container-123-json.log'
    }
    """
    containers = []

    for container_path, _, files in os.walk(containers_path):

        container_id = os.path.basename(container_path)
        log_file_name = '{}-json.log'.format(container_id)

        config = {}
        source_log_file = ''

        for f in files:
            try:
                if f == 'config.v2.json':
                    with open(os.path.join(container_path, f)) as fp:
                        config = json.load(fp)
                elif f == log_file_name:
                    # Assuming same path is mounted on node *logging agent* container.
                    source_log_file = os.path.join(container_path, log_file_name)
            except Exception:
                logger.exception('Failed while retrieving config for container({})'.format(container_id))
                break

        if source_log_file and config:
            # All is good and ready!
            containers.append({
                'id': container_id,
                'config': config,
                'log_file': source_log_file
            })

            logger.debug('Successfully collected config for container({}): {}'.format(container_id, config))

    logger.info('Collected configs for {} containers'.format(len(containers)))

    return containers


def get_container_image_parts(config: dict) -> Tuple[str]:
    docker_image_parts = config['Image'].split('/')[-1].split(':')

    image = docker_image_parts[0]
    image_version = docker_image_parts[-1] if len(docker_image_parts) > 1 else 'latest'

    return image, image_version


def sync_containers_log_agents(
        agents: list, watched_containers: list, containers: list, containers_path: str, cluster_id: str,
        kube_url=None, strict_labels=None) -> list:
    """
    Sync containers log configs using supplied agents.

    :param agents: List of agents context managers.
    :type agents: list

    :param watched_containers: List of currently watched containers.
    :type watched_containers: list

    :param containers: List of container configs dicts.
    :type containers: list

    :param containers_path: Path to mounted containers directory.
    :type containers_path: str

    :param cluster_id: Kubernetes cluster ID. If not set, then it will not be added to job/config files.
    :type cluster_id: str

    :param kube_url: URL to Kube API proxy.
    :type kube_url: str

    :param strict_labels: List of labels pods need to posses in order to be followed.
    :type strict_labels: List

    :return: Existing container IDs and stale container IDs.
    :rtype: tuple
    """
    containers_log_targets = get_new_containers_log_targets(containers, containers_path, cluster_id, kube_url=kube_url,
                                                            strict_labels=strict_labels)

    existing_container_ids = {c['id'] for c in containers_log_targets}
    stale_container_ids = get_stale_containers(watched_containers, existing_container_ids)

    for agent in agents:
        try:
            with agent:
                for target in containers_log_targets:
                    agent.add_log_target(target)

                for container_id in stale_container_ids:
                    agent.remove_log_target(container_id)
        except Exception:
            logger.exception('Failed to sync log config with agent {}'.format(agent.name))

    # 4. return new containers, stale containers
    return existing_container_ids, stale_container_ids


def get_new_containers_log_targets(
        containers: list, containers_path: str, cluster_id: str, kube_url=None, strict_labels=None) -> list:
    """
    Return list of container log targets. A ``target`` includes:
        {
            "id": <container_id>,
            "kwargs": <template_kwargs>,
            "pod_labels": <container's pod labels>
        }

    :param containers: List of container configs dicts.
    :type containers: list

    :param containers_path: Path to mounted containers directory.
    :type containers_path: str

    :param cluster_id: kubernetes cluster ID. If not set, then it will not be added to job/config files.
    :type cluster_id: str

    :param kube_url: URL to Kube API proxy.
    :type kube_url: str

    :param strict_labels: List of labels pods need to posses in order to be followed.
    :type strict_labels: List

    :return: List of existing container log targets.
    :rtype: list
    """
    containers_log_targets = []
    strict_labels = strict_labels or []

    for container in containers:
        try:
            config = container['config']

            if kube.is_pause_container(config['Config']):
                # We have no interest in Pause containers.
                continue

            pod_name = get_container_label_value(config, 'pod.name')
            container_name = get_container_label_value(config, 'container.name')
            pod_namespace = get_container_label_value(config, 'pod.namespace')

            try:
                pod = kube.get_pod(pod_name, namespace=pod_namespace, kube_url=kube_url)
            except kube.PodNotFound:
                logger.warning('Cannot find pod "{}" ... skipping container: {}'.format(pod_name, container_name))
                continue

            metadata = pod.obj['metadata']
            pod_labels, pod_annotations = metadata.get('labels', {}), metadata.get('annotations', {})

            kwargs = {}

            kwargs['container_id'] = container['id']
            kwargs['container_path'] = os.path.join(containers_path, container['id'])
            kwargs['log_file_name'] = os.path.basename(container['log_file'])
            kwargs['log_file_path'] = container['log_file']

            kwargs['image'], kwargs['image_version'] = get_container_image_parts(config['Config'])

            kwargs['application'] = pod_labels.get(APP_LABEL)
            kwargs['component'] = pod_labels.get(COMPONENT_LABEL)
            kwargs['environment'] = pod_labels.get(ENVIRONMENT_LABEL, CLUSTER_ENVIRONMENT)
            kwargs['version'] = pod_labels.get(VERSION_LABEL, '')
            kwargs['release'] = pod_labels.get('release', '')
            kwargs['cluster_id'] = cluster_id
            kwargs['pod_name'] = pod_name
            kwargs['namespace'] = pod_namespace
            kwargs['container_name'] = container_name
            kwargs['node_name'] = CLUSTER_NODE_NAME
            kwargs['pod_annotations'] = pod_annotations

            if set(strict_labels) - set(pod_labels.keys()):
                logger.warning(
                    ('Labels "{}" are required for container({}: {}) in pod({}) '
                     '... Skipping!').format(','.join(strict_labels), container_name, container['id'], pod_name))
                continue
            if not kwargs['application']:
                logger.warning('Cannot determine application for pod: {}. Falling back to pod name!'.format(
                    pod_name))
                kwargs['application'] = kwargs['pod_name']

            containers_log_targets.append({'id': container['id'], 'kwargs': kwargs, 'pod_labels': pod_labels})
        except Exception:
            logger.exception('Failed to create log target for container({})'.format(container['id']))

    return containers_log_targets


def get_stale_containers(watched_containers: set, existing_container_ids: list) -> int:
    return set(watched_containers) - set(existing_container_ids)


def load_agents(agents, configuration):
    return [BUILTIN_AGENTS[agent.strip(' ')](configuration) for agent in agents]


def load_watcher_config(watcher_config_file):
    if watcher_config_file:
        try:
            with open(watcher_config_file) as f:
                return yaml.safe_load(f)
        except Exception as error:
            logger.warning('Cannot read `{}` watcher configuration file: {}'.format(watcher_config_file, repr(error)))

    return {}


def watch(containers_path, agents_list, cluster_id, interval=60, kube_url=None,
          strict_labels=None, watcher_config_file=None):
    """Watch new containers and sync their corresponding log job/config files."""
    # TODO: Check if filesystem watcher is *better* solution than polling.
    watched_containers = set()
    watcher_config = load_watcher_config(watcher_config_file)

    configuration = dict(watcher_config, cluster_id=cluster_id)
    agents = load_agents(agents_list, configuration)

    while True:
        try:
            new_watcher_config = load_watcher_config(watcher_config_file)
            if watcher_config != new_watcher_config:
                logger.info('Reloading agents with new configuration')
                watcher_config = new_watcher_config
                configuration = dict(watcher_config, cluster_id=cluster_id)
                agents = load_agents(agents_list, configuration)

            containers = get_containers(containers_path)

            # Write new job files!
            existing_container_ids, stale_container_ids = sync_containers_log_agents(
                agents, watched_containers.copy(), containers, containers_path, cluster_id, kube_url=kube_url,
                strict_labels=strict_labels)

            watched_containers.update(existing_container_ids)
            watched_containers.intersection_update(existing_container_ids)  # remove old containers!

            logger.info('Removed {} stale containers'.format(len(stale_container_ids)))
            logger.info('Watching {} containers'.format(len(watched_containers)))

            time.sleep(interval)
        except KeyboardInterrupt:
            return
        except Exception:
            logger.exception('Failed in watch! Retrying in {} seconds ...'.format(interval / 2))
            time.sleep(interval / 2)


def main():
    argp = argparse.ArgumentParser(description='kubernetes containers log watcher.')
    argp.add_argument('-c', '--containers-path', dest='containers_path', default=CONTAINERS_PATH,
                      help='Containers directory path mounted from the host. Can be set via WATCHER_CONTAINERS_PATH '
                      'env variable.')

    argp.add_argument('-a', '--agents', dest='agents',
                      help=('Comma separated string of required log processor agents. '
                            'Current supported agents are {}. Can be set via WATCHER_AGENTS env '
                            'variable.').format(list(BUILTIN_AGENTS)))

    argp.add_argument('-i', '--cluster-id', dest='cluster_id',
                      help='Cluster ID. Can be set via WATCHER_CLUSTER_ID env variable.')

    argp.add_argument('-u', '--kube-url', dest='kube_url',
                      help='URL to API proxy service. Service is expected to handle authentication to the Kubernetes '
                      'cluster. If set, then log-watcher will not use serviceaccount config. Can be set via '
                      'WATCHER_KUBE_URL env variable.')

    argp.add_argument('--strict-labels', dest='strict_labels', default='',
                      help='Only follow containers in pods that are labeled with these labels. Takes a comma separated '
                           ' list of label names. Can be set via WATCHER_STRICT_LABELS env variable.')

    argp.add_argument('--updated-certificates', dest='update_certificates', action='store_true', default=False,
                      help='[DEPRECATED] Call update-ca-certificates for Kubernetes service account ca.crt. '
                           'Can be set via WATCHER_KUBERNETES_UPDATE_CERTIFICATES env variable.')

    # TODO: Load required agent dynamically? break hard dependency on builtins!
    # argp.add_argument('-e', '--extra-agent', dest='extra_agent_path', default=None,
    #                   help='Import path of agent module providing job/config Jinja2 template path and required extra '
    #                        'vars from pod labels.')

    argp.add_argument('--interval', dest='interval', default=60, type=int,
                      help='Sleep interval for the watcher. Can be set via WATCHER_INTERVAL env variable.')

    argp.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='Verbose output. Can be set via WATCHER_DEBUG env variable.')

    args = argp.parse_args()

    if args.verbose or os.environ.get('WATCHER_DEBUG'):
        logger.setLevel(logging.DEBUG)

    containers_path = os.environ.get('WATCHER_CONTAINERS_PATH', args.containers_path)
    cluster_id = os.environ.get('WATCHER_CLUSTER_ID', args.cluster_id)
    agents_str = os.environ.get('WATCHER_AGENTS', args.agents)
    strict_labels_str = os.environ.get('WATCHER_STRICT_LABELS', args.strict_labels)

    strict_labels = strict_labels_str.split(',') if strict_labels_str else []

    update_certificates = os.environ.get('WATCHER_KUBERNETES_UPDATE_CERTIFICATES', args.update_certificates)
    if update_certificates:
        kube.update_ca_certificate()

    if not agents_str:
        logger.error(('No log proccesing agents specified, please specify at least one log processing agent from {}. '
                      'Terminating watcher!').format(list(BUILTIN_AGENTS)))
        sys.exit(1)

    agents = set(agents_str.lower().strip(' ').strip(',').split(','))

    diff = agents - set(BUILTIN_AGENTS)
    if diff:
        logger.error(('Unsupported agent supplied: {}. '
                      'Current supported log processing agents are {}. '
                      'Terminating watcher!').format(diff, BUILTIN_AGENTS))
        sys.exit(1)

    kube_url = os.environ.get('WATCHER_KUBE_URL', args.kube_url)

    interval = os.environ.get('WATCHER_INTERVAL', args.interval)

    watcher_config_file = os.environ.get('WATCHER_CONFIG')

    logger.info('Loaded configuration:')
    logger.info('\tContainers path: {}'.format(containers_path))
    logger.info('\tAgents: {}'.format(agents))
    logger.info('\tKube url: {}'.format(kube_url))
    logger.info('\tInterval: {}'.format(interval))
    logger.info('\tStrict labels: {}'.format(strict_labels_str))
    logger.info('\tWatcher configuration file: {}'.format(watcher_config_file))

    watch(
        containers_path,
        agents,
        cluster_id,
        interval=interval,
        kube_url=kube_url,
        strict_labels=strict_labels,
        watcher_config_file=watcher_config_file,
    )

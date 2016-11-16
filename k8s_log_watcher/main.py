import argparse
import time
import os
import logging
import json

from jinja2 import Environment, FileSystemLoader

import k8s_log_watcher.kube as kube
import k8s_log_watcher.agents.appdynamics as appdynamics


CONTAINERS_PATH = '/mnt/containers/'
DEST_PATH = '/mnt/jobs/'

APPLICATION_ID_KEY = 'APPLICATION_ID'
APPLICATION_VERSION_KEY = 'APPLICATION_VERSION'


logger = logging.getLogger(__name__)
logger.handlers = [logging.StreamHandler()]

# Job file template.
# TODO: Adjust to be dynamically set from agent-plugin!
template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
env = Environment(loader=FileSystemLoader(template_path))

TPL_JOBFILE = env.get_template('appdynamics.job.jinja2')

# Set via K8S downward API.
CLUSTER_NODE_NAME = os.environ.get('CLUSTER_NODE_NAME')


def get_job_file_path(dest_path, container_id) -> str:
    return os.path.join(dest_path, 'container-{}-jobfile.job'.format(container_id))


def get_label_value(config, label) -> str:
    """
    Get label value from container config. Usually those labels are namespaced in the form:
        io.kubernetes.container.name
        io.kubernetes.pod.name
    """
    labels = config['Config']['Labels']
    for l, val in labels.items():
        if l.endswith(label):
            return labels[l]

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
            except:
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


def sync_containers_job_files(containers, containers_path, dest_path, kube_url=None, first_run=False) -> list:
    """
    Create containers log job/config files for log proccessing agent.

    :param containers: List of container configs dicts.
    :type containers: list

    :param containers_path: Path to mounted containers directory.
    :type containers_path: str

    :param dest_path: Log job/config files directory path.
    :type dest_path: str

    :param kube_url: URL to Kube API proxy.
    :type kube_url: str

    :param first_run: If ``True``, then all existing job/config files will be overridden.
    :type first_run: bool

    :return: List of existing container IDs.
    :rtype: list
    """
    pods = kube.get_pods(kube_url=kube_url)

    existing_containers = []

    for container in containers:
        try:
            config = container['config']

            if kube.is_pause_container(config['Config']):
                # We have no interest in Pause containers.
                logger.debug('Skipping pause container({})'.format(container['id']))
                continue

            pod_name = get_label_value(config, 'pod.name')
            container_name = get_label_value(config, 'container.name')
            pod_labels = kube.get_pod_labels(pods, pod_name)

            kwargs = {}

            kwargs['container_path'] = os.path.join(containers_path, container['id'])
            kwargs['log_file_name'] = os.path.basename(container['log_file'])

            kwargs['app_id'] = pod_labels.get('app')
            kwargs['app_version'] = pod_labels.get('version')
            kwargs['pod_name'] = pod_name
            kwargs['container_name'] = container_name
            kwargs['node_name'] = CLUSTER_NODE_NAME

            if not all([kwargs['app_id'], kwargs['app_version']]):
                logger.warning(
                    ('Labels "app" and "version" are required for container({}: {}) in pod({})'
                     ' ... Skipping!').format(container_name, container['id'], pod_name))
                continue

            # Get extra vars specific to log proccessing agent.
            extras = appdynamics.get_template_vars(pod_name, pod_labels)

            kwargs.update(extras)

            job = TPL_JOBFILE.render(**kwargs)

            job_file = get_job_file_path(dest_path, container['id'])

            # Override file if watcher is restarted.
            # This could happen if the watcher is updated (i.e. new job template/fixes) while old job files exist.
            if not os.path.exists(job_file) or first_run:
                with open(job_file, 'w') as fp:
                    fp.write(job)

            existing_containers.append(container['id'])
        except:
            logger.exception('Failed to create job/config file for container({})'.format(container['id']))

    return existing_containers


def remove_containers_job_files(containers, dest_path):
    """
    Remove containers job/log files for all terminated containers.

    :param containers: List of container IDs.
    :type containers: list

    :param dest_path: Log job/config files directory.
    :type dest_path: str
    """
    for container in containers:
        job_file = get_job_file_path(dest_path, container)

        try:
            os.remove(job_file)
            logger.debug('Removed container({}) job file'.format(container))
        except:
            logger.exception('Failed to remove job file: {}'.format(job_file))


def watch(containers_path, dest_path, interval=60, kube_url=None):
    """Watch new containers and sync their corresponding log job/config files."""
    # TODO: Check if filesystem watcher is *better* solution than polling.
    watched_containers = set()
    first_run = True

    while True:
        try:
            containers = get_containers(containers_path)

            # Write new job files!
            existing_containers = sync_containers_job_files(containers, containers_path, dest_path, kube_url=kube_url,
                                                            first_run=first_run)

            removed_containers = watched_containers - set(existing_containers)
            remove_containers_job_files(removed_containers, dest_path)

            watched_containers.update(existing_containers)
            watched_containers.intersection_update(existing_containers)  # remove old containers!

            logger.info('Watching {} containers'.format(len(watched_containers)))

            time.sleep(interval)
            first_run = False
        except KeyboardInterrupt:
            return
        except:
            logger.exception('Failed in watch! Retrying in {} seconds ...'.format(interval / 2))
            time.sleep(interval / 2)


def main():
    argp = argparse.ArgumentParser(description='K8S containers log watcher.')
    argp.add_argument('-c', '--containers-path', dest='containers_path', default=CONTAINERS_PATH,
                      help='Containers directory path mounted from the host.')

    argp.add_argument('-d', '--dest', dest='dest_path', default=DEST_PATH,
                      help='Destination path for log agent job/config files.')

    argp.add_argument('-u', '--kube-url', dest='kube_url',
                      help='URL to API proxy service. Service is expected to handle authentication to the K8S cluster.'
                      'If set, then log-watcher will not use serviceaccount config.')

    # TODO: Load required agent dynamically? break hard dependency on appdynamics!
    # argp.add_argument('-a', '--agent-module', dest='agent_module_path', default=None,
    #                   help='Import path of agent module providing job/config Jinja2 template path and required extra '
    #                        'vars from pod labels.')

    argp.add_argument('-i', '--interval', dest='interval', default=60, type=int, help='Sleep interval for the watcher.')

    argp.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False, help='Verbose output.')

    args = argp.parse_args()

    if args.verbose or os.environ.get('WATCHER_DEBUG'):
        logger.setLevel(logging.DEBUG)

    containers_path = os.environ.get('WATCHER_CONTAINERS_PATH', args.containers_path)
    dest_path = os.environ.get('WATCHER_DEST_PATH', args.dest_path)

    kube_url = os.environ.get('WATCHER_KUBE_URL', args.kube_url)

    interval = os.environ.get('WATCHER_INTERVAL', args.interval)

    logger.info('Loaded configuration:')
    logger.info('\tContainers path: {}'.format(containers_path))
    logger.info('\tDest path: {}'.format(dest_path))
    logger.info('\tKube url: {}'.format(kube_url))
    logger.info('\tInterval: {}'.format(interval))

    watch(containers_path, dest_path, interval=interval, kube_url=kube_url)


if __name__ == '__main__':
    main()

"""
Appdynamics watcher agent for providing job file templates and variables required to ship logs to
appdynamics controller.
"""
import os
import logging

from kube_log_watcher.agents.base import BaseWatcher
from kube_log_watcher.template_loader import load_template

TPL_NAME = 'appdynamics.job.jinja2'

logger = logging.getLogger('kube_log_watcher')


class AppDynamicsAgent(BaseWatcher):
    def __init__(self, configuration):
        self.dest_path = os.environ.get('WATCHER_APPDYNAMICS_DEST_PATH')

        if not self.dest_path:
            raise RuntimeError('AppDyanmics watcher agent initialization failed. Env variable '
                               'WATCHER_APPDYNAMICS_DEST_PATH must be set.')

        self.cluster_id = configuration['cluster_id']
        self.tpl = load_template(TPL_NAME)

        self.logs = {}
        self._first_run = True

        logger.info('AppDynamics watcher agent initialization complete!')

    @property
    def name(self):
        return 'AppDynamics'

    @property
    def first_run(self):
        return self._first_run

    def add_log_target(self, target: dict):
        """
        Update our log targets, and pick relevant log fields from ``target['kwargs']``
        """
        log = {}
        log['kwargs'] = target['kwargs']
        pod_labels = target['pod_labels']
        container_id = target['id']

        log['kwargs']['app_name'] = pod_labels.get('appdynamics_app')
        log['kwargs']['app_tier'] = pod_labels.get('appdynamics_tier')

        log['job_file_path'] = self._get_job_file_path(container_id)

        self.logs[target['id']] = log

    def remove_log_target(self, container_id):
        job_file = self._get_job_file_path(container_id)

        try:
            del self.logs[container_id]
        except KeyError:
            logger.exception('Failed to remove log target: %s', container_id)

        try:
            os.remove(job_file)
            logger.debug('AppDynamics watcher agent Removed container(%s) job file', container_id)
        except OSError:
            logger.exception('AppDynamics watcher agent Failed to remove job file: %s', job_file)

    def flush(self):
        for log in self.logs.values():
            job_file = log['job_file_path']
            if not os.path.exists(job_file) or self._first_run:
                try:
                    job = self.tpl.render(**log['kwargs'])

                    with open(job_file, 'w') as fp:
                        fp.write(job)

                except Exception:
                    logger.exception('AppDynamics watcher agent failed to write job file %s', job_file)
                else:
                    logger.debug('AppDynamics watcher agent updated job file %s', job_file)

        self._first_run = False

    def _get_job_file_path(self, container_id):
        return os.path.join(self.dest_path, 'container-{}-jobfile.job'.format(container_id))

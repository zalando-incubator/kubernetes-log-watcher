"""
Agent that creates symlinks to logfiles and embeds metadata in the
file/directory name of the Symlink.  Can be used in conjunction with a
log shipping agent (e.g. Fluentd) that watches the directory structure
containing the symlinks. Since all metadata is embedded in the
filename, there is no need to dynamically generate configuration for
the log shipping agent.
"""

import logging
import os
import pathlib
import re
import shutil

from kube_log_watcher.agents.base import BaseWatcher

logger = logging.getLogger(__name__)


def sanitize(s):
    return re.sub('[^a-zA-Z0-9_-]', '_', s)


class Symlinker(BaseWatcher):
    def __init__(self, configuration):
        symlink_dir = os.environ.get('WATCHER_SYMLINK_DIR', configuration.get('symlink_dir'))
        if not symlink_dir:
            raise RuntimeError(
                'Symlinker watcher agent initialization failed. Env variable WATCHER_SYMLINK_DIR must be set')
        self.symlink_dir = pathlib.Path(symlink_dir)
        if not self.symlink_dir.is_dir():
            raise RuntimeError(
                'Symlinker watcher agent initialization failed. Symlink base directory {} does not exist'
                .format(self.symlink_dir))
        logger.info('Symlinker watcher agent initialized')

    @property
    def name(self):
        return 'Symlinker'

    def add_log_target(self, target):
        logger.debug('Symlinker: add_log_target for %s called', target['id'])
        kw = target['kwargs']
        top_dir = self.symlink_dir / sanitize(kw['container_id'])
        link_dir = top_dir \
            / sanitize(kw['application'] or 'none') \
            / sanitize(kw['component'] or kw['application'] or 'none') \
            / sanitize(kw['namespace']) \
            / sanitize(kw['environment']) \
            / sanitize(kw['version'] or 'none') \
            / sanitize(kw['container_name'])
        link = (link_dir / sanitize(kw['pod_name'])).with_suffix('.log')

        if top_dir.exists():
            if link.is_symlink and link.samefile(kw['log_file_path']):
                logger.debug('Symlinker: link already exists for %s. Nothing to be done.', target['id'])
                return
            logger.info('Symlinker: metadata has changed for %s. Creating new symlink.', target['id'])
            shutil.rmtree(str(top_dir))
            logger.debug('Symlinker: Removed directory %s', top_dir)

        link_dir.mkdir(parents=True)
        link.symlink_to(kw['log_file_path'])
        logger.debug('Symlinker: Created symlink %s -> %s', link, kw['log_file_path'])

    def remove_log_target(self, container_id):
        logger.debug('Symlinker: remove_log_target for %s called', container_id)
        link_dir = str(self.symlink_dir / sanitize(container_id))
        try:
            shutil.rmtree(link_dir)
            logger.debug('Symlinker: Removed directory %s', link_dir)
        except Exception:
            logger.warning('%s watcher agent failed to remove link directory %s', self.name, link_dir)

    def flush(self):
        for container_dir in pathlib.Path(self.symlink_dir).iterdir():
            link = next(pathlib.Path(container_dir).glob('**/*.log'))
            if link and link.exists():
                continue
            else:
                shutil.rmtree(str(container_dir))

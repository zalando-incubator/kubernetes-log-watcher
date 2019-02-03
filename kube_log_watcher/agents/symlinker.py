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
import shutil

from kube_log_watcher.agents.base import BaseWatcher

logger = logging.getLogger('kube_log_watcher')


class Symlinker(BaseWatcher):
    def __init__(self, symlink_dir: str):
        self.symlink_dir = pathlib.Path(symlink_dir)

    @property
    def name(self):
        return 'Symlinker'

    def add_log_target(self, target):
        kw = target['kwargs']
        top_dir = self.symlink_dir / kw['container_id']
        link_dir = top_dir \
            / kw['application_id'] \
            / kw['component'] \
            / kw['namespace'] \
            / kw['environment'] \
            / kw['application_version'] \
            / kw['container_name']
        link = link_dir / 'pod-1.log'

        if top_dir.exists():
            shutil.rmtree(str(top_dir))

        link_dir.mkdir(parents=True)
        link.symlink_to(kw['log_file_path'])

    def remove_log_target(self, target):
        link_dir = str(self.symlink_dir / target['kwargs']['container_id'])
        try:
            shutil.rmtree(link_dir)
        except Exception:
            logger.exception('{} watcher agent failed to remove link directory {}'.format(self.name, link_dir))

    def flush(self):
        pass


class SymlinkerLoader(Symlinker):
    def __new__(cls, _cluster_id, _load_template):
        symlink_dir = os.environ.get('WATCHER_SYMLINK_DIR')
        if not symlink_dir:
            raise RuntimeError(
                'Symlinker watcher agent initialization failed. Env variable WATCHER_SYMLINK_DIR must be set')
        return Symlinker(symlink_dir)

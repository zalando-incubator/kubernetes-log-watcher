"""
Agent that creates symlinks to logfiles and embeds metadata in the
file/directory name of the Symlink.  Can be used in conjunction with a
log shipping agent (e.g. Fluentd) that watches the directory structure
containing the symlinks. Since all metadata is embedded in the
filename, there is no need to dynamically generate configuration for
the log shipping agent.
"""

import pathlib

from kube_log_watcher.agents.base import BaseWatcher


class Symlinker(BaseWatcher):
    def __init__(self, symlink_dir: str):
        self.symlink_dir = pathlib.Path(symlink_dir)

    @property
    def name(self):
        return 'Symlinker'

    def add_log_target(self, target):
        kw = target['kwargs']
        link_dir = self.symlink_dir \
            / kw['container_id'] \
            / kw['application_id'] \
            / kw['component'] \
            / kw['namespace'] \
            / kw['environment'] \
            / kw['application_version'] \
            / kw['container_name']
        link = link_dir / 'pod-1.log'
        link_dir.mkdir(parents=True)
        link.symlink_to(kw['log_file_path'])

    def remove_log_target(self, target):
        pass

    def flush(self):
        pass

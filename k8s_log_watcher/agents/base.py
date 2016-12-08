"""
Base watcher agent.
"""


class BaseWatcher:
    """
    BaseWatcher implementing a contextmanager.
    """

    def __init__(self, cluster_id: str, load_template):
        pass

    @property
    def name(self):
        raise NotImplementedError()

    @property
    def first_run(self):
        return True

    def __enter__(self):
        self.reset()

    def __exit__(self, *exc):
        self.flush()
        self.reset()

    def reset(self):
        return

    def add_log_target(self, target: dict):
        raise NotImplementedError()

    def remove_log_target(self, container_id: str):
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()

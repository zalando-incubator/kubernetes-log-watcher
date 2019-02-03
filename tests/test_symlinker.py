from kube_log_watcher.agents.symlinker import Symlinker


def test_symlinker_name():
    agent = Symlinker('.')
    assert agent.name == 'Symlinker'


def test_add_log_target(tmp_path):
    container_dir = tmp_path / 'containers' / 'container-1'
    container_log = container_dir / 'container-1-json.log'
    target = {
        'id': 'container-1',
        'kwargs': {
            'application_id': 'app-1',
            'environment': 'test',
            'application_version': 'v1',
            'component': 'comp',
            'cluster_id': 'kube-cluster',
            'release': '2016',
            'pod_name': 'pod-1',
            'namespace': 'default',
            'container_name': 'app-1-container-1',
            'node_name': 'node-1',
            'log_file_path': str(container_log),
            'container_id': 'container-1',
            'container_path': str(container_dir),
            'log_file_name': 'container-1-json.log',
            'pod_annotations': {}
        },
        'pod_labels': {}
    }

    container_dir.mkdir(parents=True)
    container_log.write_text('foo')

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.add_log_target(target)

    link = symlink_dir / 'container-1' / 'app-1' / 'comp' / 'default' \
        / 'test' / 'v1' / 'app-1-container-1' / 'pod-1.log'

    assert link.is_symlink()
    assert link.samefile(target['kwargs']['log_file_path'])
    assert link.read_text() == 'foo'


def test_remove_log_target(tmp_path):
    container_dir = tmp_path / 'containers' / 'container-1'
    container_log = container_dir / 'container-1-json.log'
    target = {
        'id': 'container-1',
        'kwargs': {
            'application_id': 'app-1',
            'environment': 'test',
            'application_version': 'v1',
            'component': 'comp',
            'cluster_id': 'kube-cluster',
            'release': '2016',
            'pod_name': 'pod-1',
            'namespace': 'default',
            'container_name': 'app-1-container-1',
            'node_name': 'node-1',
            'log_file_path': str(container_log),
            'container_id': 'container-1',
            'container_path': str(container_dir),
            'log_file_name': 'container-1-json.log',
            'pod_annotations': {}
        },
        'pod_labels': {}
    }

    container_dir.mkdir(parents=True)

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.add_log_target(target)

    with agent:
        agent.remove_log_target(target)

    assert not (symlink_dir / 'container-1').exists()

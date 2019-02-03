from kube_log_watcher.agents.symlinker import Symlinker


def helper_target(tmp_path):
    container_dir = tmp_path / 'containers' / 'container-1'
    container_log = container_dir / 'container-1-json.log'
    target = {
        'id': 'container-1',
        'kwargs': {
            'application_id': 'app/with/slashes',
            'environment': 'test',
            'application_version': 'v1.5',
            'component': 'comp with spaces',
            'cluster_id': 'kube-cluster',
            'release': '2016',
            'pod_name': 'pod-123',
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

    return target


def test_symlinker_name():
    agent = Symlinker('.')
    assert agent.name == 'Symlinker'


def test_add_log_target(tmp_path):
    target = helper_target(tmp_path)

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.add_log_target(target)

    link = symlink_dir / 'container-1' / 'app_with_slashes' / 'comp_with_spaces' \
        / 'default' / 'test' / 'v1_5' / 'app-1-container-1' / 'pod-123.log'

    assert link.is_symlink()
    assert link.samefile(target['kwargs']['log_file_path'])
    assert link.read_text() == 'foo'


def test_remove_log_target(tmp_path):
    target = helper_target(tmp_path)

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.add_log_target(target)

    with agent:
        agent.remove_log_target(target)

    assert not (symlink_dir / 'container-1').exists()


def test_remove_log_target_that_doesnt_exist(tmp_path):
    target = helper_target(tmp_path)

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.remove_log_target(target)

    assert not (symlink_dir / 'container-1').exists()


def test_add_log_target_twice(tmp_path):
    target = helper_target(tmp_path)

    symlink_dir = tmp_path / "links"
    symlink_dir.mkdir()

    agent = Symlinker(str(symlink_dir))

    with agent:
        agent.add_log_target(target)
        agent.add_log_target(target)

    link = symlink_dir / 'container-1' / 'app_with_slashes' / 'comp_with_spaces' \
        / 'default' / 'test' / 'v1_5' / 'app-1-container-1' / 'pod-123.log'

    assert link.is_symlink()
    assert link.samefile(target['kwargs']['log_file_path'])
    assert link.read_text() == 'foo'

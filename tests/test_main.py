import os

import pytest

from mock import MagicMock, call

from kube_log_watcher.kube import PodNotFound
from kube_log_watcher.main import (
    get_container_label_value, get_containers, sync_containers_log_agents, load_agents,
    get_new_containers_log_targets, get_container_image_parts, watch)

from .conftest import CLUSTER_ID


CONFIG = {
    'Config': {
        'Labels': {
            'io.kubernetes.pod.name': 'pod-name',
            'io.kubernetes.pod.namespace': 'default',
            'io.kubernetes.container.name': 'container-1',
        }
    }
}

CONTAINERS_PATH = '/mnt/containers/'
DEST_PATH = '/mnt/jobs/'


def pod_mock(metadata):
    pod = MagicMock()
    pod.obj = metadata

    return pod


@pytest.mark.parametrize('image, res', (
    ('repo/image-1:0.1', ('image-1', '0.1')),
    ('', ('', 'latest')),
    ('image-1:0.1', ('image-1', '0.1')),
    ('repo/image-1:0.1:0.2:0.3', ('image-1', '0.3')),
    ('repo/:0.1', ('', '0.1')),
    ('repo/image-1', ('image-1', 'latest')),
    ('repo/', ('', 'latest')),
    ('repo/vendor/project/image-1:0.1-alpha-1', ('image-1', '0.1-alpha-1')),
))
def test_get_container_image_parts(monkeypatch, image, res):
    config = {'Image': image}

    assert get_container_image_parts(config) == res


@pytest.mark.parametrize(
    'label,val',
    (
        ('pod.name', 'pod-name'),
        ('pod.namespace', 'default'),
        ('io.kubernetes.container.name', 'container-1'),
        ('container.nam', None),
    )
)
def test_get_container_label_value(monkeypatch, label, val):
    assert val == get_container_label_value(CONFIG, label)


@pytest.mark.parametrize(
    'walk,config,res,exc',
    (
        (
            [('/mnt/containers/cont-1', '', ['config.v2.json', 'cont-1-json.log'])],
            {'Config': ''},
            [{'id': 'cont-1', 'config': {'Config': ''}, 'log_file': '/mnt/containers/cont-1/cont-1-json.log'}],
            None,
        ),
        (
            [('/mnt/containers/cont-1', '', ['config.v2.json'])],
            {'Config': ''},
            [],
            None,
        ),
        (
            [('/mnt/containers/cont-1', '', ['cont-1-json.log'])],
            {'Config': ''},
            [],
            None
        ),
        (
            [('/mnt/containers/cont-1', '', ['config.v2.json', 'cont-1-json.log'])],
            {'Config': ''},
            [],
            OSError,
        ),
    )
)
def test_get_containers(monkeypatch, walk, config, res, exc):
    mock_open = MagicMock()

    mock_walk = MagicMock(return_value=walk)

    mock_load = MagicMock()
    if exc:
        mock_load.side_effect = exc
    else:
        mock_load.return_value = config

    monkeypatch.setattr('builtins.open', mock_open)
    monkeypatch.setattr('os.walk', mock_walk)
    monkeypatch.setattr('json.load', mock_load)

    containers = get_containers(CONTAINERS_PATH)

    assert containers == res

    mock_walk.assert_called_with(CONTAINERS_PATH)
    if 'config.v2.json' in walk[0][-1][0]:
        mock_open.assert_called_with(os.path.join(walk[0][0], 'config.v2.json'))
        mock_load.assert_called()


@pytest.mark.parametrize(
    'watched_containers',
    (
        set(),
        {'cont-5'},
        {'cont-6'},  # stale
    )
)
def test_sync_containers_log_agents(monkeypatch, watched_containers, fx_containers_sync):
    containers, pods, targets, _, result = fx_containers_sync

    get_pod = MagicMock(side_effect=pods)

    monkeypatch.setattr('kube_log_watcher.kube.get_pod', get_pod)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    stale_containers = watched_containers - result
    if watched_containers:
        result = result - watched_containers
        targets = [t for t in targets if t['id'] not in watched_containers]

    get_targets = MagicMock(return_value=targets)
    monkeypatch.setattr('kube_log_watcher.main.get_new_containers_log_targets', get_targets)

    agent1 = MagicMock()
    agent2 = MagicMock()
    agents = [agent1, agent2]

    existing, stale = sync_containers_log_agents(agents, watched_containers, containers, CONTAINERS_PATH, CLUSTER_ID,
                                                 strict_labels=[])

    get_targets.assert_called_with([c for c in containers if c['id'] not in watched_containers],
                                   CONTAINERS_PATH, CLUSTER_ID, kube_url=None, strict_labels=[])
    assert existing == result
    assert stale == stale_containers

    add_calls = [call(target) for target in targets]

    agent1.add_log_target.assert_has_calls(add_calls, any_order=True)
    agent2.add_log_target.assert_has_calls(add_calls, any_order=True)

    if stale_containers:
        remove_calls = [call(c) for c in stale_containers]
        agent1.remove_log_target.assert_has_calls(remove_calls, any_order=True)
        agent2.remove_log_target.assert_has_calls(remove_calls, any_order=True)


@pytest.mark.parametrize(
    'watched_containers',
    (
        set(),
        {'cont-5'},
        {'cont-6'},  # stale
    )
)
def test_sync_containers_log_agents_failure(monkeypatch, watched_containers, fx_containers_sync):
    containers, pods, targets, _, result = fx_containers_sync

    get_pod = MagicMock(side_effect=pods)

    monkeypatch.setattr('kube_log_watcher.kube.get_pod', get_pod)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    stale_containers = watched_containers - result
    if watched_containers:
        result = result - watched_containers
        targets = [t for t in targets if t['id'] not in watched_containers]

    get_targets = MagicMock(return_value=targets)
    monkeypatch.setattr('kube_log_watcher.main.get_new_containers_log_targets', get_targets)

    agent1 = MagicMock()
    agent2 = MagicMock()
    agent1.add_log_target.side_effect, agent2.add_log_target.side_effect = Exception, RuntimeError
    agents = [agent1, agent2]

    existing, stale = sync_containers_log_agents(agents, watched_containers, containers, CONTAINERS_PATH, CLUSTER_ID)

    assert existing == result
    assert stale == stale_containers


def test_get_new_containers_log_targets(monkeypatch, fx_containers_sync):
    containers, pods, result, _, _ = fx_containers_sync

    get_pod = MagicMock(side_effect=[pod_mock(p) for p in pods])

    monkeypatch.setattr('kube_log_watcher.kube.get_pod', get_pod)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID,
                                             strict_labels=['application', 'version'])

    assert targets == result


def test_get_new_containers_log_targets_not_found_pods(monkeypatch, fx_containers_sync):
    containers, pods, _, _, _ = fx_containers_sync

    get_pod = MagicMock(side_effect=PodNotFound)

    monkeypatch.setattr('kube_log_watcher.kube.get_pod', get_pod)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID,
                                             strict_labels=['application', 'version'])

    assert targets == []


def test_get_new_containers_log_targets_failure(monkeypatch, fx_containers_sync):
    containers, pods, _, _, _ = fx_containers_sync

    is_pause = MagicMock(side_effect=Exception)

    # Force exception
    monkeypatch.setattr('kube_log_watcher.kube.is_pause_container', is_pause)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID,
                                             strict_labels=['application', 'version'])

    assert targets == []


def test_get_new_containers_log_targets_no_strict_labels(monkeypatch, fx_containers_sync):
    containers, pods, result_labels, result_no_labels, _ = fx_containers_sync

    result = result_labels + result_no_labels

    get_pod = MagicMock(side_effect=[pod_mock(p) for p in pods])

    monkeypatch.setattr('kube_log_watcher.kube.get_pod', get_pod)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID)

    assert sorted(targets, key=lambda k: k['id']) == sorted(result, key=lambda k: k['id'])


def test_load_agents(monkeypatch):
    agent1 = MagicMock()
    agent2 = MagicMock()

    builtins = {
        'agent1': agent1,
        'agent2': agent2,
    }
    monkeypatch.setattr('kube_log_watcher.main.BUILTIN_AGENTS', builtins)

    load_agents(['agent1', 'agent2'], {
        'cluster_id': CLUSTER_ID,
    })

    agent1.assert_called_with({
        'cluster_id': CLUSTER_ID,
    })


@pytest.mark.parametrize('strict', (['application', 'version'], []))
def test_watch(monkeypatch, strict):
    containers = [
        [{'id': 'cont-1'}, {'id': 'cont-2'}, {'id': 'cont-3'}],
        [{'id': 'cont-1'}, {'id': 'cont-2'}],
        [{'id': 'cont-1'}, {'id': 'cont-2'}],
    ]

    new_ids = [
        {'cont-1', 'cont-2', 'cont-3'},
        set(),
        set(),
    ]

    stale_ids = [
        set(),
        {'cont-3', },
        set(),
    ]

    load_agents_mock = MagicMock(return_value=['agent-1', 'agent-2'])

    get_containers_mock = MagicMock(side_effect=containers)

    sync_containers_log_agents_mock = MagicMock(side_effect=list(zip(new_ids, stale_ids)))

    sleep = MagicMock(side_effect=(None, None, KeyboardInterrupt))  # terminate loop on third time
    monkeypatch.setattr('time.sleep', sleep)

    monkeypatch.setattr('kube_log_watcher.main.load_agents', load_agents_mock)
    monkeypatch.setattr('kube_log_watcher.main.get_containers', get_containers_mock)
    monkeypatch.setattr('kube_log_watcher.main.sync_containers_log_agents', sync_containers_log_agents_mock)

    watch(CONTAINERS_PATH, ['a-1', 'a-2'], CLUSTER_ID, strict_labels=strict)

    load_agents_mock.assert_called_with(['a-1', 'a-2'], {
        'cluster_id': CLUSTER_ID,
    })

    get_containers_mock.assert_called_with(CONTAINERS_PATH)

    calls = [
        call(['agent-1', 'agent-2'], set(), containers[0], CONTAINERS_PATH, CLUSTER_ID, kube_url=None,
             strict_labels=strict),
        call(['agent-1', 'agent-2'], set(['cont-1', 'cont-2', 'cont-3']), containers[1], CONTAINERS_PATH, CLUSTER_ID,
             kube_url=None, strict_labels=strict),
        call(['agent-1', 'agent-2'], set(['cont-1', 'cont-2']), containers[2], CONTAINERS_PATH, CLUSTER_ID,
             kube_url=None, strict_labels=strict),
    ]

    sync_containers_log_agents_mock.assert_has_calls(calls, any_order=True)


@pytest.mark.parametrize('strict', (['application, version'], []))
def test_watch_failure(monkeypatch, strict):
    sleep = MagicMock(return_value=None)
    monkeypatch.setattr('time.sleep', sleep)

    load_agents_mock = MagicMock(return_value=['agent-1', 'agent-2'])

    get_containers_mock = MagicMock(side_effect=[Exception, Exception, KeyboardInterrupt])

    monkeypatch.setattr('kube_log_watcher.main.load_agents', load_agents_mock)
    monkeypatch.setattr('kube_log_watcher.main.get_containers', get_containers_mock)

    interval = 60
    watch(CONTAINERS_PATH, ['a-1', 'a-2'], CLUSTER_ID, interval=interval, strict_labels=strict)

    load_agents_mock.assert_called_with(['a-1', 'a-2'], {
        'cluster_id': CLUSTER_ID,
    })

    get_containers_mock.assert_called_with(CONTAINERS_PATH)
    sleep.assert_called_with(interval / 2)


def test_load_configuration(monkeypatch, tmp_path):
    watcher_config_file = tmp_path / 'log-watcher.yaml'

    get_containers_mock = MagicMock(return_value=[])
    monkeypatch.setattr('kube_log_watcher.main.get_containers', get_containers_mock)

    load_agents_mock = MagicMock(return_value=[])
    monkeypatch.setattr('kube_log_watcher.main.load_agents', load_agents_mock)

    step = 0

    def sync_containers_log_agents(*args, **kwargs):
        nonlocal step

        if step in [0, 1]:
            watcher_config_file.write_text('')
        elif step in [2, 3]:
            watcher_config_file.write_text('{"foo":')
        elif step in [4, 5]:
            watcher_config_file.write_text('{"foo": "bar"}')
        elif step in [6, 7]:
            watcher_config_file.write_text('{"foo": "baz"}')
        else:
            raise KeyboardInterrupt

        step += 1
        return set(), set()

    monkeypatch.setattr('kube_log_watcher.main.sync_containers_log_agents', sync_containers_log_agents)
    watch(CONTAINERS_PATH, [], CLUSTER_ID, interval=0.001, watcher_config_file=str(watcher_config_file))

    assert load_agents_mock.call_count == 3

    load_agents_mock.assert_has_calls([
        call([], {'cluster_id': 'kube-cluster'}),
        call([], {'foo': 'bar', 'cluster_id': 'kube-cluster'}),
        call([], {'foo': 'baz', 'cluster_id': 'kube-cluster'}),
    ])

import os

import pytest

from mock import MagicMock, call

from kube_log_watcher.template_loader import load_template
from kube_log_watcher.main import (
    get_container_label_value, get_containers, sync_containers_log_agents, get_stale_containers, load_agents,
    get_new_containers_log_targets, get_container_image_parts, watch, get_pod_annotations_from_container,
    get_pod_labels_from_container)

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


def test_get_pod_labels_from_container():
    config = {
        'Config': {
            'Labels': {
                'io.kubernetes.pod.name': 'pod-1',
                'application': 'app-1',
                'job': 'job-app-1',
                'annotation.some-annotation/annotation-val': 'v1',
            }
        }
    }

    assert get_pod_labels_from_container(config) == {'application': 'app-1', 'job': 'job-app-1'}


def test_get_pod_annotations_from_container():
    config = {
        'Config': {
            'Labels': {
                'io.kubernetes.pod.name': 'pod-1',
                'application': 'app-1',
                'job': 'job-app-1',
                'annotation.some-annotation/annotation-val': 'v1',
            }
        }
    }

    assert get_pod_annotations_from_container(config) == {'some-annotation/annotation-val': 'v1'}


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
            Exception,
        ),
    )
)
def test_get_containers(monkeypatch, walk, config, res, exc):
    mock_open = MagicMock()

    mock_walk = MagicMock()
    mock_walk.return_value = walk

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
        {'cont-4'},  # stale
    )
)
def test_sync_containers_log_agents(monkeypatch, watched_containers, fx_containers_sync):
    containers, pods, targets, _, result = fx_containers_sync

    get_pods = MagicMock()
    get_pods.return_value = pods

    monkeypatch.setattr('kube_log_watcher.kube.get_pods', get_pods)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    stale_containers = watched_containers - result
    if watched_containers:
        result = result - watched_containers
        targets = [t for t in targets if t['id'] not in watched_containers]

    get_targets = MagicMock()
    get_targets.return_value = targets
    get_stale = MagicMock()
    get_stale.return_value = stale_containers
    monkeypatch.setattr('kube_log_watcher.main.get_new_containers_log_targets', get_targets)
    monkeypatch.setattr('kube_log_watcher.main.get_stale_containers', get_stale)

    agent1 = MagicMock()
    agent2 = MagicMock()
    agents = [agent1, agent2]

    existing, stale = sync_containers_log_agents(agents, watched_containers, containers, CONTAINERS_PATH, CLUSTER_ID)

    assert existing == result
    assert stale == stale_containers

    add_calls = [call(target) for target in targets]

    agent1.add_log_target.assert_has_calls(add_calls, any_order=True)
    agent2.add_log_target.assert_has_calls(add_calls, any_order=True)

    if stale_containers:
        remove_calls = [call(c) for c in stale_containers]
        agent1.remove_log_target.assert_has_calls(remove_calls, any_order=True)
        agent2.remove_log_target.assert_has_calls(remove_calls, any_order=True)


def test_get_new_containers_log_targets(monkeypatch, fx_containers_sync):
    containers, pods, result, _, _ = fx_containers_sync

    get_pods = MagicMock()
    get_pods.return_value = pods

    monkeypatch.setattr('kube_log_watcher.kube.get_pods', get_pods)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID, strict_labels=True)

    assert targets == result


def test_get_new_containers_log_targets_no_strict_labels(monkeypatch, fx_containers_sync):
    containers, pods, result_labels, result_no_labels, _ = fx_containers_sync

    result = result_labels + result_no_labels

    get_pods = MagicMock()
    get_pods.return_value = pods

    monkeypatch.setattr('kube_log_watcher.kube.get_pods', get_pods)
    monkeypatch.setattr('kube_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    targets = get_new_containers_log_targets(containers, CONTAINERS_PATH, CLUSTER_ID)

    assert sorted(targets, key=lambda k: k['id']) == sorted(result, key=lambda k: k['id'])


@pytest.mark.parametrize(
    'watched,existing,result',
    (
        ([1, 2, 3], [1, 2, 3], set()),
        ([1], [1, 2, 3], set()),
        ([4], [1, 2, 3], {4}),
    )
)
def test_get_stale_containers(watched, existing, result):
    assert get_stale_containers(watched, existing) == result


def test_load_agents(monkeypatch):
    agent1 = MagicMock()
    agent2 = MagicMock()

    builtins = {
        'agent1': agent1,
        'agent2': agent2,
    }
    monkeypatch.setattr('kube_log_watcher.main.BUILTIN_AGENTS', builtins)

    load_agents(['agent1', 'agent2'], CLUSTER_ID)

    agent1.assert_called_with(CLUSTER_ID, load_template)


@pytest.mark.parametrize('strict', (True, False))
def test_watch(monkeypatch, strict):
    containers = [
        [{'id': 'cont-1'}, {'id': 'cont-2'}, {'id': 'cont-3'}],
        [{'id': 'cont-1'}, {'id': 'cont-2'}],
        [{'id': 'cont-1'}, {'id': 'cont-2'}],
    ]

    existing_ids = [
        ('cont-1', 'cont-2', 'cont-3'),
        ('cont-1', 'cont-2'),
        ('cont-1', 'cont-2'),
    ]

    stale_ids = [
        set(),
        ('cont-3',),
        set(),
    ]

    load_agents_mock = MagicMock()
    load_agents_mock.return_value = ['agent-1', 'agent-2']

    get_containers_mock = MagicMock()
    get_containers_mock.side_effect = containers

    sync_containers_log_agents_mock = MagicMock()
    sync_containers_log_agents_mock.side_effect = list(zip(existing_ids, stale_ids))

    sleep = MagicMock()
    sleep.side_effect = (None, None, KeyboardInterrupt)  # terminate loop on third time
    monkeypatch.setattr('time.sleep', sleep)

    monkeypatch.setattr('kube_log_watcher.main.load_agents', load_agents_mock)
    monkeypatch.setattr('kube_log_watcher.main.get_containers', get_containers_mock)
    monkeypatch.setattr('kube_log_watcher.main.sync_containers_log_agents', sync_containers_log_agents_mock)

    watch(CONTAINERS_PATH, ['a-1', 'a-2'], CLUSTER_ID, strict_labels=strict)

    load_agents_mock.assert_called_with(['a-1', 'a-2'], CLUSTER_ID)

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


@pytest.mark.parametrize('strict', (True, False))
def test_watch_failure(monkeypatch, strict):
    sleep = MagicMock()
    sleep.return_value = None
    monkeypatch.setattr('time.sleep', sleep)

    load_agents_mock = MagicMock()
    load_agents_mock.return_value = ['agent-1', 'agent-2']

    get_containers_mock = MagicMock()
    get_containers_mock.side_effect = [Exception, Exception, KeyboardInterrupt]

    monkeypatch.setattr('kube_log_watcher.main.load_agents', load_agents_mock)
    monkeypatch.setattr('kube_log_watcher.main.get_containers', get_containers_mock)

    interval = 60
    watch(CONTAINERS_PATH, ['a-1', 'a-2'], CLUSTER_ID, interval=interval, strict_labels=strict)

    load_agents_mock.assert_called_with(['a-1', 'a-2'], CLUSTER_ID)

    get_containers_mock.assert_called_with(CONTAINERS_PATH)
    sleep.assert_called_with(interval / 2)

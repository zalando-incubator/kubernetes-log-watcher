import os

import pytest

from mock import MagicMock, call

from k8s_log_watcher.main import (get_label_value, get_containers, sync_containers_log_agents)

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


@pytest.mark.parametrize(
    'label,val',
    (
        ('pod.name', 'pod-name'),
        ('pod.namespace', 'default'),
        ('io.kubernetes.container.name', 'container-1'),
        ('container.nam', None),
    )
)
def test_get_label_value(monkeypatch, label, val):
    assert val == get_label_value(CONFIG, label)


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
    containers, pods, targets, result = fx_containers_sync

    get_pods = MagicMock()
    get_pods.return_value = pods

    monkeypatch.setattr('k8s_log_watcher.kube.get_pods', get_pods)
    monkeypatch.setattr('k8s_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    stale_containers = watched_containers - result
    if watched_containers:
        result = result - watched_containers
        targets = [t for t in targets if t['id'] not in watched_containers]

    get_targets = MagicMock()
    get_targets.return_value = targets
    get_stale = MagicMock()
    get_stale.return_value = stale_containers
    monkeypatch.setattr('k8s_log_watcher.main.get_new_containers_log_targets', get_targets)
    monkeypatch.setattr('k8s_log_watcher.main.get_stale_containers', get_stale)

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

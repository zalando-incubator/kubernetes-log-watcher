import os

import pytest

from mock import MagicMock, call

from k8s_log_watcher.main import (get_job_file_path, get_label_value, get_containers, remove_containers_job_files,
                                  sync_containers_job_files)
from k8s_log_watcher.main import TPL_JOBFILE


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


def test_get_jobfile_path(monkeypatch):
    dest_path = '/tmp/jobs'
    container_id = '123'

    job_file = get_job_file_path(dest_path, container_id)

    assert '/tmp/jobs/container-123-jobfile.job' == job_file


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


@pytest.mark.parametrize('exc', (False, True))
def test_remove_containers_job_files(monkeypatch, exc):
    containers = [1, 2, 3]
    res = 3

    remove = MagicMock()
    if exc:
        remove.side_effect = [None, None, Exception]
        res = 2
    monkeypatch.setattr('os.remove', remove)

    count = remove_containers_job_files(containers, DEST_PATH)

    assert count == res

    calls = [call(get_job_file_path(DEST_PATH, c)) for c in containers]
    remove.assert_has_calls(calls, any_order=True)


@pytest.mark.parametrize('job_exists,first_run', ((True, True), (True, False), (False, True), (False, False)))
def test_sync_containers_job_files(monkeypatch, fx_containers_sync, job_exists, first_run):
    containers, pods, kwargs, res = fx_containers_sync

    get_pods = MagicMock()
    get_pods.return_value = pods

    mock_open = MagicMock()
    mock_fp = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_fp

    exists = MagicMock()
    exists.return_value = job_exists

    monkeypatch.setattr('k8s_log_watcher.kube.get_pods', get_pods)
    monkeypatch.setattr('builtins.open', mock_open)
    monkeypatch.setattr('os.path.exists', exists)

    monkeypatch.setattr('k8s_log_watcher.main.CLUSTER_NODE_NAME', 'node-1')

    existing = sync_containers_job_files(containers, CONTAINERS_PATH, DEST_PATH, first_run=first_run, cluster_id='CL1')

    assert existing == res

    exists_calls = [call(get_job_file_path(DEST_PATH, c)) for c in res]
    exists.assert_has_calls(exists_calls, any_order=True)

    if first_run or not job_exists:
        open_calls = [call(get_job_file_path(DEST_PATH, c), 'w') for c in res]
        mock_open.assert_has_calls(open_calls, any_order=True)

        write_calls = [call(TPL_JOBFILE.render(k)) for k in kwargs]
        mock_fp.write.assert_has_calls(write_calls, any_order=True)

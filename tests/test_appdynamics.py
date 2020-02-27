import os

import pytest

from mock import MagicMock

from kube_log_watcher.agents.appdynamics import AppDynamicsAgent

from .conftest import CLUSTER_ID, APPDYNAMICS_DEST_PATH


@pytest.fixture
def appdynamics_env(monkeypatch):
    monkeypatch.setenv('WATCHER_APPDYNAMICS_DEST_PATH', APPDYNAMICS_DEST_PATH)


def assert_agent(agent):
    assert agent.name

    assert agent.dest_path == APPDYNAMICS_DEST_PATH
    assert agent.cluster_id == CLUSTER_ID


def patch_open(monkeypatch, exc=None):
    mock_open = MagicMock()
    mock_fp = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_fp

    if exc:
        mock_fp.side_effect = exc

    monkeypatch.setattr('builtins.open', mock_open)

    return mock_open, mock_fp


def test_add_log_target(monkeypatch, appdynamics_env, fx_appdynamics):
    target = fx_appdynamics['target']
    kwargs = fx_appdynamics['kwargs']

    agent = AppDynamicsAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    mock_open, mock_fp = patch_open(monkeypatch)

    with agent:
        agent.add_log_target(target)

    job_file = os.path.join(agent.dest_path, 'container-{}-jobfile.job'.format(target['id']))

    mock_open.assert_called_with(job_file, 'w')
    job = agent.tpl.render(**kwargs)
    mock_fp.write.assert_called_with(job)

    assert agent.first_run is False


@pytest.mark.parametrize('exc', (None, OSError))
def test_remove_log_target(monkeypatch, appdynamics_env, exc):
    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    remove = MagicMock()
    if exc:
        remove.side_effect = exc
    monkeypatch.setattr('os.remove', remove)

    agent = AppDynamicsAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    container_id = 'container-1'
    agent.remove_log_target(container_id)

    job_file = os.path.join(agent.dest_path, 'container-{}-jobfile.job'.format(container_id))
    remove.assert_called_with(job_file)

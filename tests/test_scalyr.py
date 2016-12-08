import os
import json

import pytest

from mock import MagicMock

from k8s_log_watcher.template_loader import load_template
from k8s_log_watcher.agents.scalyr import ScalyrAgent, SCALYR_CONFIG_PATH, TPL_NAME

from .conftest import CLUSTER_ID
from .conftest import SCALYR_KEY, SCALYR_DEST_PATH, SCALYR_JOURNALD_DEFAULTS


ENVS = (
    {
        'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
        'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
    },
    {
        'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
    },
    {
        'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
        'WATCHER_SCALYR_JOURNALD': 'true',
    },
)

KWARGS_KEYS = ('scalyr_key', 'cluster_id', 'logs', 'monitor_journald')


def assert_fx_sanity(kwargs):
    assert set(KWARGS_KEYS) == set(kwargs.keys())


def assert_agent(agent, env):
    assert agent.name

    assert agent.api_key == env.get('WATCHER_SCALYR_API_KEY')
    assert agent.dest_path == env.get('WATCHER_SCALYR_DEST_PATH')
    assert agent.config_path == env.get('WATCHER_SCALYR_CONFIG_PATH', SCALYR_CONFIG_PATH)

    journald = env.get('WATCHER_SCALYR_JOURNALD')
    assert agent.journald == (SCALYR_JOURNALD_DEFAULTS if journald else None)

    assert agent.cluster_id == CLUSTER_ID


def patch_env(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    if 'WATCHER_SCALYR_CONFIG_PATH' not in env:
        monkeypatch.delenv('WATCHER_SCALYR_CONFIG_PATH', raising=False)


def patch_os(monkeypatch):
    makedirs = MagicMock()
    symlink = MagicMock()

    monkeypatch.setattr('os.makedirs', makedirs)
    monkeypatch.setattr('os.symlink', symlink)

    return makedirs, symlink


def patch_open(monkeypatch, exc=None):
    mock_open = MagicMock()
    mock_fp = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_fp

    if exc:
        mock_fp.side_effect = exc

    monkeypatch.setattr('builtins.open', mock_open)

    return mock_open, mock_fp


@pytest.mark.parametrize('env', ENVS)
def test_add_log_target(monkeypatch, env, fx_scalyr):
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_JOURNALD_DEFAULTS

    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink = patch_os(monkeypatch)

    current_targets = MagicMock()
    current_targets.return_value = []
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    mock_open, mock_fp = patch_open(monkeypatch)

    with agent:
        agent.add_log_target(target)

    log_path = kwargs['logs'][0]['path']

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    mock_open.assert_called_with(agent.config_path, 'w')
    config = agent.tpl.render(**kwargs)
    mock_fp.write.assert_called_with(config)

    assert agent.first_run is False


@pytest.mark.parametrize('env', ENVS)
def test_add_log_target_no_src(monkeypatch, env, fx_scalyr):
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']

    exists = MagicMock()
    exists.side_effect = (True, False)
    monkeypatch.setattr('os.path.exists', exists)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    agent.add_log_target(target)

    assert agent.logs == []


@pytest.mark.parametrize('env', ENVS)
def test_add_log_target_no_change(monkeypatch, env, fx_scalyr):
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_JOURNALD_DEFAULTS

    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink = patch_os(monkeypatch)

    log_path = kwargs['logs'][0]['path']

    # targets did not change
    current_targets = MagicMock()
    current_targets.return_value = [log_path]
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    mock_open, mock_fp = patch_open(monkeypatch)

    # assuming not the first run
    agent._first_run = False

    with agent:
        agent.add_log_target(target)

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    mock_fp.write.assert_not_called()

    assert agent.first_run is False


@pytest.mark.parametrize('env', ENVS)
def test_flush_failure(monkeypatch, env, fx_scalyr):
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_JOURNALD_DEFAULTS

    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink = patch_os(monkeypatch)

    log_path = kwargs['logs'][0]['path']

    current_targets = MagicMock()
    current_targets.return_value = []
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    mock_open, mock_fp = patch_open(monkeypatch, Exception)

    with agent:
        agent.add_log_target(target)

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    assert agent.first_run is False


@pytest.mark.parametrize(
    'env,config,result',
    (
        (
            ENVS[0],
            {'scalyr_api_key': '123', 'logs': [{'path': '/p1'}, {'path': '/p2'}, {'path': '/p3'}]},
            {'/p1', '/p2', '/p3'}
        ),
        (
            ENVS[0],
            Exception,
            set()
        )
    )
)
def test_get_current_log_paths(monkeypatch, env, config, result):
    patch_env(monkeypatch, env)
    mock_open, mock_fp = patch_open(monkeypatch)

    load = MagicMock()
    load.return_value = config
    monkeypatch.setattr('json.load', load)

    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink = patch_os(monkeypatch)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    res = agent._get_current_log_paths()

    assert res == result

    mock_open.assert_called_with(os.path.join(agent.config_path))


@pytest.mark.parametrize(
    'env,exc',
    (
        (
            ENVS[0],
            None,
        ),
        (
            ENVS[0],
            Exception,
        )
    )
)
def test_remove_log_target(monkeypatch, env, exc):
    patch_env(monkeypatch, env)

    exists = MagicMock()
    exists.side_effect = (True, True, False, False)
    monkeypatch.setattr('os.path.exists', exists)

    rmtree = MagicMock()
    if exc:
        rmtree.side_effect = exc
    monkeypatch.setattr('shutil.rmtree', rmtree)

    agent = ScalyrAgent(CLUSTER_ID, load_template)

    assert_agent(agent, env)

    container_id = 'container-1'
    agent.remove_log_target(container_id)

    rmtree.assert_called_with(os.path.join(agent.dest_path, container_id))


@pytest.mark.parametrize(
    'kwargs,expected',
    (
        (
            {'scalyr_key': SCALYR_KEY, 'cluster_id': CLUSTER_ID, 'monitor_journald': 0, 'logs': []},
            {
                'api_key': 'scalyr-key-123',
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {'serverHost': 'kube-cluster'},
                'logs': [], 'monitors': []
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY, 'cluster_id': CLUSTER_ID, 'logs': [],
                'monitor_journald': {'journal_path': None, 'attributes': {}, 'extra_fields': {}},
            },
            {
                'api_key': 'scalyr-key-123',
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {'serverHost': 'kube-cluster'},
                'logs': [],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                    }
                ]
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY, 'cluster_id': CLUSTER_ID,
                'logs': [{'path': '/p1', 'attributes': {'a1': 'v1'}}],
                'monitor_journald': {
                    'journal_path': '/var/log/journal',
                    'attributes': {'cluster': CLUSTER_ID},
                    'extra_fields': {'_COMM': 'command'}
                },
            },
            {
                'api_key': 'scalyr-key-123',
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {'serverHost': 'kube-cluster'},
                'logs': [{'attributes': {'a1': 'v1', 'parser': 'json'}, 'path': '/p1'}],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                        'journal_path': '/var/log/journal',
                        'attributes': {'cluster': CLUSTER_ID},
                        'extra_fields': {'_COMM': 'command'}
                    }
                ]
            },
        ),
    )
)
def test_tpl_render(monkeypatch, kwargs, expected):
    tpl = load_template(TPL_NAME)

    config = tpl.render(**kwargs)

    assert json.loads(config) == expected

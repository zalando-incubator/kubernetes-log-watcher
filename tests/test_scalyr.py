import os
import json
import copy

import pytest

from mock import MagicMock
from urllib.parse import quote_plus

from kube_log_watcher.template_loader import load_template
from kube_log_watcher.agents.scalyr \
    import ScalyrAgent, SCALYR_CONFIG_PATH, TPL_NAME, JWT_REDACTION_RULE,\
    get_parser, get_sampling_rules, get_redaction_rules, container_annotation

from .conftest import CLUSTER_ID, NODE, APPLICATION_ID, APPLICATION_VERSION, COMPONENT
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
    {
        'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
        'WATCHER_SCALYR_JOURNALD': 'true', 'WATCHER_SCALYR_JOURNALD_WRITE_RATE': 1,
        'WATCHER_SCALYR_JOURNALD_WRITE_BURST': 2,
    },
)

KWARGS_KEYS = ('scalyr_key', 'parse_lines_json', 'cluster_id', 'logs', 'monitor_journald')


SCALYR_MONITOR_JOURNALD = copy.deepcopy(SCALYR_JOURNALD_DEFAULTS)
SCALYR_MONITOR_JOURNALD['attributes']['node'] = NODE


def assert_fx_sanity(kwargs):
    assert set(KWARGS_KEYS) == set(kwargs.keys())


def assert_agent(agent, env):
    assert agent.name

    assert agent.api_key == env.get('WATCHER_SCALYR_API_KEY')
    assert agent.dest_path == env.get('WATCHER_SCALYR_DEST_PATH')
    assert agent.config_path == env.get('WATCHER_SCALYR_CONFIG_PATH', SCALYR_CONFIG_PATH)

    journald = env.get('WATCHER_SCALYR_JOURNALD')
    journald_defaults = copy.deepcopy(SCALYR_JOURNALD_DEFAULTS)
    if env.get('WATCHER_SCALYR_JOURNALD_WRITE_RATE'):
        journald_defaults['write_rate'] = env.get('WATCHER_SCALYR_JOURNALD_WRITE_RATE')
    if env.get('WATCHER_SCALYR_JOURNALD_WRITE_BURST'):
        journald_defaults['write_burst'] = env.get('WATCHER_SCALYR_JOURNALD_WRITE_BURST')
    assert agent.journald == (journald_defaults if journald else None)

    assert agent.cluster_id == CLUSTER_ID


def patch_env(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    if 'WATCHER_SCALYR_CONFIG_PATH' not in env:
        monkeypatch.delenv('WATCHER_SCALYR_CONFIG_PATH', raising=False)


def patch_os(monkeypatch):
    makedirs = MagicMock()
    symlink = MagicMock()
    listdir = MagicMock()
    listdir.return_value = []

    monkeypatch.setattr('os.makedirs', makedirs)
    monkeypatch.setattr('os.symlink', symlink)
    monkeypatch.setattr('os.listdir', listdir)

    return makedirs, symlink, listdir


def patch_open(monkeypatch, exc=None):
    mock_open = MagicMock()
    mock_fp = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_fp

    if exc:
        mock_fp.side_effect = exc

    monkeypatch.setattr('builtins.open', mock_open)

    return mock_open, mock_fp


@pytest.mark.parametrize(
    'env,exists',
    (
        (
            {
                # No API KEY
                'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
                'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
            },
            (True, True)
        ),
        (
            {
                # No Dest path
                'WATCHER_SCALYR_API_KEY': SCALYR_KEY,
            },
            (True, True)
        ),
        (
            {
                'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
                'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
            },
            # Config path does not exist
            (False, True)
        ),
        (
            {
                'WATCHER_SCALYR_API_KEY': SCALYR_KEY, 'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
                'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
            },
            # Dest path does not exist
            (True, False)
        ),
    )
)
def test_initialization_failure(monkeypatch, env, exists):
    patch_env(monkeypatch, env)
    patch_os(monkeypatch)

    exists = MagicMock()
    exists.side_effect = exists
    monkeypatch.setattr('os.path.exists', exists)

    with pytest.raises(RuntimeError):
        ScalyrAgent(CLUSTER_ID, load_template)


@pytest.mark.parametrize('env', ENVS)
def test_add_log_target(monkeypatch, env, fx_scalyr):
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_MONITOR_JOURNALD

    exists = MagicMock()
    exists.side_effect = (True, True, True, False, False, True)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

    current_targets = MagicMock()
    current_targets.return_value = []
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent(CLUSTER_ID, load_template)
    assert_agent(agent, env)

    mock_open, mock_fp = patch_open(monkeypatch)

    with agent:
        agent.add_log_target(target)
        assert agent.logs[0]['attributes']['parser'] == kwargs['logs'][0]['attributes']['parser']

    log_path = kwargs['logs'][0]['path']

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    mock_open.assert_called_with(agent.config_path, 'w')
    mock_fp.write.assert_called_once()

    assert agent.first_run is False


@pytest.mark.parametrize('env', ENVS)
def test_add_log_target_no_src(monkeypatch, env, fx_scalyr):
    patch_os(monkeypatch)
    patch_env(monkeypatch, env)

    target = fx_scalyr['target']

    exists = MagicMock()
    exists.side_effect = (True, True, False)
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
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_MONITOR_JOURNALD

    exists = MagicMock()
    exists.side_effect = (True, True, True, False, False, True)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

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
    kwargs['monitor_journald'] = {} if not env.get('WATCHER_SCALYR_JOURNALD') else SCALYR_MONITOR_JOURNALD

    exists = MagicMock()
    exists.side_effect = (True, True, True, False, False, True)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

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
    exists.side_effect = (True, True, True, False, False, True)
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

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
    patch_os(monkeypatch)
    patch_env(monkeypatch, env)

    exists = MagicMock()
    exists.side_effect = (True, True, True, False, False, True)
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
            {
                'scalyr_key': SCALYR_KEY,
                'cluster_id': CLUSTER_ID,
                'cluster_environment': 'testing',
                'cluster_alias': 'cluster-alias',
                'monitor_journald': None,
                'logs': []
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 100000000,
                'max_existing_log_offset_size': 200000000,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {
                    'serverHost': 'kube-cluster',
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias'
                    },
                'logs': [], 'monitors': []
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'cluster_id': CLUSTER_ID,
                'cluster_environment': 'testing',
                'cluster_alias': 'cluster-alias',
                'logs': [],
                'monitor_journald': {
                    'journal_path': None, 'attributes': {}, 'extra_fields': {}, 'write_rate': 10000,
                    'write_burst': 200000
                },
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 100000000,
                'max_existing_log_offset_size': 200000000,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {
                    'serverHost': 'kube-cluster',
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias'
                },
                'logs': [],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                        'monitor_log_write_rate': 10000,
                        'monitor_log_max_write_burst': 200000,
                    }
                ]
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'cluster_id': CLUSTER_ID,
                'cluster_environment': 'testing',
                'cluster_alias': 'cluster-alias',
                'logs': [
                    {
                        'path': '/p1',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True
                    }
                ],
                'monitor_journald': {
                    'journal_path': '/var/log/journal',
                    'attributes': {'cluster': CLUSTER_ID, 'node': NODE},
                    'extra_fields': {'_COMM': 'command'},
                    'write_rate': 10000,
                    'write_burst': 200000,
                },
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 100000000,
                'max_existing_log_offset_size': 200000000,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {
                    'serverHost': 'kube-cluster',
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias'
                    },
                'logs': [
                    {
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=',
                        'copy_from_start': True
                    }
                ],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                        'monitor_log_write_rate': 10000,
                        'monitor_log_max_write_burst': 200000,
                        'journal_path': '/var/log/journal',
                        'attributes': {'cluster': CLUSTER_ID, 'node': NODE},
                        'extra_fields': {'_COMM': 'command'}
                    }
                ]
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'cluster_id': CLUSTER_ID,
                'cluster_environment': 'testing',
                'cluster_alias': 'cluster-alias',
                'monitor_journald': None,
                'logs': [
                    {
                        'path': '/p1',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True,
                        'sampling_rules': {"match_expression": "match-expression"}
                    }
                ]
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 100000000,
                'max_existing_log_offset_size': 200000000,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {
                    'serverHost': 'kube-cluster',
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias'},
                'monitors': [],
                'logs': [
                    {
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True,
                        'sampling_rules': {'match_expression': 'match-expression'}
                    }
                ],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'cluster_id': CLUSTER_ID,
                'cluster_environment': 'testing',
                'cluster_alias': 'cluster-alias',
                'monitor_journald': None,
                'logs': [
                    {
                        'path': '/p1',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ]
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 100000000,
                'max_existing_log_offset_size': 200000000,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': {
                    'serverHost': 'kube-cluster',
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias'},
                'monitors': [],
                'logs': [
                    {
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=',
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ],
            },
        ),
        (
                {
                    'scalyr_key': SCALYR_KEY,
                    'cluster_id': CLUSTER_ID,
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias',
                    'parse_lines_json': True,
                    'monitor_journald': None,
                    'logs': [
                        {
                            'path': '/p1',
                            'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                            'copy_from_start': True,
                            'redaction_rules': {'match_expression': 'match-expression'}
                        }
                    ]
                },
                {
                    'api_key': 'scalyr-key-123',
                    'max_log_offset_size': 100000000,
                    'max_existing_log_offset_size': 200000000,
                    'max_allowed_request_size': 5500000,
                    'min_request_spacing_interval': 0.5,
                    'max_request_spacing_interval': 1.0,
                    'pipeline_threshold': 0.1,
                    "compression_type": "deflate",
                    "compression_level": 9,
                    'implicit_metric_monitor': False,
                    'implicit_agent_process_metrics_monitor': False,
                    'server_attributes': {
                        'serverHost': 'kube-cluster',
                        'cluster_environment': 'testing',
                        'cluster_alias': 'cluster-alias'
                        },
                    'monitors': [],
                    'logs': [
                        {
                            'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                            'path': '/p1',
                            'rename_logfile': '?application=&component=&version=',
                            'parse_lines_as_json': True,
                            'copy_from_start': True,
                            'redaction_rules': {'match_expression': 'match-expression'}
                        }
                    ],
                },
        ),
        (
                {
                    'scalyr_key': SCALYR_KEY,
                    'cluster_id': CLUSTER_ID,
                    'cluster_environment': 'testing',
                    'cluster_alias': 'cluster-alias',
                    'parse_lines_json': True,
                    'monitor_journald': None,
                    'logs': [
                        {
                            'path': '/p1',
                            'attributes': {
                                'a1': 'v1',
                                'parser': 'c-parser',
                                'application': APPLICATION_ID,
                                'component': COMPONENT,
                                'version': APPLICATION_VERSION
                            },
                            'copy_from_start': True,
                            'redaction_rules': {'match_expression': 'match-expression'}
                        }
                    ]
                },
                {
                    'api_key': 'scalyr-key-123',
                    'max_log_offset_size': 100000000,
                    'max_existing_log_offset_size': 200000000,
                    'max_allowed_request_size': 5500000,
                    'min_request_spacing_interval': 0.5,
                    'max_request_spacing_interval': 1.0,
                    'pipeline_threshold': 0.1,
                    "compression_type": "deflate",
                    "compression_level": 9,
                    'implicit_metric_monitor': False,
                    'implicit_agent_process_metrics_monitor': False,
                    'server_attributes': {
                        'serverHost': 'kube-cluster',
                        'cluster_environment': 'testing',
                        'cluster_alias': 'cluster-alias'
                        },
                    'monitors': [],
                    'logs': [
                        {
                            'attributes': {
                                'a1': 'v1',
                                'parser': 'c-parser',
                                'application': APPLICATION_ID,
                                'component': COMPONENT,
                                'version': APPLICATION_VERSION
                            },
                            'path': '/p1',
                            'rename_logfile': '?application={}&component={}&version={}'.format(
                                quote_plus(APPLICATION_ID),
                                quote_plus(COMPONENT),
                                quote_plus(APPLICATION_VERSION)),
                            'parse_lines_as_json': True,
                            'copy_from_start': True,
                            'redaction_rules': {'match_expression': 'match-expression'}
                        }
                    ],
                },
        ),
    )
)
def test_tpl_render(monkeypatch, kwargs, expected):
    tpl = load_template(TPL_NAME)

    config = tpl.render(**kwargs)

    assert json.loads(config) == expected


def test_container_annotation_no_annotation():
    assert container_annotation(
        annotations={},
        container_name="cnt",
        pod_name="pod",
        annotation_key="foo",
        result_key="bar",
        default="def",
    ) == "def"


def test_container_annotation_value_is_set():
    assert container_annotation(
        annotations={
            "foo": json.dumps(
                [{"container": "cnt",
                  "bar": {"some": "data", "with": ["arbitrary", "structure"]}},
                 {"container": "other-cnt",
                  "bar": "not for us"}]
            )
        },
        container_name="cnt",
        pod_name="pod",
        annotation_key="foo",
        result_key="bar",
        default="def",
    ) == {"some": "data", "with": ["arbitrary", "structure"]}


def test_container_annotation_other_container():
    assert container_annotation(
        annotations={
            "foo": json.dumps(
                [{"container": "other-cnt",
                  "bar": "not for us"}]
            )
        },
        container_name="cnt",
        pod_name="pod",
        annotation_key="foo",
        result_key="bar",
        default="def",
    ) == "def"


def test_container_annotation_not_a_list():
    assert container_annotation(
        annotations={
            "foo": json.dumps(
                {"container": "cnt",
                 "bar": {"some": "data", "with": ["arbitrary", "structure"]}}
            )
        },
        container_name="cnt",
        pod_name="pod",
        annotation_key="foo",
        result_key="bar",
        default="def",
    ) == "def"


def test_container_annotation_invalid_json():
    assert container_annotation(
        annotations={
            "foo": "[{]"
        },
        container_name="cnt",
        pod_name="pod",
        annotation_key="foo",
        result_key="bar",
        default="def",
    ) == "def"


@pytest.fixture
def minimal_kwargs():
    return {'pod_name': 'some-random-pod',
            'container_name': 'cnt'}


def test_parser_no_annotation(minimal_kwargs):
    assert get_parser({}, minimal_kwargs) == 'json'


def test_parser_custom(minimal_kwargs):
    annotations = {
        "kubernetes-log-watcher/scalyr-parser": json.dumps(
            [{"container": "cnt", "parser": "custom-parser"}]
        )
    }
    assert get_parser(annotations, minimal_kwargs) == "custom-parser"


def test_sampling_rules_no_annotation(minimal_kwargs):
    assert get_sampling_rules({}, minimal_kwargs) is None


def test_sampling_rules_custom(minimal_kwargs):
    annotations = {
        "kubernetes-log-watcher/scalyr-sampling-rules": json.dumps(
            [{"container": "cnt", "sampling-rules": {"foo": "bar"}}]
        )
    }
    assert get_sampling_rules(annotations, minimal_kwargs) == {"foo": "bar"}


def test_redaction_rules_no_annotation(minimal_kwargs):
    assert get_redaction_rules({}, minimal_kwargs) == [JWT_REDACTION_RULE]


def test_redaction_rules_custom(minimal_kwargs):
    custom_rule = {"match_expression": "foo", "replacement": "bar"}
    annotations = {
        "kubernetes-log-watcher/scalyr-redaction-rules": json.dumps(
            [{"container": "cnt", "redaction-rules": [custom_rule]}]
        )
    }
    assert get_redaction_rules(annotations, minimal_kwargs) == [custom_rule, JWT_REDACTION_RULE]


def test_redaction_rules_invalid_format(minimal_kwargs):
    custom_rule = {"match_expression": "foo", "replacement": "bar"}
    annotations = {
        "kubernetes-log-watcher/scalyr-redaction-rules": json.dumps(
            [{"container": "cnt", "redaction-rules": custom_rule}]   # not a list
        )
    }
    assert get_redaction_rules(annotations, minimal_kwargs) == [JWT_REDACTION_RULE]

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

from .conftest \
    import CLUSTER_ID, CLUSTER_ENVIRONMENT, CLUSTER_ALIAS, NODE, APPLICATION, VERSION, COMPONENT, CONTAINER_ID
from .conftest import SCALYR_KEY, SCALYR_DEST_PATH, SCALYR_JOURNALD_DEFAULTS, SCALYR_DEFAULT_PARSER

DEFAULT_ENV = {
    'CLUSTER_ENVIRONMENT': CLUSTER_ENVIRONMENT,
    'CLUSTER_ALIAS': CLUSTER_ALIAS,
    'CLUSTER_NODE_NAME': NODE,
    'WATCHER_SCALYR_API_KEY_FILE': '',
    'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
}

ENVS = (
    {**DEFAULT_ENV, 'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'},
    {**DEFAULT_ENV},
    {**DEFAULT_ENV, 'WATCHER_SCALYR_JOURNALD': 'true'},
    {**DEFAULT_ENV, 'WATCHER_SCALYR_JOURNALD': 'true', 'WATCHER_SCALYR_JOURNALD_WRITE_RATE': '1',
        'WATCHER_SCALYR_JOURNALD_WRITE_BURST': '2'},
)

KWARGS_KEYS = ('scalyr_key', 'parse_lines_json', 'enable_profiling', 'cluster_id', 'logs', 'monitor_journald')


SCALYR_MONITOR_JOURNALD = copy.deepcopy(SCALYR_JOURNALD_DEFAULTS)
SCALYR_MONITOR_JOURNALD['attributes']['node'] = NODE

SCALYR_SAMPLING_RULES = [
    {
        'application': 'app-1',
        'component': 'comp-1',
        'probability': 0,
        'value': '{"annotation": 1}',
    },
    {
        'application': 'app-1',
        'component': 'comp-1',
        'probability': 0.5,
        'value': '{"annotation": 2}',
    },
    {
        'application': 'app-1',
        'component': 'comp-2',
        'probability': 1,
        'value': '{"annotation": 3}',
    },
    {
        'application': 'app-1',
        'value': '{"annotation": 4}',
    },
    {
        'application': 'app-1',
        'component': 'comp-3',
        'probability': 10,
        'value': '{"annotation": 5}',
    },
    {
        'application': 'app-1',
        'component': 'comp-3',
        'value': '{"annotation": 6}',
    },
    {
        'application': 'app-2',
        'component': 'comp-1',
        'value': '{"annotation": 7}',
    },
    {
        'component': 'comp-5',
        'value': '{"annotation": 8}',
    },
    {
        'application': 'app-2',
        'value': '{"annotation": 9}',
    },
    {
        'application': 'app-3',
    },
    {
        'application': 'app-3',
        'value': 'not valid JSON',
    },
]


def assert_fx_sanity(kwargs):
    assert set(KWARGS_KEYS) == set(kwargs.keys())


def assert_agent(agent):
    assert agent.name

    assert agent.api_key_file == os.environ.get('WATCHER_SCALYR_API_KEY_FILE')
    assert agent.dest_path == os.environ.get('WATCHER_SCALYR_DEST_PATH')
    assert agent.config_path == os.environ.get('WATCHER_SCALYR_CONFIG_PATH', SCALYR_CONFIG_PATH)

    journald = os.environ.get('WATCHER_SCALYR_JOURNALD')
    journald_defaults = copy.deepcopy(SCALYR_JOURNALD_DEFAULTS)
    if os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_RATE'):
        journald_defaults['write_rate'] = int(os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_RATE'))
    if os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_BURST'):
        journald_defaults['write_burst'] = int(os.environ.get('WATCHER_SCALYR_JOURNALD_WRITE_BURST'))
    assert agent.journald == (journald_defaults if journald else None)

    assert agent.server_attributes['serverHost'] == CLUSTER_ID
    assert agent.server_attributes['cluster'] == CLUSTER_ID
    assert agent.server_attributes['cluster_environment'] == CLUSTER_ENVIRONMENT
    assert agent.server_attributes['environment'] == CLUSTER_ENVIRONMENT
    assert agent.server_attributes['cluster_alias'] == CLUSTER_ALIAS
    assert agent.server_attributes['node'] == NODE
    assert agent.server_attributes['parser'] == SCALYR_DEFAULT_PARSER


def patch_env(monkeypatch, scalyr_key_file, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    if 'WATCHER_SCALYR_API_KEY_FILE' in env:
        monkeypatch.setenv('WATCHER_SCALYR_API_KEY_FILE', scalyr_key_file)

    if 'WATCHER_SCALYR_CONFIG_PATH' not in env:
        monkeypatch.delenv('WATCHER_SCALYR_CONFIG_PATH', raising=False)


@pytest.fixture(params=ENVS)
def scalyr_env(monkeypatch, scalyr_key_file, request):
    patch_env(monkeypatch, scalyr_key_file, request.param)


def patch_os(monkeypatch):
    makedirs = MagicMock()
    symlink = MagicMock()
    listdir = MagicMock(return_value=[])

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
    'env,isdir',
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
                'WATCHER_SCALYR_API_KEY_FILE': '',
            },
            (True, True)
        ),
        (
            {
                'WATCHER_SCALYR_API_KEY_FILE': '',
                'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
                'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
            },
            # Config path does not exist
            (False, True)
        ),
        (
            {
                'WATCHER_SCALYR_API_KEY_FILE': '',
                'WATCHER_SCALYR_DEST_PATH': SCALYR_DEST_PATH,
                'WATCHER_SCALYR_CONFIG_PATH': '/etc/config'
            },
            # Dest path does not exist
            (True, False)
        ),
    )
)
def test_initialization_failure(monkeypatch, scalyr_key_file, env, isdir):
    patch_env(monkeypatch, scalyr_key_file, env)
    patch_os(monkeypatch)

    isdir = MagicMock(side_effect=isdir)
    monkeypatch.setattr('os.path.isdir', isdir)

    with pytest.raises(RuntimeError):
        ScalyrAgent({
            'cluster_id': CLUSTER_ID,
            'scalyr_sampling_rules': None,
        })


def test_add_log_target(monkeypatch, scalyr_env, fx_scalyr):
    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = SCALYR_MONITOR_JOURNALD if os.environ.get('WATCHER_SCALYR_JOURNALD') else {}

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False, True])
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

    current_targets = MagicMock(return_value=set())
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })
    assert_agent(agent)

    mock_open, mock_fp = patch_open(monkeypatch)

    with agent:
        agent.add_log_target(target)
        if kwargs['logs'][0]['attributes']['parser'] == SCALYR_DEFAULT_PARSER:
            assert 'parser' not in agent.logs[target['id']]['attributes']
        else:
            assert agent.logs[target['id']]['attributes']['parser'] == kwargs['logs'][0]['attributes']['parser']

    log_path = kwargs['logs'][0]['path']

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    mock_open.assert_called_with(agent.config_path, 'w')
    mock_fp.write.assert_called_once()

    assert agent.first_run is False


def test_add_log_target_no_src(monkeypatch, scalyr_env, fx_scalyr):
    patch_os(monkeypatch)

    target = fx_scalyr['target']

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[False])
    monkeypatch.setattr('os.path.exists', exists)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    agent.add_log_target(target)

    assert agent.logs == {}


def test_add_log_target_no_change(monkeypatch, scalyr_env, fx_scalyr):
    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = SCALYR_MONITOR_JOURNALD if os.environ.get('WATCHER_SCALYR_JOURNALD') else {}

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False, True])
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

    log_path = kwargs['logs'][0]['path']

    # targets did not change
    current_targets = MagicMock(return_value={log_path})
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    mock_open, mock_fp = patch_open(monkeypatch)

    # assuming not the first run
    agent._first_run = False
    agent.api_key = SCALYR_KEY
    mock_fp.read.side_effect = lambda: SCALYR_KEY

    with agent:
        agent.add_log_target(target)

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    mock_fp.write.assert_not_called()

    assert agent.first_run is False


def test_flush_failure(monkeypatch, scalyr_env, fx_scalyr):
    target = fx_scalyr['target']
    kwargs = fx_scalyr['kwargs']

    assert_fx_sanity(kwargs)

    # adjust kwargs
    kwargs['monitor_journald'] = SCALYR_MONITOR_JOURNALD if os.environ.get('WATCHER_SCALYR_JOURNALD') else {}

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False, True])
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

    log_path = kwargs['logs'][0]['path']

    current_targets = MagicMock(return_value=set())
    monkeypatch.setattr(ScalyrAgent, '_get_current_log_paths', current_targets)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    mock_open, mock_fp = patch_open(monkeypatch, Exception)

    with agent:
        agent.add_log_target(target)

    makedirs.assert_called_with(os.path.dirname(log_path))
    symlink.assert_called_with(target['kwargs']['log_file_path'], log_path)

    assert agent.first_run is False


@pytest.mark.parametrize(
    'config,result',
    (
        (
            {'scalyr_api_key': '123', 'logs': [{'path': '/p1'}, {'path': '/p2'}, {'path': '/p3'}]},
            {'/p1', '/p2', '/p3'}
        ),
        (
            Exception,
            set()
        )
    )
)
def test_get_current_log_paths(monkeypatch, scalyr_key_file, config, result):
    patch_env(monkeypatch, scalyr_key_file, ENVS[0])

    mock_open, mock_fp = patch_open(monkeypatch)

    load = MagicMock(return_value=config)
    monkeypatch.setattr('json.load', load)

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False, True])
    monkeypatch.setattr('os.path.exists', exists)

    makedirs, symlink, listdir = patch_os(monkeypatch)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    res = agent._get_current_log_paths()

    assert res == result

    mock_open.assert_called_with(os.path.join(agent.config_path))


@pytest.mark.parametrize('exc', (None, OSError))
def test_remove_log_target(monkeypatch, scalyr_key_file, exc):
    patch_env(monkeypatch, scalyr_key_file, ENVS[0])
    patch_os(monkeypatch)

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False, True])
    monkeypatch.setattr('os.path.exists', exists)

    rmtree = MagicMock()
    if exc:
        rmtree.side_effect = exc
    monkeypatch.setattr('shutil.rmtree', rmtree)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
    })

    assert_agent(agent)

    container_id = 'container-1'
    agent.remove_log_target(container_id)

    rmtree.assert_called_with(os.path.join(agent.dest_path, container_id))


SERVER_ATTRIBUTES = {
                    'serverHost': CLUSTER_ID,
                    'cluster': CLUSTER_ID,
                    'cluster_environment': CLUSTER_ENVIRONMENT,
                    'cluster_alias': CLUSTER_ALIAS,
                    'environment': CLUSTER_ENVIRONMENT,
                    'node': NODE,
                    'parser': SCALYR_DEFAULT_PARSER
                }


@pytest.mark.parametrize(
    'kwargs,expected',
    (
        (
            {
                'scalyr_key': SCALYR_KEY,
                'monitor_journald': None,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': []
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': [], 'monitors': [], 'journald_logs': [],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': [],
                'monitor_journald': {
                    'journal_path': None, 'attributes': {}, 'extra_fields': {}, 'write_rate': 10000,
                    'write_burst': 200000
                },
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': [],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                        'monitor_log_write_rate': 10000,
                        'monitor_log_max_write_burst': 200000,
                    }
                ],
                'journald_logs': [{'journald_unit': '.*', 'parser': 'journald_monitor'}],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': [
                    {
                        'path': '/p1',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True
                    }
                ],
                'monitor_journald': {
                    'journal_path': '/var/log/journal',
                    # 'extra_fields': {'_COMM': 'command'},
                    'write_rate': 10000,
                    'write_burst': 200000,
                },
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'logs': [
                    {
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=&container_id=',
                        'copy_from_start': True
                    }
                ],
                'monitors': [
                    {
                        'module': 'scalyr_agent.builtin_monitors.journald_monitor',
                        'monitor_log_write_rate': 10000,
                        'monitor_log_max_write_burst': 200000,
                        'journal_path': '/var/log/journal',
                        # 'extra_fields': {'_COMM': 'command'}
                    }
                ],
                'journald_logs': [{'journald_unit': '.*', 'parser': 'journald_monitor'}],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
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
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'monitors': [],
                'logs': [
                    {
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=&container_id=',
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'copy_from_start': True,
                        'sampling_rules': {'match_expression': 'match-expression'}
                    }
                ],
                'journald_logs': [],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
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
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'monitors': [],
                'logs': [
                    {
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=&container_id=',
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ],
                'journald_logs': [],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
                'parse_lines_json': True,
                'enable_profiling': False,
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
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'monitors': [],
                'logs': [
                    {
                        'attributes': {'a1': 'v1', 'parser': 'c-parser'},
                        'path': '/p1',
                        'rename_logfile': '?application=&component=&version=&container_id=',
                        'parse_lines_as_json': True,
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ],
                'journald_logs': [],
            },
        ),
        (
            {
                'scalyr_key': SCALYR_KEY,
                'server_attributes': SERVER_ATTRIBUTES,
                'parse_lines_json': True,
                'enable_profiling': True,
                'monitor_journald': None,
                'logs': [
                    {
                        'path': '/p1',
                        'attributes': {
                            'a1': 'v1',
                            'parser': 'c-parser',
                            'application': APPLICATION,
                            'component': COMPONENT,
                            'version': VERSION,
                            'container_id': CONTAINER_ID,
                        },
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ],
            },
            {
                'api_key': 'scalyr-key-123',
                'max_log_offset_size': 536870912,
                'max_existing_log_offset_size': 536870912,
                'max_allowed_request_size': 5500000,
                'min_request_spacing_interval': 0.5,
                'max_request_spacing_interval': 1.0,
                'pipeline_threshold': 0.1,
                "compression_type": "deflate",
                'enable_profiling': True,
                "compression_level": 9,
                "max_line_size": 49900,
                "read_page_size": 131072,
                'implicit_metric_monitor': False,
                'implicit_agent_process_metrics_monitor': False,
                'server_attributes': SERVER_ATTRIBUTES,
                'monitors': [],
                'logs': [
                    {
                        'attributes': {
                            'a1': 'v1',
                            'parser': 'c-parser',
                            'application': APPLICATION,
                            'component': COMPONENT,
                            'version': VERSION,
                            'container_id': CONTAINER_ID,
                        },
                        'path': '/p1',
                        'rename_logfile': '?application={}&component={}&version={}&container_id={}'.format(
                            quote_plus(APPLICATION),
                            quote_plus(COMPONENT),
                            quote_plus(VERSION),
                            quote_plus(CONTAINER_ID),
                        ),
                        'parse_lines_as_json': True,
                        'copy_from_start': True,
                        'redaction_rules': {'match_expression': 'match-expression'}
                    }
                ],
                'journald_logs': [],
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


def test_parse_scalyr_sampling_rules(monkeypatch, scalyr_env, fx_scalyr):
    patch_os(monkeypatch)

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[False])
    monkeypatch.setattr('os.path.exists', exists)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
        'scalyr_sampling_rules': SCALYR_SAMPLING_RULES,
    })

    assert agent.scalyr_sampling_rules == [
        {'application': 'app-1', 'component': 'comp-1', 'probability': 0, 'value': '{"annotation": 1}'},
        {'application': 'app-1', 'component': 'comp-1', 'probability': 0.5, 'value': '{"annotation": 2}'},
        {'application': 'app-1', 'component': 'comp-2', 'probability': 1, 'value': '{"annotation": 3}'},
        {'application': 'app-1', 'value': '{"annotation": 4}'},
        {'application': 'app-1', 'component': 'comp-3', 'value': '{"annotation": 6}'},
        {'application': 'app-2', 'component': 'comp-1', 'value': '{"annotation": 7}'},
        {'component': 'comp-5', 'value': '{"annotation": 8}'},
        {'application': 'app-2', 'value': '{"annotation": 9}'},
    ]


def test_get_scalyr_sampling_rule(monkeypatch, scalyr_env, fx_scalyr):
    patch_os(monkeypatch)

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[False])
    monkeypatch.setattr('os.path.exists', exists)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
        'scalyr_sampling_rules': SCALYR_SAMPLING_RULES,
    })

    # Component is not applied because of `probability`
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-1',
        'component': 'comp-1',
        'container_id': '472de5194b88bc3302721ac28dcfe3a9fdc58350d0a8dcafab2f24683bca50f8',
    })
    assert rule == '{"annotation": 2}'

    # Component is applied because of `probability`
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-1',
        'component': 'comp-1',
        'container_id': 'f2c88e81c4a4dd91023e5725bae3f743caef6e6bd727e255c7c6949a8bf56978',
    })
    assert rule == '{"annotation": 4}'

    # Get rule for component
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-1',
        'component': 'comp-2',
        'container_id': '472de5194b88bc3302721ac28dcfe3a9fdc58350d0a8dcafab2f24683bca50f8',
    })
    assert rule == '{"annotation": 3}'

    # Component rule is lower than application rule - use application's one
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-1',
        'component': 'comp-3',
        'container_id': '472de5194b88bc3302721ac28dcfe3a9fdc58350d0a8dcafab2f24683bca50f8',
    })
    assert rule == '{"annotation": 4}'

    # No rule for component - use application's rule
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-1',
        'component': 'comp-4',
        'container_id': '472de5194b88bc3302721ac28dcfe3a9fdc58350d0a8dcafab2f24683bca50f8',
    })
    assert rule == '{"annotation": 4}'

    # Get rule by component
    rule = agent.get_scalyr_sampling_rule({
        'application': 'app-5',
        'component': 'comp-5',
        'container_id': '472de5194b88bc3302721ac28dcfe3a9fdc58350d0a8dcafab2f24683bca50f8',
    })
    assert rule == '{"annotation": 8}'


def test_add_log_target_with_sampling(monkeypatch, scalyr_env, fx_scalyr):
    target = fx_scalyr['target']

    isdir = MagicMock(side_effect=[True, True])
    monkeypatch.setattr('os.path.isdir', isdir)

    exists = MagicMock(side_effect=[True, False, False])
    monkeypatch.setattr('os.path.exists', exists)

    patch_os(monkeypatch)

    agent = ScalyrAgent({
        'cluster_id': CLUSTER_ID,
        'scalyr_sampling_rules': [
            {
                'application': 'app-2',
                'value': '[{"container": "app-1-container-1", "sampling-rules":[{ "match_expression": "WARNING", "sampling_rate": 0 }]}]',          # noqa: E501
            },
            {
                'application': 'app-1',
                'component': 'main',
                'value': '[{"container": "app-1-container-1", "sampling-rules":[{ "match_expression": "INFO", "sampling_rate": 0 }]}]',             # noqa: E501
            },
            {
                'application': 'app-1',
                'value': '[{"container": "app-1-container-1", "sampling-rules":[{ "match_expression": "DEBUG", "sampling_rate": 0 }]}]',            # noqa: E501
            },
        ],
    })
    assert_agent(agent)

    agent.add_log_target(target)

    assert agent.logs[target['id']]['sampling_rules'] == [{'match_expression': 'INFO', 'sampling_rate': 0}]

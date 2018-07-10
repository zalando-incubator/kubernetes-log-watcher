import os
import copy

import pytest

CLUSTER_ID = 'kube-cluster'
NODE = 'node-1'

APPDYNAMICS_DEST_PATH = '/var/log/watcher/'

SCALYR_DEST_PATH = '/var/log/watcher/'
SCALYR_KEY = 'scalyr-key-123'
SCALYR_JOURNALD_DEFAULTS = {
    'journal_path': None, 'attributes': {'cluster': CLUSTER_ID}, 'extra_fields': {}, 'write_rate': 10000,
    'write_burst': 200000
}
SCALYR_ANNOTATION_PARSER = 'kubernetes-log-watcher/scalyr-parser'
SCALYR_ANNOTATION_SAMPLING_RULES = 'kubernetes-log-watcher/scalyr-sampling-rules'
SCALYR_ANNOTATION_REDACTION_RULES = 'kubernetes-log-watcher/scalyr-redaction-rules'

TARGET = {
    'id': 'container-1',
    'kwargs': {
        'application_id': 'app-1',
        'application_version': 'v1',
        'cluster_id': 'kube-cluster',
        'release': '2016',
        'pod_name': 'pod-1',
        'namespace': 'default',
        'container_name': 'app-1-container-1',
        'node_name': NODE,
        'log_file_path': '/mn/containers/container-1/container-1-json.log',
        'container_id': 'container-1',
        'container_path': '/mnt/containers/container-1',
        'log_file_name': 'container-1-json.log',
        'pod_annotations': {
            SCALYR_ANNOTATION_PARSER: '[{"container": "app-1-container-1", "parser": "custom-parser"}]',
            SCALYR_ANNOTATION_SAMPLING_RULES:
                '[{"container": "app-1-container-1", "sampling-rules":[{ "match_expression": "<expression here>", '
                '"sampling_rate": "0" }]}]',
            SCALYR_ANNOTATION_REDACTION_RULES:
                '[{"container": "app-1-container-1", "redaction-rules":[{ "match_expression": "<expression here>" }]}]'
        }

    },
    'pod_labels': {}
}

TARGET_NO_ANNOT = copy.deepcopy(TARGET)
TARGET_NO_ANNOT['kwargs']['pod_annotations'] = {'a/1': 'a-1'}

TARGET_INVALID_ANNOT = copy.deepcopy(TARGET)
TARGET_INVALID_ANNOT['kwargs']['pod_annotations'] = {SCALYR_ANNOTATION_PARSER: '{"container": "cont-1", "parser": "n"}'}


@pytest.fixture(params=[
    (
        # 1. containers
        [
            {
                'config': {
                    'Config': {
                        'Labels': {
                            'io.kubernetes.pod.name': 'pod-1', 'pod.namespace': 'default', 'container.name': 'cont-1',
                            'annotation.some-annotation': 'v1',
                        },
                        'Image': 'repo/example.org/cont-1:1.1'
                    }
                },
                'id': 'cont-1',
                'log_file': '/mnt/containers/cont-1/cont-1-json.log'
            },
            {
                'config': {
                    'Config': {
                        'Labels': {'pod.name': 'pod-1', 'pod.namespace': 'default', 'container.name': 'cont-2'},
                        'Image': 'gcr.io/google_containers/pause-123'
                    }
                },
                'id': 'cont-2',
                'log_file': '/mnt/containers/cont-2/cont-2-json.log'
            },
            {
                'config': {
                    'Config': {
                        'Labels': {'pod.name': 'pod-2', 'pod.namespace': 'default', 'container.name': 'cont-3'},
                        'Image': 'repo/example.org/cont-3:1.1'
                    }
                },
                'id': 'cont-3',
                'log_file': '/mnt/containers/cont-3/cont-3-json.log'
            },
            {
                'config': {
                    'Config': {
                        'Labels': {'pod.name': 'pod-3', 'pod.namespace': 'default', 'container.name': 'cont-4'},
                        'Image': 'repo/example.org/cont-4:1.1'
                    }
                },
                'id': 'cont-4',
                'log_file': '/mnt/containers/cont-4/cont-4-json.log'
            },
            {
                'config': {
                    'Config': {
                        'Labels': {'pod.name': 'pod-4', 'pod.namespace': 'kube', 'container.name': 'cont-5'},
                        'Image': 'repo/example.org/cont-5'
                    }
                },
                'id': 'cont-5',
                'log_file': '/mnt/containers/cont-5/cont-5-json.log'
            },
        ],
        # 2. pods
        [
            {
                'metadata': {
                    'name': 'pod-1',
                    'labels': {'application': 'app-1', 'version': 'v1', 'release': '123'},
                    'annotations': {'a/1': 'a-1', 'a/2': 'a-2'},
                }
            },
            {
                'metadata': {
                    'name': 'pod-2',
                    'labels': {'application': 'app-1'}  # missing 'version' label
                }
            },
            {
                'metadata': {
                    'name': 'pod-3',
                    'labels': {'version': 'v1'}  # missing 'application' label
                }
            },
            {
                'metadata': {
                    'name': 'pod-4',
                    'labels': {'application': 'app-2', 'version': 'v1'},
                    'annotations': {},
                }
            },
        ],
        # 3. targets strict
        [
            {
                'pod_labels': {'application': 'app-1', 'version': 'v1', 'release': '123'},
                'id': 'cont-1',
                'kwargs': {
                    'pod_name': 'pod-1', 'release': '123', 'namespace': 'default', 'node_name': NODE,
                    'container_id': 'cont-1', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-1-json.log',
                    'application_id': 'app-1', 'application_version': 'v1', 'container_path': '/mnt/containers/cont-1',
                    'log_file_path': '/mnt/containers/cont-1/cont-1-json.log', 'container_name': 'cont-1',
                    'pod_annotations': {'a/1': 'a-1', 'a/2': 'a-2'}, 'image': 'cont-1', 'image_version': '1.1'
                }
            },
            {
                'pod_labels': {'application': 'app-2', 'version': 'v1'},
                'id': 'cont-5',
                'kwargs': {
                    'pod_name': 'pod-4', 'release': '', 'namespace': 'kube', 'node_name': NODE,
                    'container_id': 'cont-5', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-5-json.log',
                    'application_id': 'app-2', 'application_version': 'v1', 'container_path': '/mnt/containers/cont-5',
                    'log_file_path': '/mnt/containers/cont-5/cont-5-json.log', 'container_name': 'cont-5',
                    'pod_annotations': {}, 'image': 'cont-5', 'image_version': 'latest'
                }
            },
        ],
        # 4. targets no labels
        [
            {
                'pod_labels': {'application': 'app-1'},
                'id': 'cont-3',
                'kwargs': {
                    'pod_name': 'pod-2', 'namespace': 'default', 'node_name': NODE, 'release': '',
                    'container_id': 'cont-3', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-3-json.log',
                    'application_id': 'app-1', 'application_version': '', 'container_path': '/mnt/containers/cont-3',
                    'log_file_path': '/mnt/containers/cont-3/cont-3-json.log', 'container_name': 'cont-3',
                    'pod_annotations': {}, 'image': 'cont-3', 'image_version': '1.1'
                }
            },
            {
                'pod_labels': {'version': 'v1'},
                'id': 'cont-4',
                'kwargs': {
                    'pod_name': 'pod-3', 'namespace': 'default', 'node_name': NODE, 'release': '',
                    'container_id': 'cont-4', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-4-json.log',
                    'application_id': 'pod-3', 'application_version': 'v1', 'container_path': '/mnt/containers/cont-4',
                    'log_file_path': '/mnt/containers/cont-4/cont-4-json.log', 'container_name': 'cont-4',
                    'pod_annotations': {}, 'image': 'cont-4', 'image_version': '1.1'
                }
            }
        ],
        # 5. res
        {'cont-1', 'cont-5'}
    )
])
def fx_containers_sync(request):
    return request.param


KWARGS = {
    'scalyr_key': SCALYR_KEY,
    'cluster_id': CLUSTER_ID,
    'monitor_journald': None,
    'parse_lines_json': False,
    'logs': [
        {
            'path': os.path.join(SCALYR_DEST_PATH, 'container-1', 'app-1-v1.log'),
            'attributes': {
                'application': 'app-1',
                'version': 'v1',
                'cluster': 'kube-cluster',
                'release': '2016',
                'pod': 'pod-1',
                'namespace': 'default',
                'container': 'app-1-container-1',
                'node': NODE,
                'parser': 'custom-parser',
            }
        }
    ]
}

KWARGS_JSON = copy.deepcopy(KWARGS)
KWARGS_JSON['logs'][0]['attributes']['parser'] = 'json'


@pytest.fixture(params=[
    {
        'target': TARGET,
        'kwargs': KWARGS,
    },
    {
        'target': TARGET_NO_ANNOT,
        'kwargs': KWARGS_JSON
    },
    {
        'target': TARGET_INVALID_ANNOT,
        'kwargs': KWARGS_JSON
    }
])
def fx_scalyr(request):
    return request.param


@pytest.fixture(params=[
    {
        'target': TARGET,
        'kwargs': {
            'application_id': 'app-1',
            'application_version': 'v1',
            'cluster_id': 'kube-cluster',
            'release': '2016',
            'pod_name': 'pod-1',
            'namespace': 'default',
            'container_name': 'app-1-container-1',
            'node_name': NODE,
            'log_file_path': '/mn/containers/container-1/container-1-json.log',
            'container_id': 'container-1',
            'container_path': '/mnt/containers/container-1',
            'log_file_name': 'container-1-json.log',
            'app_name': None,
            'app_tire': None,
        }
    }
])
def fx_appdynamics(request):
    return request.param

import os

import pytest

CLUSTER_ID = 'kube-cluster'

APPDYNAMICS_DEST_PATH = '/var/log/watcher/'

SCALYR_DEST_PATH = '/var/log/watcher/'
SCALYR_KEY = 'scalyr-key-123'
SCALYR_JOURNALD_DEFAULTS = {'journal_path': None, 'attributes': {'cluster': CLUSTER_ID}, 'extra_fields': {}}

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
        'node_name': 'node-1',
        'log_file_path': '/mn/containers/container-1/container-1-json.log',
        'container_id': 'container-1',
        'container_path': '/mnt/containers/container-1',
        'log_file_name': 'container-1-json.log',

    },
    'pod_labels': {}
}


@pytest.fixture(params=[
    (
        # 1. containers
        [
            {
                'config': {
                    'Config': {'Labels': {'pod.name': 'pod-1', 'pod.namespace': 'default', 'container.name': 'cont-1'}}
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
                    'Config': {'Labels': {'pod.name': 'pod-2', 'pod.namespace': 'default', 'container.name': 'cont-3'}}
                },
                'id': 'cont-3',
                'log_file': '/mnt/containers/cont-3/cont-3-json.log'
            },
            {
                'config': {
                    'Config': {'Labels': {'pod.name': 'pod-3', 'pod.namespace': 'default', 'container.name': 'cont-4'}}
                },
                'id': 'cont-4',
                'log_file': '/mnt/containers/cont-4/cont-4-json.log'
            },
            {
                'config': {
                    'Config': {'Labels': {'pod.name': 'pod-4', 'pod.namespace': 'kube', 'container.name': 'cont-5'}}
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
                    'labels': {'application': 'app-1', 'version': 'v1', 'release': '123'}
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
                    'labels': {'version': 'v1'}  # missing 'app' label
                }
            },
            {
                'metadata': {
                    'name': 'pod-4',
                    'labels': {'application': 'app-2', 'version': 'v1'}
                }
            },
        ],
        # 3. targets
        [
            {
                'pod_labels': {'application': 'app-1', 'version': 'v1', 'release': '123'},
                'id': 'cont-1',
                'kwargs': {
                    'pod_name': 'pod-1', 'release': '123', 'namespace': 'default', 'node_name': 'node-1',
                    'container_id': 'cont-1', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-1-json.log',
                    'application_id': 'app-1', 'application_version': 'v1', 'container_path': '/mnt/containers/cont-1',
                    'log_file_path': '/mnt/containers/cont-1/cont-1-json.log', 'container_name': 'cont-1'
                }
            },
            {
                'pod_labels': {'application': 'app-2', 'version': 'v1'},
                'id': 'cont-5',
                'kwargs': {
                    'pod_name': 'pod-4', 'release': '', 'namespace': 'kube', 'node_name': 'node-1',
                    'container_id': 'cont-5', 'cluster_id': 'kube-cluster', 'log_file_name': 'cont-5-json.log',
                    'application_id': 'app-2', 'application_version': 'v1', 'container_path': '/mnt/containers/cont-5',
                    'log_file_path': '/mnt/containers/cont-5/cont-5-json.log', 'container_name': 'cont-5'
                }
            }
        ],
        # 4. res
        {'cont-1', 'cont-5'}
    )
])
def fx_containers_sync(request):
    return request.param


@pytest.fixture(params=[
    {
        'target': TARGET,
        'kwargs': {
            'scalyr_key': SCALYR_KEY,
            'cluster_id': CLUSTER_ID,
            'monitor_journald': None,
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
                        'node': 'node-1',
                    }
                }
            ]
        },
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
            'node_name': 'node-1',
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

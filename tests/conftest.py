import pytest


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
        # 3. TPL kwargs
        [
            {
                'app_id': 'app-1', 'app_version': 'v1', 'conatiner_id': 'cont-1', 'pod_name': 'pod-1',
                'namespace': 'default', 'container_name': 'cont-1', 'log_file_name': 'cont-1-json.log',
                'container_path': '/mnt/containers/cont-1', 'node_name': 'node-1', 'release': '123',
            },
            {
                'app_id': 'app-2', 'app_version': 'v1', 'conatiner_id': 'cont-5', 'pod_name': 'pod-4',
                'namespace': 'kube', 'container_name': 'cont-5', 'log_file_name': 'cont-5-json.log',
                'container_path': '/mnt/containers/cont-5', 'node_name': 'node-1',
            },
        ],
        # 4. res
        ['cont-1', 'cont-5']
    )
])
def fx_containers_sync(request):
    return request.param

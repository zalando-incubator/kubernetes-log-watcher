import pytest

from mock import MagicMock

from kube_log_watcher.kube import get_pods, is_pause_container, get_pod_labels
from kube_log_watcher.kube import PAUSE_CONTAINER_PREFIX


KUBE_URL = 'https://my-kube-api'

# Mock pykube Pod obj
POD_OBJ = MagicMock()
POD_OBJ.obj = {
    'metadata': {
        'labels': {'app': 'app-3', 'version': 'v1'},
        'name': 'pod-3'
    }
}

PODS = [
    {
        'metadata': {
            'labels': {'app': 'app-1', 'version': 'v1'},
            'name': 'pod-1'
        }
    },
    {
        'metadata': {
            'labels': {'app': 'app-2', 'version': 'v1'},
            'name': 'pod-2'
        }
    },
    POD_OBJ
]


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pods_url(monkeypatch, namespace):
    get = MagicMock()
    res = [1, 2, 3]
    get.return_value.json.return_value = {'items': res}

    monkeypatch.setattr('requests.get', get)

    result = get_pods(KUBE_URL, namespace=namespace)

    assert res == result

    get.assert_called_with('https://my-kube-api/api/v1/namespaces/{}/pods'.format(namespace))


@pytest.mark.parametrize(
    'config,res',
    (
        ({'Image': PAUSE_CONTAINER_PREFIX}, True),
        ({'Image': PAUSE_CONTAINER_PREFIX + '-123'}, True),
        ({}, False),
        ({'Image': PAUSE_CONTAINER_PREFIX[:-1]}, False),
        ({'Image': PAUSE_CONTAINER_PREFIX[1:]}, False),
    )
)
def test_pause_container(monkeypatch, config, res):
    assert res == is_pause_container(config)


@pytest.mark.parametrize(
    'pod_name,res',
    (
        ('pod-1', {'app': 'app-1', 'version': 'v1'}),
        ('pod-2', {'app': 'app-2', 'version': 'v1'}),
        ('pod-3', POD_OBJ.obj['metadata']['labels']),
        ('pod-4', {}),
    )
)
def test_get_pod_labels(monkeypatch, pod_name, res):
    assert get_pod_labels(PODS, pod_name) == res

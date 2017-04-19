import pytest

from mock import MagicMock

from kube_log_watcher.kube import get_pods, is_pause_container, get_pod_labels_annotations, get_client
from kube_log_watcher.kube import PAUSE_CONTAINER_PREFIX, DEFAULT_SERVICE_ACC


KUBE_URL = 'https://my-kube-api'

# Mock pykube Pod obj
POD_OBJ = MagicMock()
POD_OBJ.obj = {
    'metadata': {
        'labels': {'app': 'app-3', 'version': 'v1'},
        'annotations': {'annotation/1': 'a1', 'annotation/2': 'a2'},
        'name': 'pod-3'
    }
}

PODS = [
    {
        'metadata': {
            'labels': {'app': 'app-1', 'version': 'v1'},
            'annotations': {'annotation/1': 'a1', 'annotation/2': 'a2'},
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


def test_get_client(monkeypatch):
    kube_config = MagicMock()
    kube_config.from_service_account.return_value = {}
    kube_client = MagicMock()

    monkeypatch.setattr('pykube.KubeConfig', kube_config)
    monkeypatch.setattr('pykube.HTTPClient', kube_client)

    client = get_client()

    assert client.session.trust_env is False

    kube_config.from_service_account.assert_called_with(DEFAULT_SERVICE_ACC)


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pods_url(monkeypatch, namespace):
    get = MagicMock()
    res = [1, 2, 3]
    get.return_value.json.return_value = {'items': res}

    monkeypatch.setattr('requests.get', get)

    result = get_pods(KUBE_URL, namespace=namespace)

    assert res == result

    get.assert_called_with('https://my-kube-api/api/v1/namespaces/{}/pods'.format(namespace))


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pods_pykube(monkeypatch, namespace):
    get = MagicMock()
    pod = MagicMock()
    res = [1, 2, 3]
    pod.objects.return_value.filter.return_value = res

    monkeypatch.setattr('kube_log_watcher.kube.get_client', get)
    monkeypatch.setattr('pykube.Pod', pod)

    result = get_pods(namespace=namespace)

    assert res == result

    get.assert_called_once()
    pod.objects.return_value.filter.assert_called_with(namespace=namespace)


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
        ('pod-1', ({'app': 'app-1', 'version': 'v1'}, {'annotation/1': 'a1', 'annotation/2': 'a2'})),
        ('pod-2', ({'app': 'app-2', 'version': 'v1'}, {})),
        ('pod-3', (POD_OBJ.obj['metadata']['labels'], {'annotation/1': 'a1', 'annotation/2': 'a2'})),
        ('pod-4', ({}, {})),
    )
)
def test_get_pod_labels_annotations(monkeypatch, pod_name, res):
    assert get_pod_labels_annotations(PODS, pod_name) == res

import pytest

from mock import MagicMock

from kube_log_watcher.kube import get_pod, is_pause_container, get_client, PodNotFound
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
def test_get_pod_url(monkeypatch, namespace):
    get = MagicMock()
    res = [1]
    get.return_value.json.return_value = {'items': res}

    monkeypatch.setattr('requests.get', get)

    result = get_pod('my-pod', namespace=namespace, kube_url=KUBE_URL)

    assert res[0] == result

    get.assert_called_with('https://my-kube-api/api/v1/namespaces/{}/pods/my-pod'.format(namespace))


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pod_pykube(monkeypatch, namespace):
    get = MagicMock()
    pod = MagicMock()
    res = [1]
    pod.objects.return_value.filter.return_value = res

    monkeypatch.setattr('kube_log_watcher.kube.get_client', get)
    monkeypatch.setattr('pykube.Pod', pod)

    result = get_pod('my-pod', namespace=namespace)

    assert res[0] == result

    get.assert_called_once()
    pod.objects.return_value.filter.assert_called_with(namespace=namespace, field_selector={'metadata.name': 'my-pod'})


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pod_pykube_not_found(monkeypatch, namespace):
    get = MagicMock()
    pod = MagicMock()
    res = []
    pod.objects.return_value.filter.return_value = res

    monkeypatch.setattr('kube_log_watcher.kube.get_client', get)
    monkeypatch.setattr('pykube.Pod', pod)

    with pytest.raises(PodNotFound):
        get_pod('my-pod', namespace=namespace)

    get.assert_called_once()
    pod.objects.return_value.filter.assert_called_with(namespace=namespace, field_selector={'metadata.name': 'my-pod'})


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

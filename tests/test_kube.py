import pykube.exceptions
import pytest
from mock import MagicMock

from kube_log_watcher.kube import PAUSE_CONTAINER_PREFIX, DEFAULT_SERVICE_ACC
from kube_log_watcher.kube import get_pod, is_pause_container, get_client, PodNotFound

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
    monkeypatch.setattr('kube_log_watcher.kube.TimedHTTPClient', kube_client)

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
    mock_pod = MagicMock(name='pod')
    mock_client = MagicMock(name='client')

    pykube_pod = MagicMock()
    pykube_pod_objects = MagicMock()

    pykube_pod.objects.return_value = pykube_pod_objects
    pykube_pod_objects.get_by_name.return_value = mock_pod

    monkeypatch.setattr('kube_log_watcher.kube.get_client', lambda: mock_client)
    monkeypatch.setattr('pykube.Pod', pykube_pod)

    result = get_pod('my-pod', namespace=namespace)

    assert result == mock_pod

    pykube_pod.objects.assert_called_once()
    pykube_pod.objects.assert_called_with(api=mock_client, namespace=namespace)

    pykube_pod_objects.get_by_name.assert_called_once()
    pykube_pod_objects.get_by_name.assert_called_with('my-pod')


@pytest.mark.parametrize('namespace', ('default', 'kube-system'))
def test_get_pod_pykube_not_found(monkeypatch, namespace):
    mock_client = MagicMock(name='client')

    pykube_pod = MagicMock()
    pykube_pod_objects = MagicMock()

    pykube_pod.objects.return_value = pykube_pod_objects
    pykube_pod_objects.get_by_name.side_effect = pykube.exceptions.ObjectDoesNotExist()

    monkeypatch.setattr('kube_log_watcher.kube.get_client', lambda: mock_client)
    monkeypatch.setattr('pykube.Pod', pykube_pod)

    with pytest.raises(PodNotFound):
        get_pod('my-pod', namespace=namespace)

    pykube_pod.objects.assert_called_once()
    pykube_pod.objects.assert_called_with(api=mock_client, namespace=namespace)

    pykube_pod_objects.get_by_name.assert_called_once()
    pykube_pod_objects.get_by_name.assert_called_with('my-pod')


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

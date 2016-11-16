import pytest

from mock import MagicMock

from k8s_log_watcher.kube import get_pods, is_pause_container
from k8s_log_watcher.kube import PAUSE_CONTAINER_PREFIX


KUBE_URL = 'https://my-kube-api'


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

from urllib.parse import urljoin

import pykube
import requests


DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'
DEFAULT_NAMESPACE = 'default'

PODS_URL = 'api/v1/namespaces/default/pods'

PAUSE_CONTAINER_PREFIX = 'gcr.io/google_containers/pause-'


def get_client():
    config = pykube.KubeConfig.from_service_account(DEFAULT_SERVICE_ACC)
    return pykube.HTTPClient(config)


def get_pods(kube_url=None) -> list:
    """
    Return list of pods in cluster. If ``kube_url`` is not ``None`` then K8S service account config won't be used.

    :param kube_url: URL of a proxy to K8S cluster api. This is useful to offload authentication/authorization
                     to proxy service instead of depending on serviceaccount config. Default is ``None``.
    :type kube_url: str

    :return: List of pods.
    :rtype: list
    """
    if kube_url:
        r = requests.get(urljoin(kube_url, PODS_URL))

        r.raise_for_status()

        return r.json().get('items', [])

    kube_client = get_client()
    return pykube.Pod.objects(kube_client).filter(namespace=DEFAULT_NAMESPACE)


def get_pod_labels(pods: list, pod_name: str) -> dict:
    for pod in pods:
        metadata = pod.obj['metadata'] if hasattr(pod, 'obj') else pod['metadata']
        if metadata['name'] == pod_name:
            return metadata['labels']

    return {}


def is_pause_container(config: dict) -> bool:
    """
    Return True if the config belongs to K8S *Pause* containers.

    :param config: Container "Config" from ``config.v2.json``.
    :type config: dict

    :return: True if "Pause" container, False otherwise.
    :rtype: bool
    """
    return config.get('Image', '').startswith(PAUSE_CONTAINER_PREFIX)

import os
import shutil
import subprocess
import logging
import warnings

from urllib.parse import urljoin

from typing import Tuple

import pykube
import requests


DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'
DEFAULT_NAMESPACE = 'default'

PODS_URL = 'api/v1/namespaces/{}/pods'

PAUSE_CONTAINER_PREFIX = 'gcr.io/google_containers/pause-'

logger = logging.getLogger('kube_log_watcher')


class PodNotFound(Exception):
    pass


def update_ca_certificate():
    warnings.warn('update_ca_certificate is deprecated.')
    try:
        shutil.copyfile(os.path.join(DEFAULT_SERVICE_ACC, 'ca.crt'), '/usr/local/share/ca-certificates/ca-kube.crt')
        subprocess.check_call(['update-ca-certificates'])
    except Exception:
        logger.exception('Watcher failed to update CA certificates')
        raise


def get_client():
    config = pykube.KubeConfig.from_service_account(DEFAULT_SERVICE_ACC)
    client = pykube.HTTPClient(config)
    client.session.trust_env = False

    return client


def get_pods(kube_url=None, namespace=DEFAULT_NAMESPACE) -> list:
    """
    Return list of pods in cluster.
    If ``kube_url`` is not ``None`` then kubernetes service account config won't be used.

    :param kube_url: URL of a proxy to kubernetes cluster api. This is useful to offload authentication/authorization
                     to proxy service instead of depending on serviceaccount config. Default is ``None``.
    :type kube_url: str

    :param namespace: Desired namespace of the pods. Default namespace is ``default``.
    :type namespace: str

    :return: List of pods.
    :rtype: list
    """
    if kube_url:
        r = requests.get(urljoin(kube_url, PODS_URL.format(namespace)))

        r.raise_for_status()

        return r.json().get('items', [])

    kube_client = get_client()
    return pykube.Pod.objects(kube_client).filter(namespace=namespace)


def get_pod(name, namespace=DEFAULT_NAMESPACE, kube_url=None) -> pykube.Pod:
    """
    Return Pod with name.
    If ``kube_url`` is not ``None`` then kubernetes service account config won't be used.

    :param name: Pod name to use in filtering.
    :type name: str

    :param namespace: Desired namespace of the pod. Default namespace is ``default``.
    :type namespace: str

    :param kube_url: URL of a proxy to kubernetes cluster api. This is useful to offload authentication/authorization
                     to proxy service instead of depending on serviceaccount config. Default is ``None``.
    :type kube_url: str

    :return: The matching pod.
    :rtype: pykube.Pod
    """
    print('WHAAAT')
    if kube_url:
        r = requests.get(urljoin(kube_url, PODS_URL.format(namespace)))

        r.raise_for_status()

        return r.json().get('items', [])

    kube_client = get_client()
    try:
        return list(
            pykube.Pod.objects(kube_client).filter(namespace=namespace, field_selector={'metadata.name': name}))[0]
    except Exception:
        raise PodNotFound('Cannot find pod: {}'.format(name))


def get_pod_labels_annotations(pods: list, pod_name: str) -> Tuple[dict, dict]:
    for pod in pods:
        metadata = pod.obj['metadata'] if hasattr(pod, 'obj') else pod.get('metadata', {})
        if metadata.get('name') == pod_name:
            return metadata.get('labels', {}), metadata.get('annotations', {})

    logger.warning('Failed to get pod "{}" labels and annotations'.format(pod_name))

    return {}, {}


def is_pause_container(config: dict) -> bool:
    """
    Return True if the config belongs to kubernetes *Pause* containers.

    :param config: Container "Config" from ``config.v2.json``.
    :type config: dict

    :return: True if "Pause" container, False otherwise.
    :rtype: bool
    """
    return config.get('Image', '').startswith(PAUSE_CONTAINER_PREFIX)

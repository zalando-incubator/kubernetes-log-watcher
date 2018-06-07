import os
import shutil
import subprocess
import logging
import warnings

from urllib.parse import urljoin

import pykube
import requests


DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'
DEFAULT_NAMESPACE = 'default'

PODS_URL = 'api/v1/namespaces/{}/pods/{}'

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
    try:
        if kube_url:
            r = requests.get(urljoin(kube_url, PODS_URL.format(namespace, name)))

            r.raise_for_status()

            return r.json().get('items', [])[0]

        kube_client = get_client()
        return list(
            pykube.Pod.objects(kube_client).filter(namespace=namespace, field_selector={'metadata.name': name}))[0]
    except Exception:
        raise PodNotFound('Cannot find pod: {}'.format(name))


def is_pause_container(config: dict) -> bool:
    """
    Return True if the config belongs to kubernetes *Pause* containers.

    :param config: Container "Config" from ``config.v2.json``.
    :type config: dict

    :return: True if "Pause" container, False otherwise.
    :rtype: bool
    """
    return config.get('Image', '').startswith(PAUSE_CONTAINER_PREFIX)

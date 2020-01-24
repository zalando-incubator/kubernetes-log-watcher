import logging
import os
import shutil
import subprocess
import warnings
from urllib.parse import urljoin

import pykube
import requests

import kube_log_watcher

DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'
DEFAULT_NAMESPACE = 'default'

PODS_URL = 'api/v1/namespaces/{}/pods/{}'

PAUSE_CONTAINER_PREFIX = 'gcr.io/google_containers/pause-'

logger = logging.getLogger('kube_log_watcher')


class PodNotFound(Exception):
    pass


class TimedHTTPClient(pykube.HTTPClient):
    def __init__(self, config, timeout=10):
        self.timeout = timeout
        super().__init__(config)

    def get_kwargs(self, **kwargs):
        """Override parent method to add timeout to all requests"""
        kw = super().get_kwargs(**kwargs)
        kw['timeout'] = self.timeout

        return kw


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
    client = TimedHTTPClient(config)
    client.session.trust_env = False
    client.session.headers["User-Agent"] = "kube-log-watcher/{}".format(kube_log_watcher.__version__)

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
        return pykube.Pod.objects(api=kube_client, namespace=namespace).get_by_name(name)
    except Exception as error:
        if not isinstance(error, pykube.ObjectDoesNotExist):
            logger.error('Failed to get pod: %s', repr(error))
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

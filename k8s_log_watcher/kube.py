import pykube


DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'
DEFAULT_NAMESPACE = 'default'


def get_client():
    config = pykube.KubeConfig.from_service_account(DEFAULT_SERVICE_ACC)
    return pykube.HTTPClient(config)


def get_pods() -> list:
    kube_client = get_client()
    return pykube.Pod.objects(kube_client).filter(namespace=DEFAULT_NAMESPACE)


def get_pod_labels(pods: list, pod_name: str) -> dict:
    for pod in pods:
        if pod.name == pod_name:
            return pod.obj['metadata']['labels']

    return {}

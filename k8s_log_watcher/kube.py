import pykube


DEFAULT_SERVICE_ACC = '/var/run/secrets/kubernetes.io/serviceaccount'

config = pykube.KubeConfig.from_file(DEFAULT_SERVICE_ACC)
kube_client = pykube.HTTPClient(config)


def get_pods() -> list:
    return pykube.Pod.objects(kube_client).filter(namespace='dafault')


def get_pod_labels(pods: list, pod_name: str) -> dict:
    for pod in pods:
        if pod.name == pod_name:
            return pod.obj['metadata']['labels']

    return {}

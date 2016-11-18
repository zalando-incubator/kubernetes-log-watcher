"""
Appdynamics module for providing job file templates and variables required to ship logs to appdynamics controller.
"""


def get_template_path():
    return ''


def get_template_vars(pod_labels):
    return {
        'app_name': pod_labels.get('appdynamics_app'),
        'app_tier': pod_labels.get('appdynamics_tier'),
    }

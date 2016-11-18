import pytest

from k8s_log_watcher.agents.appdynamics import get_template_vars


@pytest.mark.parametrize(
    'labels,res',
    (
        (
            {'appdynamics_app': 'app-1', 'appdynamics_tier': 'tier-1'},
            {'app_name': 'app-1', 'app_tier': 'tier-1'}
        ),
        (
            {'app': 'app-1', 'appdynamics_tier': 'tier-1'},
            {'app_name': None, 'app_tier': 'tier-1'}
        )
    )
)
def test_get_template_vars(monkeypatch, labels, res):
    assert get_template_vars(labels) == res

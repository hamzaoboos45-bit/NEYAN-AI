"""Gate 1: customer Home startup contracts remain deterministic."""
import os


def test_home_runtime_has_one_guarded_startup_and_settled_state_contract():
    source = open(os.path.join("frontend", "static", "js", "home-dashboard.js"), encoding="utf-8").read()
    assert source.count('fetch("/api/dashboard/home")') == 1
    assert "var initialized = false" in source
    assert "if (initialized) return" in source
    assert "if (inFlightLoad) return inFlightLoad" in source
    assert "errorBox.hidden = true" in source
    assert "loading.hidden = false" in source
    assert "loading.hidden = true" in source
    assert "document.addEventListener(\"neyan:languagechange\", render)" in source


def test_home_template_keeps_distinct_loading_error_and_success_regions():
    template = open(os.path.join("frontend", "templates", "home.html"), encoding="utf-8").read()
    assert 'id="homeDashboardError"' in template
    assert 'id="homeDashboardLoading"' in template
    assert 'id="homeDashboardContent" hidden' in template
    assert 'id="homeDashboardRetry"' in template

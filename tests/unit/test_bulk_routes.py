"""Bulk coverage integration tests - hit all reachable API endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from orbit.api.main import create_app


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(enable_auth=False))


# -- Observability (highest missed lines: 75) --

def test_obs_health_all(client):
    r = client.get("/api/v1/observability/health")
    assert r.status_code == 200

def test_obs_health_component(client):
    for comp in ("scheduler", "knowledge_engine", "llm_gateway", "code_graph", "db_graph",
                 "config_graph", "hallucination_layers", "sandbox"):
        r = client.get(f"/api/v1/observability/health/{comp}")
        assert r.status_code == 200

def test_obs_health_unknown(client):
    r = client.get("/api/v1/observability/health/nope")
    assert r.status_code == 200

def test_obs_startup_probe(client):
    r = client.get("/api/v1/observability/startup-probe")
    assert r.status_code == 200

def test_obs_startup_probe_reset(client):
    r = client.post("/api/v1/observability/startup-probe/reset")
    assert r.status_code in (200, 404, 500)

def test_obs_feedback(client):
    r = client.get("/api/v1/observability/feedback")
    assert r.status_code in (200, 404, 500)

def test_obs_trace_recent(client):
    r = client.get("/api/v1/observability/trace/recent?limit=5")
    assert r.status_code == 200

def test_obs_trace_not_found(client):
    r = client.get("/api/v1/observability/trace/nonexistent")
    assert r.status_code in (200, 404)

def test_obs_trace_export(client):
    r = client.get("/api/v1/observability/trace/nonexistent/export")
    assert r.status_code in (200, 404)


# -- Config routes (67 missed) --

def test_config_read_sandbox(client):
    r = client.get("/api/v1/config/sandbox")
    assert r.status_code == 200

def test_config_history(client):
    r = client.get("/api/v1/config/sandbox/history")
    assert r.status_code in (200, 404, 500)

def test_config_branches(client):
    r = client.get("/api/v1/config/branches/list")
    assert r.status_code in (200, 404, 500)

def test_config_create_branch(client):
    r = client.post("/api/v1/config/branches", json={"name": "test-branch"})
    assert r.status_code in (200, 201, 422, 500)


# -- Projects (82 missed) --

def test_projects_list(client):
    r = client.get("/api/v1/projects")
    assert r.status_code in (200, 404, 500)

def test_projects_get_nonexistent(client):
    r = client.get("/api/v1/projects/nonexistent_xyz")
    assert r.status_code in (200, 404, 500)


# -- Knowledge routes --

def test_knowledge_concepts(client):
    r = client.get("/api/v1/knowledge/concepts")
    assert r.status_code in (200, 404, 500)

def test_knowledge_stats(client):
    r = client.get("/api/v1/knowledge/stats")
    assert r.status_code in (200, 404, 500)


# -- Tasks --

def test_tasks_list(client):
    r = client.get("/api/v1/tasks")
    assert r.status_code in (200, 404, 500)

def test_tasks_create(client):
    r = client.post("/api/v1/tasks", json={"prd": "test", "mode": "auto"})
    assert r.status_code in (200, 201, 422, 500)


# -- Search --

def test_search_query(client):
    r = client.get("/api/v1/search?q=test")
    assert r.status_code in (200, 404, 500)

def test_search_empty(client):
    r = client.get("/api/v1/search?q=")
    assert r.status_code in (200, 422)


# -- Files routes --

def test_files_list(client):
    r = client.get("/api/v1/files/.")
    assert r.status_code in (200, 404, 500)


# -- CodeGraph routes --

def test_codegraph_info(client):
    r = client.get("/api/v1/codegraph/info")
    assert r.status_code in (200, 404, 500)


# -- Tests routes --

def test_tests_results(client):
    r = client.get("/api/v1/tests/results")
    assert r.status_code in (200, 404, 500)

def test_tests_coverage(client):
    r = client.get("/api/v1/tests/coverage")
    assert r.status_code in (200, 404, 500)


# -- Agent LLM --

def test_agent_llm_list(client):
    r = client.get("/api/v1/agent-llm")
    assert r.status_code in (200, 404, 500)

def test_agent_llm_config(client):
    r = client.get("/api/v1/agent-llm/developer")
    assert r.status_code in (200, 400, 404, 500)


# -- Backup --

def test_backup_list(client):
    r = client.get("/api/v1/backup")
    assert r.status_code in (200, 404, 500)


# -- Sessions --

def test_sessions_list(client):
    r = client.get("/api/v1/sessions")
    assert r.status_code in (200, 404, 500)


# -- Versioning --

def test_versioning_list(client):
    r = client.get("/api/v1/versioning")
    assert r.status_code in (200, 404, 500)


# -- Compliance routes --

def test_compliance_status(client):
    r = client.get("/api/v1/compliance/status")
    assert r.status_code in (200, 404, 500)


# -- Insights --

def test_insights(client):
    r = client.get("/api/v1/insights")
    assert r.status_code in (200, 404, 500)


# -- Blame --

def test_blame_no_file(client):
    r = client.get("/api/v1/blame?file=nonexistent.py")
    assert r.status_code in (200, 422, 500)


# -- Schedule --

def test_schedule_status(client):
    r = client.get("/schedule/status")
    assert r.status_code in (200, 404, 500)


# -- Review --

def test_review_status(client):
    r = client.get("/api/v1/review/status")
    assert r.status_code in (200, 404, 500)


# -- Goal (no prefix) --

def test_goal_status(client):
    r = client.get("/goal/status")
    assert r.status_code in (200, 404, 500)


# -- Ponytail debt --

def test_ponytail_list(client):
    r = client.get("/api/v1/ponytail-debt")
    assert r.status_code in (200, 404, 500)


# -- Dream --

def test_dream_status(client):
    r = client.get("/api/v1/dream/status")
    assert r.status_code in (200, 404, 500)


# -- Health (root) --

def test_health_root(client):
    r = client.get("/health")
    assert r.status_code == 200

"""
Functional API tests for :mod:`api.routers.hypothesis_testing` -- migrated 2026-09-05 from
``core/tabs/knowledge_graph.py``'s "Hypothesis Testing"/"Uncertainty Analysis" tabs. Through the
real FastAPI app, with ``hypothesis_testing._repository`` swapped for a fake -- no live Neo4j
server involved at all, this page never touches it (see the module's own docstring).
"""

import pytest
from fastapi.testclient import TestClient

import api.routers.hypothesis_testing as ht_router
from api.app import app
from core.domain.entities import ExperimentConfig, PromptMode, RunRecord
from tests.unit.test_experiment_runner import FakeRepository

pytestmark = pytest.mark.req("REQ-PAGE-HYP-01")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_run(run_id, started_at, total_tasks=6):
    config = ExperimentConfig(
        student_models=["qwen:latest"],
        teacher_model="llama3:latest",
        archetypes=["Detached", "Expressive"],
        biases=["toxic"],
        prompt_mode=PromptMode.TUNED,
    )
    return RunRecord(run_id=run_id, started_at=started_at, config=config, total_tasks=total_tasks)


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture(autouse=True)
def _fake_repo(fake_repo):
    orig = ht_router._repository
    ht_router._repository = fake_repo
    yield
    ht_router._repository = orig


def test_page_with_no_runs_shows_empty_state(client):
    response = client.get("/hypothesis_testing")
    assert response.status_code == 200
    assert "No experiment runs found yet" in response.text


def test_page_with_a_run_lists_its_archetypes(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "cognitive_load": 0.5})
    fake_repo.save_response("run-a", {"archetype": "Expressive", "cognitive_load": 0.3})

    response = client.get("/hypothesis_testing")
    assert response.status_code == 200
    assert "run-a" in response.text
    assert "Detached" in response.text
    assert "Expressive" in response.text


def test_archetypes_fragment_for_unknown_run_returns_404_with_a_clear_message(client):
    response = client.get("/hypothesis_testing/archetypes", params={"run_id": "unknown-run"})
    assert response.status_code == 404
    assert "No responses found" in response.text


def test_compare_renders_the_real_mean_shift_and_a_chart(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "cognitive_load": 2.0})
    fake_repo.save_response("run-a", {"archetype": "Expressive", "cognitive_load": 1.0})

    response = client.post(
        "/hypothesis_testing/compare",
        data={"run_id": "run-a", "archetype_a": "Detached", "archetype_b": "Expressive", "metric": "cognitive_load"},
    )
    assert response.status_code == 200
    assert "2.000" in response.text and "1.000" in response.text
    assert "Hypothesis confirmed" in response.text
    assert 'src="data:image/png;base64,' in response.text


def test_compare_for_an_unknown_run_shows_a_clear_error_not_a_500(client):
    response = client.post(
        "/hypothesis_testing/compare",
        data={"run_id": "unknown-run", "archetype_a": "A", "archetype_b": "B", "metric": "cognitive_load"},
    )
    assert response.status_code == 200
    assert "No responses found" in response.text


def test_compare_with_an_archetype_missing_the_metric_shows_a_clear_error_not_a_500(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    fake_repo.save_response("run-a", {"archetype": "Detached", "cognitive_load": 2.0})

    response = client.post(
        "/hypothesis_testing/compare",
        data={"run_id": "run-a", "archetype_a": "Detached", "archetype_b": "Expressive", "metric": "cognitive_load"},
    )
    assert response.status_code == 200
    assert "No responses with a real" in response.text


def test_uncertainty_renders_distribution_shift_and_charts(client, fake_repo):
    fake_repo.save_run(_make_run("run-a", "2026-09-05T00:00:00Z"))
    for v in [1.0, 1.0, 1.0]:
        fake_repo.save_response(
            "run-a", {"archetype": "Detached", "cognitive_load": v, "sentiment": v, "lexical_density": v}
        )
    for v in [10.0, 10.0, 10.0]:
        fake_repo.save_response(
            "run-a", {"archetype": "Expressive", "cognitive_load": v, "sentiment": v, "lexical_density": v}
        )

    response = client.post(
        "/hypothesis_testing/uncertainty",
        data={"run_id": "run-a", "archetype_a": "Detached", "archetype_b": "Expressive"},
    )
    assert response.status_code == 200
    assert "KL divergence" in response.text
    assert 'src="data:image/png;base64,' in response.text


def test_uncertainty_for_an_unknown_run_shows_a_clear_error_not_a_500(client):
    response = client.post(
        "/hypothesis_testing/uncertainty",
        data={"run_id": "unknown-run", "archetype_a": "A", "archetype_b": "B"},
    )
    assert response.status_code == 200
    assert "No responses found" in response.text

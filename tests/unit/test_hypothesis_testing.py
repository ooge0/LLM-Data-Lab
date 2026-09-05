"""
Unit tests for :mod:`core.services.hypothesis_testing` -- migrated 2026-09-05 from
``core/tabs/knowledge_graph.py``'s "Hypothesis Testing"/"Uncertainty Analysis" tabs. Pure
pandas/numpy/scipy, no Neo4j and no live server needed.
"""

import pytest

from core.services.hypothesis_testing import compare_archetype_means, run_uncertainty_analysis

# --- compare_archetype_means --------------------------------------------------------------------


def test_compare_archetype_means_computes_the_real_mean_and_shift():
    responses = [
        {"archetype": "A", "cognitive_load": 1.0},
        {"archetype": "A", "cognitive_load": 2.0},
        {"archetype": "B", "cognitive_load": 1.0},
    ]
    result = compare_archetype_means(responses, "A", "B", "cognitive_load")
    assert result["mean_a"] == 1.5
    assert result["mean_b"] == 1.0
    assert result["relative_shift"] == pytest.approx(0.5)
    assert result["shift_over_50"] is False, "exactly 50% is not over 50%"
    assert result["n_a"] == 2
    assert result["n_b"] == 1


def test_compare_archetype_means_flags_a_real_over_50_percent_shift():
    responses = [{"archetype": "A", "m": 3.0}, {"archetype": "B", "m": 1.0}]
    result = compare_archetype_means(responses, "A", "B", "m")
    assert result["relative_shift"] == 2.0
    assert result["shift_over_50"] is True


def test_compare_archetype_means_relative_shift_is_none_when_mean_b_is_zero():
    """Matches the legacy tab's own explicit division-by-zero guard."""
    responses = [{"archetype": "A", "m": 5.0}, {"archetype": "B", "m": 0.0}]
    result = compare_archetype_means(responses, "A", "B", "m")
    assert result["relative_shift"] is None
    assert result["shift_over_50"] is False


def test_compare_archetype_means_ignores_null_metric_values():
    responses = [
        {"archetype": "A", "m": 1.0},
        {"archetype": "A", "m": None},
        {"archetype": "B", "m": 1.0},
    ]
    result = compare_archetype_means(responses, "A", "B", "m")
    assert result["n_a"] == 1


def test_compare_archetype_means_raises_when_archetype_a_has_no_responses_at_all():
    responses = [{"archetype": "B", "m": 1.0}]
    with pytest.raises(ValueError, match="A"):
        compare_archetype_means(responses, "A", "B", "m")


def test_compare_archetype_means_raises_when_archetype_b_has_only_null_metric_values():
    """Real, deliberate improvement over the legacy tab: a NaN mean would previously just print
    as literal "nan" text -- this now raises a clear, catchable error instead."""
    responses = [{"archetype": "A", "m": 1.0}, {"archetype": "B", "m": None}]
    with pytest.raises(ValueError, match="B"):
        compare_archetype_means(responses, "A", "B", "m")


# --- run_uncertainty_analysis --------------------------------------------------------------------


def _responses(values_a, values_b, metric="m"):
    return [{"archetype": "A", metric: v} for v in values_a] + [{"archetype": "B", metric: v} for v in values_b]


def test_run_uncertainty_analysis_is_deterministic_given_a_seed():
    responses = _responses([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    r1 = run_uncertainty_analysis(responses, "A", "B", ["m"], n_bootstrap=20, seed=42)
    r2 = run_uncertainty_analysis(responses, "A", "B", ["m"], n_bootstrap=20, seed=42)
    assert r1 == r2


def test_run_uncertainty_analysis_returns_one_variance_row_per_archetype_per_metric():
    responses = _responses([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    result = run_uncertainty_analysis(responses, "A", "B", ["m"], seed=0)
    assert len(result["variance_results"]) == 2
    assert {row["archetype"] for row in result["variance_results"]} == {"A", "B"}
    for row in result["variance_results"]:
        assert row["dominant"] in ("Epistemic", "Aleatoric")
        assert row["epistemic"] >= 0
        assert row["aleatoric"] >= 0


def test_run_uncertainty_analysis_computes_a_real_nonnegative_kl_divergence():
    responses = _responses([1.0, 1.0, 1.0], [10.0, 10.0, 10.0])
    result = run_uncertainty_analysis(responses, "A", "B", ["m"], seed=0)
    assert len(result["distribution_shifts"]) == 1
    assert result["distribution_shifts"][0]["metric"] == "m"
    assert result["distribution_shifts"][0]["kl_divergence"] >= 0


def test_run_uncertainty_analysis_skips_an_archetype_with_zero_real_values_for_a_metric():
    """Matches the legacy tab's own `if len(df_arch) == 0: continue` -- one missing metric/archetype
    combination shouldn't raise or block the rest, unlike compare_archetype_means's stricter guard."""
    responses = [{"archetype": "A", "m": 1.0}, {"archetype": "B", "m": None}]
    result = run_uncertainty_analysis(responses, "A", "B", ["m"], seed=0)
    assert all(row["archetype"] != "B" for row in result["variance_results"])
    assert result["distribution_shifts"] == [], "distribution shift needs real values on both sides"

"""
core.services.hypothesis_testing
====================================

Corpus-level archetype-comparison statistics -- migrated 2026-09-05 from
``core/tabs/knowledge_graph.py``'s "Hypothesis Testing" and "Uncertainty Analysis" tabs. Unlike
every other capability that lived in that file, these two never touched Neo4j at all (pure pandas/
numpy/scipy over the already-persisted response corpus) -- CLAUDE.md SS1's Neo4j quarantine never
actually applied to them, they were just trapped behind the same tab's unconditional Neo4j
connection load. Belongs alongside :mod:`core.services.metrics_engine` /
:mod:`core.services.cluster_discovery` (CLAUDE.md SS3b's corpus-level confirmatory analysis), not
:class:`core.domain.interfaces.GraphRepository`.

Both functions raise ``ValueError`` on a genuinely unusable input (an archetype with zero real
values for the chosen metric) rather than silently computing/returning ``NaN`` -- the legacy tab
had no such guard (``f"{mean_A:.3f}"`` on a NaN just prints ``"nan"``); routers catch this and
render a clear message instead of a raw 500, matching this project's established
graceful-degradation precedent (Stage 8's sparse-run guards).
"""

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import entropy


def compare_archetype_means(responses: list[dict], archetype_a: str, archetype_b: str, metric: str) -> dict:
    """
    Compares one metric's mean between two archetypes and flags a >50% relative shift -- ported
    from the legacy tab's "Hypothesis Testing" button, unchanged logic.

    Parameters
    ----------
    responses : list[dict]
        A run's persisted response records.
    archetype_a, archetype_b : str
        The two archetypes to compare.
    metric : str
        Which persisted numeric field to compare (e.g. ``"cognitive_load"``).

    Returns
    -------
    dict
        ``{"archetype_a", "archetype_b", "metric", "mean_a", "mean_b", "n_a", "n_b",
        "relative_shift", "shift_over_50"}``. ``relative_shift`` is ``None`` if ``mean_b`` is 0
        (division by zero, matching the legacy tab's own explicit guard).

    Raises
    ------
    ValueError
        If either archetype has zero responses with a real (non-null) value for ``metric``.
    """
    df = pd.DataFrame(responses)
    values_a = df.loc[df["archetype"] == archetype_a, metric].dropna()
    values_b = df.loc[df["archetype"] == archetype_b, metric].dropna()
    if values_a.empty:
        raise ValueError(f"No responses with a real {metric!r} value for archetype {archetype_a!r}.")
    if values_b.empty:
        raise ValueError(f"No responses with a real {metric!r} value for archetype {archetype_b!r}.")

    mean_a = float(values_a.mean())
    mean_b = float(values_b.mean())
    relative_shift = (mean_a - mean_b) / mean_b if mean_b != 0 else None

    return {
        "archetype_a": archetype_a,
        "archetype_b": archetype_b,
        "metric": metric,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "n_a": int(values_a.size),
        "n_b": int(values_b.size),
        "relative_shift": relative_shift,
        "shift_over_50": relative_shift is not None and relative_shift > 0.5,
    }


def run_uncertainty_analysis(
    responses: list[dict],
    archetype_a: str,
    archetype_b: str,
    metrics: list[str],
    n_bootstrap: int = 50,
    seed: Optional[int] = None,
) -> dict:
    """
    Bootstrap epistemic/aleatoric variance + KL-divergence distribution shift, per metric, between
    two archetypes -- ported from the legacy tab's "Uncertainty Analysis" button, unchanged logic
    (epistemic = variance of the bootstrap mean, i.e. how uncertain the *estimate* is; aleatoric =
    variance of the raw values themselves, i.e. how spread out the *data* is).

    One real, disclosed addition over the legacy version: an optional ``seed`` for the bootstrap
    resampling, so tests can pin exact output -- the legacy tab's ``np.random.choice`` had no seed
    at all. Default (``seed=None``) reproduces the legacy behavior exactly (genuinely random each
    call).

    Parameters
    ----------
    responses : list[dict]
        A run's persisted response records.
    archetype_a, archetype_b : str
        The two archetypes to compare.
    metrics : list[str]
        Which persisted numeric fields to analyze.
    n_bootstrap : int
        Number of bootstrap resamples per (archetype, metric) pair.
    seed : int, optional
        Seed for the bootstrap resampling RNG.

    Returns
    -------
    dict
        ``{"variance_results": list[dict], "distribution_shifts": list[dict]}``.
        Each variance row: ``{"archetype", "metric", "epistemic", "aleatoric", "dominant"}``.
        Each shift row: ``{"metric", "kl_divergence"}``. A metric/archetype pair with zero real
        values is silently skipped (matching the legacy tab's own ``if len(df_arch) == 0: continue``)
        rather than raising -- unlike :func:`compare_archetype_means`, this already aggregates
        across several metrics, so one missing metric shouldn't block the rest.
    """
    df = pd.DataFrame(responses)
    rng = np.random.default_rng(seed)

    variance_results = []
    for metric in metrics:
        for archetype in (archetype_a, archetype_b):
            values = df.loc[df["archetype"] == archetype, metric].dropna().to_numpy()
            if values.size == 0:
                continue
            bootstrap_means = np.array(
                [rng.choice(values, size=values.size, replace=True).mean() for _ in range(n_bootstrap)]
            )
            epistemic_var = float(np.var(bootstrap_means))
            aleatoric_var = float(np.var(values))
            variance_results.append(
                {
                    "archetype": archetype,
                    "metric": metric,
                    "epistemic": epistemic_var,
                    "aleatoric": aleatoric_var,
                    "dominant": "Epistemic" if epistemic_var > aleatoric_var else "Aleatoric",
                }
            )

    distribution_shifts = []
    for metric in metrics:
        values_a = df.loc[df["archetype"] == archetype_a, metric].dropna().to_numpy()
        values_b = df.loc[df["archetype"] == archetype_b, metric].dropna().to_numpy()
        if values_a.size == 0 or values_b.size == 0:
            continue
        combined = np.concatenate([values_a, values_b])
        bins = np.linspace(combined.min(), combined.max(), 20)
        hist_a, _ = np.histogram(values_a, bins=bins, density=True)
        hist_b, _ = np.histogram(values_b, bins=bins, density=True)
        hist_a = hist_a + 1e-9
        hist_b = hist_b + 1e-9
        distribution_shifts.append({"metric": metric, "kl_divergence": float(entropy(hist_a, hist_b))})

    return {"variance_results": variance_results, "distribution_shifts": distribution_shifts}

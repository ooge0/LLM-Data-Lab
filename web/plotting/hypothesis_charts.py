"""
web.plotting.hypothesis_charts
==================================

Matplotlib charts for :mod:`core.services.hypothesis_testing` -- migrated 2026-09-05 from
``core/tabs/knowledge_graph.py``'s "Hypothesis Testing"/"Uncertainty Analysis" tabs (``st.pyplot``
figures there, ``figure_to_img_tag``'s base64-PNG embedding here, matching Stage 10's precedent for
matplotlib-only charts with no Plotly equivalent).

Distribution-shift histograms take ``responses`` directly rather than the service's already-computed
KL-divergence number -- the number is real business logic (:func:`core.services.hypothesis_testing
.run_uncertainty_analysis`, authoritative), the bin edges/counts needed to *draw* the histogram are
a presentation concern, matching how :mod:`web.plotting.cluster_charts` re-reads a result's own
DataFrame columns to build its traces rather than having the service pre-render chart specs.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from web.plotting.mpl_render import figure_to_img_tag


def build_comparison_chart(result: dict) -> str:
    """Bar chart of one metric's mean for two archetypes -- see
    :func:`core.services.hypothesis_testing.compare_archetype_means`."""
    fig, ax = plt.subplots()
    ax.bar(
        [result["archetype_a"], result["archetype_b"]],
        [result["mean_a"], result["mean_b"]],
        color=["#6f9bd8", "#d9a94f"],
    )
    ax.set_ylabel(result["metric"])
    ax.set_title(f"{result['metric']} comparison: {result['archetype_a']} vs {result['archetype_b']}")
    return figure_to_img_tag(fig, alt=f"{result['metric']} comparison chart")


def build_uncertainty_variance_charts(variance_results: list[dict], metrics: list[str]) -> list[str]:
    """One grouped Epistemic-vs-Aleatoric bar chart per metric -- see
    :func:`core.services.hypothesis_testing.run_uncertainty_analysis`."""
    charts = []
    for metric in metrics:
        subset = [r for r in variance_results if r["metric"] == metric]
        if not subset:
            continue
        archetypes = [r["archetype"] for r in subset]
        x = np.arange(len(archetypes))
        width = 0.35
        fig, ax = plt.subplots()
        ax.bar(x - width / 2, [r["epistemic"] for r in subset], width, label="Epistemic")
        ax.bar(x + width / 2, [r["aleatoric"] for r in subset], width, label="Aleatoric")
        ax.set_xticks(x)
        ax.set_xticklabels(archetypes)
        ax.set_ylabel("Variance")
        ax.set_title(f"Uncertainty comparison for {metric}")
        ax.legend()
        charts.append(figure_to_img_tag(fig, alt=f"Uncertainty comparison for {metric}"))
    return charts


def build_distribution_shift_charts(
    responses: list[dict], archetype_a: str, archetype_b: str, metrics: list[str]
) -> list[str]:
    """One overlapping histogram per metric, comparing the two archetypes' real value
    distributions -- the visual counterpart to :func:`core.services.hypothesis_testing
    .run_uncertainty_analysis`'s KL-divergence number."""
    df = pd.DataFrame(responses)
    charts = []
    for metric in metrics:
        values_a = df.loc[df["archetype"] == archetype_a, metric].dropna().to_numpy()
        values_b = df.loc[df["archetype"] == archetype_b, metric].dropna().to_numpy()
        if values_a.size == 0 or values_b.size == 0:
            continue
        combined = np.concatenate([values_a, values_b])
        bins = np.linspace(combined.min(), combined.max(), 20)
        fig, ax = plt.subplots()
        # matplotlib's own stubs declare `bins` narrower than its real runtime API -- an ndarray of
        # bin edges is explicitly documented and works correctly; not a real type error.
        ax.hist(values_a, bins=bins, alpha=0.5, label=archetype_a)  # type: ignore[arg-type]
        ax.hist(values_b, bins=bins, alpha=0.5, label=archetype_b)  # type: ignore[arg-type]
        ax.set_title(f"Distribution comparison for {metric}")
        ax.legend()
        charts.append(figure_to_img_tag(fig, alt=f"Distribution comparison for {metric}"))
    return charts

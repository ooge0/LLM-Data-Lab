"""
PageRank symmetry on the Archetype/Bias co-occurrence graph -- what is actually proven.

docs/source/wiki/07-knowledge-graph-results.rst records a live Neo4j GDS run in which, on a graph with
5 Archetype and 6 Bias nodes and 30 edges, every Archetype scored 1.0496 and every Bias scored 0.8876.
The explanation given there is graph-theoretic: 30 edges across 5 x 6 nodes is a *complete bipartite*
graph, so PageRank is symmetric within each side by necessity.

These tests pin that argument with an independent implementation (networkx) so it does not rest on one
live run: it holds when every archetype co-occurs with every bias at least once (completeness); it does
NOT depend on the counts being balanced for the unweighted graph; and it breaks as soon as a pair is
missing or, in the weighted graph the app now uses, the counts differ. No Neo4j is needed.
"""

import networkx as nx
import pytest

N_ARCHETYPES = 5
N_BIASES = 6
# Recorded live GDS scores from the wiki page; only their ratio is compared (GDS stops after a fixed
# number of iterations, so absolute values depend on convergence, the ratio does not).
LIVE_ARCHETYPE_SCORE = 1.0496
LIVE_BIAS_SCORE = 0.8876


def _graph(weights=None, skip=()):
    """Build the Archetype x Bias co-occurrence graph, optionally weighted and/or missing some pairs."""
    g = nx.Graph()
    for a in range(N_ARCHETYPES):
        for b in range(N_BIASES):
            if (a, b) in skip:
                continue
            w = 1.0 if weights is None else weights.get((a, b), 1.0)
            g.add_edge(f"A{a}", f"B{b}", weight=w)
    return g


def _spread(scores, prefix):
    """Largest minus smallest PageRank score among the nodes whose name starts with ``prefix``."""
    values = [v for k, v in scores.items() if k.startswith(prefix)]
    return max(values) - min(values)


def _pagerank(g, weighted):
    return nx.pagerank(g, alpha=0.85, tol=1e-12, max_iter=1000, weight="weight" if weighted else None)


def test_complete_bipartite_unweighted_scores_are_uniform_within_each_side():
    """In the complete bipartite graph K(5,6) every Archetype scores the same, and so does every Bias."""
    scores = _pagerank(_graph(), weighted=False)
    assert _spread(scores, "A") == pytest.approx(0.0, abs=1e-9)
    assert _spread(scores, "B") == pytest.approx(0.0, abs=1e-9)


def test_unweighted_uniformity_does_not_depend_on_balanced_counts():
    """Completeness alone forces uniformity: the unweighted graph ignores how often each pair co-occurred."""
    skewed_counts = {(0, 0): 40.0, (1, 2): 7.0}
    scores = _pagerank(_graph(weights=skewed_counts), weighted=False)
    assert _spread(scores, "A") == pytest.approx(0.0, abs=1e-9)
    assert _spread(scores, "B") == pytest.approx(0.0, abs=1e-9)


def test_smaller_side_scores_higher_and_ratio_matches_the_recorded_live_gds_run():
    """The 5-node Archetype side outscores the 6-node Bias side by the same ratio the live GDS run recorded."""
    scores = _pagerank(_graph(), weighted=False)
    ratio = scores["A0"] / scores["B0"]
    assert ratio > 1.0
    assert ratio == pytest.approx(LIVE_ARCHETYPE_SCORE / LIVE_BIAS_SCORE, abs=1e-3)


def test_missing_pair_breaks_the_symmetry():
    """Remove one co-occurrence and the graph is no longer complete: scores now differ within a side."""
    scores = _pagerank(_graph(skip={(0, 0)}), weighted=False)
    assert _spread(scores, "A") > 1e-4
    assert _spread(scores, "B") > 1e-4


def test_weighted_scores_differ_within_a_side_when_counts_are_unequal():
    """The weighted graph (what the app uses now) is only informative if co-occurrence counts vary."""
    scores = _pagerank(_graph(weights={(0, 0): 5.0}), weighted=True)
    assert _spread(scores, "A") > 1e-4
    assert _spread(scores, "B") > 1e-4


def test_weighted_scores_are_uniform_again_when_all_counts_are_equal():
    """Perfectly balanced counts bring the uniformity back: balance matters for the weighted graph only."""
    equal = {(a, b): 3.0 for a in range(N_ARCHETYPES) for b in range(N_BIASES)}
    scores = _pagerank(_graph(weights=equal), weighted=True)
    assert _spread(scores, "A") == pytest.approx(0.0, abs=1e-9)
    assert _spread(scores, "B") == pytest.approx(0.0, abs=1e-9)

"""
web.plotting.knowledge_graph_charts
=======================================

Builds the interactive Archetype/Bias network diagram -- migrated 2026-09-05 from
``core/tabs/knowledge_graph.py``'s PageRank script-3 (pyvis + NetworkX), which built the same
diagram inside a Streamlit tab via ``st.iframe(open(path).read())`` after writing it to
``results/graph_data/experimentGraph.html`` first. This version returns the HTML string directly
(``pyvis.network.Network.generate_html``) instead of round-tripping through a file on disk --
:mod:`api.routers.knowledge_graph` serves it straight from a route, no intermediate artifact to go
stale.

Uses ``cdn_resources="in_line"`` -- every script/style pyvis needs is embedded directly in the
returned HTML string, matching this project's established "vendor everything, no live CDN
dependency" convention (``web/static/vendor/htmx``/``plotly.min.js``) for a library that isn't
otherwise vendored as a static file.
"""

from pyvis.network import Network


def build_archetype_bias_network_html(graph_data: dict) -> str:
    """
    Renders :meth:`core.domain.interfaces.GraphRepository.archetype_bias_graph_data`'s node/edge
    data as a self-contained, interactive pyvis network diagram.

    Parameters
    ----------
    graph_data : dict
        ``{"nodes": list[dict], "edges": list[dict]}`` -- see
        :meth:`~core.domain.interfaces.GraphRepository.archetype_bias_graph_data`.

    Returns
    -------
    str
        A complete, self-contained HTML document (no external requests needed to render it).
    """
    net = Network(height="600px", width="100%", notebook=False, cdn_resources="in_line")
    colors = {"Archetype": "#6f9bd8", "Bias": "#d9a94f"}
    for node in graph_data["nodes"]:
        net.add_node(node["name"], label=node["name"], color=colors.get(node["node_type"], "#8b8d98"))
    for edge in graph_data["edges"]:
        net.add_edge(edge["source"], edge["target"], value=edge["weight"], title=f"weight: {edge['weight']}")
    net.show_buttons(filter_=["physics"])
    return net.generate_html(notebook=False)

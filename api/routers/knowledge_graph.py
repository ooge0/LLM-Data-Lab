"""
api.routers.knowledge_graph
==============================

Wires :class:`core.adapters.neo4j_repo.Neo4jGraphRepo` (the failure-mode/cascade-lineage graph) to
a real page + real endpoints -- promoted 2026-09-05 from the legacy Neo4j subsystem
(``core/tabs/knowledge_graph.py``) into the layered architecture, by explicit author decision (see
:class:`core.domain.interfaces.GraphRepository`'s own docstring for the exact scope of that
decision). This covers the failure-mode graph, its 3 root-cause queries, Stages 4/5 of
``docs/source/wiki/08-graph-representation-learning.rst`` (Leiden community detection,
node-similarity analogy/anomaly), and (2026-09-05, later still) the plain Archetype/Bias
co-occurrence graph + PageRank -- the full remaining Neo4j-touching part of the legacy
``core/tabs/knowledge_graph.py``, migrated and fixed (see
:meth:`core.domain.interfaces.GraphRepository.archetype_bias_pagerank`'s own docstring for the two
real bugs found in the original PageRank scripts). Hypothesis Testing / Uncertainty Analysis --
pure pandas/scipy, never touched Neo4j -- moved separately to ``api/routers/hypothesis_testing.py``,
not here. ``run_knowledge_graph.py``/``core/tabs/knowledge_graph.py`` are retired entirely as of
this migration -- there is no longer a separate Streamlit entry point for any of this.

Every endpoint here degrades to a clear inline error rather than a raw 500 when Neo4j isn't
reachable -- this app's other pages don't depend on Neo4j at all, and this one shouldn't take the
whole request down just because the graph database happens to be offline.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.adapters.neo4j_repo import Neo4jGraphRepo
from web.plotting.knowledge_graph_charts import build_archetype_bias_network_html

router = APIRouter(prefix="/knowledge_graph", tags=["knowledge_graph"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()
_graph_repo = Neo4jGraphRepo()


@router.get("", response_class=HTMLResponse)
def knowledge_graph_page(request: Request) -> HTMLResponse:
    """Render the run picker (for syncing) plus the most recently started run's archetype list
    (for the terminal-stage query's dropdown) -- the three root-cause queries themselves are
    corpus-wide (every run ever synced), not scoped to the selected run."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    archetypes: list[str] = []
    if selected_run_id:
        responses = _repository.load_responses(selected_run_id)
        archetypes = sorted({r["archetype"] for r in responses if r.get("archetype")})
    return templates.TemplateResponse(
        request,
        "knowledge_graph.html",
        {"runs": runs, "selected_run_id": selected_run_id, "archetypes": archetypes},
    )


@router.post("/sync", response_class=HTMLResponse)
def sync_failure_mode_graph(request: Request, run_id: str) -> HTMLResponse:
    """Sync one run's responses into the failure-mode graph, returning a small status fragment."""
    try:
        responses = _repository.load_responses(run_id)
        if not responses:
            logger.warning(f"knowledge_graph sync requested for run {run_id!r} but it has no persisted responses")
            return templates.TemplateResponse(
                request, "_knowledge_graph_status.html", {"error": f"No responses found for run {run_id}."}
            )
        count = _graph_repo.sync_failure_mode_graph(run_id, responses)
        logger.info(f"Synced {count} response(s) for run {run_id!r} into the failure-mode graph")
        return templates.TemplateResponse(
            request,
            "_knowledge_graph_status.html",
            {"message": f"Failure-mode graph synced! {count} response(s) processed."},
        )
    except Exception as exc:
        logger.error(f"Failed to sync run {run_id!r} into the failure-mode graph: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error syncing failure-mode graph: {exc}"}
        )


@router.get("/echo_by_model", response_class=HTMLResponse)
def echo_by_model(request: Request) -> HTMLResponse:
    """Root-cause query 1: which models are most linked to Layer-1 echo rejections."""
    try:
        rows = _graph_repo.echo_rejections_by_model()
        return templates.TemplateResponse(
            request, "_knowledge_graph_table.html", {"title": "Echo rejections by model", "rows": rows}
        )
    except Exception as exc:
        logger.error(f"echo_rejections_by_model query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/terminal_stage", response_class=HTMLResponse)
def terminal_stage(request: Request, archetype: str) -> HTMLResponse:
    """Root-cause query 2: for one archetype, where does the cascade chain actually terminate."""
    try:
        rows = _graph_repo.terminal_stage_by_archetype(archetype)
        return templates.TemplateResponse(
            request,
            "_knowledge_graph_table.html",
            {"title": f"Terminal cascade stage for {archetype}", "rows": rows},
        )
    except Exception as exc:
        logger.error(f"terminal_stage_by_archetype({archetype!r}) query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/rag_chunks_echo", response_class=HTMLResponse)
def rag_chunks_echo(request: Request) -> HTMLResponse:
    """Root-cause query 3: which RAG knowledge categories precede echo rejections."""
    try:
        rows = _graph_repo.rag_chunks_linked_to_echo()
        return templates.TemplateResponse(
            request, "_knowledge_graph_table.html", {"title": "RAG knowledge categories linked to echo", "rows": rows}
        )
    except Exception as exc:
        logger.error(f"rag_chunks_linked_to_echo query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/behavioral_communities", response_class=HTMLResponse)
def behavioral_communities(request: Request) -> HTMLResponse:
    """Stage 4 (docs/source/wiki/08-graph-representation-learning.rst): Leiden community
    detection over Archetype/Bias/Model/CascadeOutcome, unlike the 3 root-cause queries above,
    this surfaces structure nobody wrote a query for in advance."""
    try:
        result = _graph_repo.behavioral_communities()
        return templates.TemplateResponse(request, "_knowledge_graph_communities.html", result)
    except Exception as exc:
        logger.error(f"behavioral_communities query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/structural_similarity", response_class=HTMLResponse)
def structural_similarity(request: Request) -> HTMLResponse:
    """Stage 5 (docs/source/wiki/08-graph-representation-learning.rst): analogy/anomaly detection
    via gds.knn over the same FastRP embeddings Stage 4 introduced."""
    try:
        result = _graph_repo.structural_similarity()
        return templates.TemplateResponse(request, "_knowledge_graph_similarity.html", result)
    except Exception as exc:
        logger.error(f"structural_similarity query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/archetype_bias_pagerank", response_class=HTMLResponse)
def archetype_bias_pagerank(request: Request) -> HTMLResponse:
    """Migrated from core/tabs/knowledge_graph.py's PageRank scripts 1/4, fixed (weighted
    projection, not the two originals' zero-edge/uniform-score bugs) rather than ported as-is."""
    try:
        rows = _graph_repo.archetype_bias_pagerank()
        return templates.TemplateResponse(
            request, "_knowledge_graph_table.html", {"title": "Archetype/Bias PageRank", "rows": rows}
        )
    except Exception as exc:
        logger.error(f"archetype_bias_pagerank query failed: {exc}")
        return templates.TemplateResponse(
            request, "_knowledge_graph_status.html", {"error": f"Error running query: {exc}"}
        )


@router.get("/archetype_bias_network", response_class=HTMLResponse)
def archetype_bias_network(request: Request) -> HTMLResponse:
    """Migrated from PageRank script-3's pyvis/NetworkX diagram. Returns a complete, self-contained
    HTML document (not wrapped in the app shell) -- knowledge_graph.html embeds it via an iframe."""
    try:
        data = _graph_repo.archetype_bias_graph_data()
        return HTMLResponse(build_archetype_bias_network_html(data))
    except Exception as exc:
        logger.error(f"archetype_bias_graph_data query failed: {exc}")
        return HTMLResponse(f"<p>Error building network visualization: {exc}</p>")

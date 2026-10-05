"""
api.routers.hypothesis_testing
==================================

Archetype-comparison statistics -- migrated 2026-09-05 from ``core/tabs/knowledge_graph.py``'s
"Hypothesis Testing" and "Uncertainty Analysis" tabs. Both are pure pandas/numpy/scipy over one
run's already-persisted responses -- they never touched Neo4j (see
:mod:`core.services.hypothesis_testing`'s own docstring), so unlike the rest of that legacy file
this doesn't go anywhere near :class:`core.domain.interfaces.GraphRepository`; it's a plain
corpus-level analysis page, matching ``/model_evo``/``/benchmark``.

Metric choices (``cognitive_load``, ``sentiment``, ``lexical_density``) are the legacy tab's own
fixed list, confirmed to still exist as real persisted fields (checked directly against a live
response record, not assumed) -- unlike ``dimension``/``category``/``severity``/``bias_type``,
which PageRank script-2 referenced and which do **not** exist in current data (see
:meth:`core.domain.interfaces.GraphRepository.archetype_bias_pagerank`'s own docstring for that
finding; script-2 itself was not ported forward for this reason).
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR
from core.adapters.jsonl_store import JSONLStore
from core.services.hypothesis_testing import compare_archetype_means, run_uncertainty_analysis
from web.plotting.hypothesis_charts import (
    build_comparison_chart,
    build_distribution_shift_charts,
    build_uncertainty_variance_charts,
)
from web.plotting.mpl_render import set_chart_theme

router = APIRouter(prefix="/hypothesis_testing", tags=["hypothesis_testing"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_repository = JSONLStore()
_METRICS = ["cognitive_load", "sentiment", "lexical_density"]


def _archetypes_context(run_id: str) -> dict:
    responses = _repository.load_responses(run_id)
    if not responses:
        return {"selected_run_id": run_id, "has_data": False}
    archetypes = sorted({r["archetype"] for r in responses if r.get("archetype")})
    return {"selected_run_id": run_id, "has_data": True, "archetypes": archetypes, "metrics": _METRICS}


@router.get("", response_class=HTMLResponse)
def hypothesis_testing_page(request: Request) -> HTMLResponse:
    """Render the run picker plus the most recently started run's archetype/metric selectors."""
    runs = _repository.list_runs()
    selected_run_id = runs[0].run_id if runs else None
    context = {"runs": runs, "selected_run_id": None, "has_data": False}
    if selected_run_id:
        context.update(_archetypes_context(selected_run_id))
        context["runs"] = runs
    return templates.TemplateResponse(request, "hypothesis_testing.html", context)


@router.get("/archetypes", response_class=HTMLResponse)
def hypothesis_testing_archetypes(request: Request, run_id: str) -> HTMLResponse:
    """Return the ``#hypothesis-archetypes`` fragment for one run -- used by the picker's htmx swap."""
    context = _archetypes_context(run_id)
    status_code = 200 if context["has_data"] else 404
    return templates.TemplateResponse(request, "_hypothesis_archetypes.html", context, status_code=status_code)


@router.post("/compare", response_class=HTMLResponse)
async def hypothesis_testing_compare(request: Request) -> HTMLResponse:
    """Mean-shift comparison (>50% relative shift flag) for one run/archetype-pair/metric."""
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    form = await request.form()
    run_id = str(form.get("run_id", ""))
    archetype_a = str(form.get("archetype_a", ""))
    archetype_b = str(form.get("archetype_b", ""))
    metric = str(form.get("metric", ""))

    responses = _repository.load_responses(run_id)
    if not responses:
        return templates.TemplateResponse(
            request, "_hypothesis_comparison_result.html", {"error": f"No responses found for run {run_id}."}
        )
    try:
        result = compare_archetype_means(responses, archetype_a, archetype_b, metric)
        chart = build_comparison_chart(result)
        return templates.TemplateResponse(
            request, "_hypothesis_comparison_result.html", {"result": result, "chart": chart}
        )
    except ValueError as exc:
        return templates.TemplateResponse(request, "_hypothesis_comparison_result.html", {"error": str(exc)})


@router.post("/uncertainty", response_class=HTMLResponse)
async def hypothesis_testing_uncertainty(request: Request) -> HTMLResponse:
    """Bootstrap epistemic/aleatoric variance + KL-divergence distribution shift, across every
    metric, for one run/archetype-pair."""
    set_chart_theme(request.cookies.get("nn_lab_theme", "dark"))
    form = await request.form()
    run_id = str(form.get("run_id", ""))
    archetype_a = str(form.get("archetype_a", ""))
    archetype_b = str(form.get("archetype_b", ""))

    responses = _repository.load_responses(run_id)
    if not responses:
        return templates.TemplateResponse(
            request, "_hypothesis_uncertainty_result.html", {"error": f"No responses found for run {run_id}."}
        )

    analysis = run_uncertainty_analysis(responses, archetype_a, archetype_b, _METRICS)
    variance_charts = build_uncertainty_variance_charts(analysis["variance_results"], _METRICS)
    shift_charts = build_distribution_shift_charts(responses, archetype_a, archetype_b, _METRICS)
    return templates.TemplateResponse(
        request,
        "_hypothesis_uncertainty_result.html",
        {
            "distribution_shifts": analysis["distribution_shifts"],
            "variance_charts": variance_charts,
            "shift_charts": shift_charts,
        },
    )

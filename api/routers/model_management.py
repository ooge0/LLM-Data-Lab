"""
api.routers.model_management
==============================

Model management: list installed Ollama models, pull new ones with live progress,
and delete models.  This is the FastAPI port of the ``tab_monitor`` Ollama management
block from the legacy Streamlit app (``legacy/streamlit_app.py:3186-3387``), which
was explicitly excluded from ``api/routers/monitor.py`` (see that module's docstring)
due to its "different risk profile" (subprocess execution, destructive delete).

The FastAPI version replaces the legacy ``subprocess.Popen(["ollama", "pull", ...]``
and fake animated progress bar with a real SSE stream from
``ollama.Client().pull(name, stream=True)``, which yields actual progress dicts from
the Ollama daemon.  Delete still uses ``ollama.Client().delete()`` directly.

All Ollama calls use ``ollama.Client()`` directly, NOT ``OllamaClient`` -- that
wrapper only has ``generate()``, while this module needs pull/list/delete.
"""

import asyncio
import json
from typing import AsyncGenerator

import ollama
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from api._paths import TEMPLATES_DIR

router = APIRouter(prefix="/models", tags=["model_management"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _get_installed_models() -> list[dict]:
    """Return installed models as a list of dicts with name, size_gb, family."""
    try:
        result = ollama.Client().list()
        models = []
        for m in result.models:
            size_gb = round(m.size / 1_073_741_824, 2) if m.size else None
            family = (m.details.family if m.details and m.details.family else None) or ""
            models.append(
                {
                    "name": m.model,
                    "size_gb": size_gb,
                    "family": family,
                }
            )
        return sorted(models, key=lambda x: x["name"])
    except Exception as exc:
        return [{"name": f"Error: {exc}", "size_gb": None, "family": ""}]


@router.get("", response_class=HTMLResponse)
async def model_management_page(request: Request) -> HTMLResponse:
    """Full model management page: installed models table + pull form."""
    return templates.TemplateResponse(request, "model_management.html", {})


@router.get("/list", response_class=HTMLResponse)
async def models_list_fragment(request: Request) -> HTMLResponse:
    """HTMX fragment: installed model table, refreshed on load and after pull/delete."""
    models = _get_installed_models()
    return templates.TemplateResponse(
        request,
        "_models_table.html",
        {"models": models},
    )


@router.get("/pull/stream")
async def models_pull_stream(model: str = "") -> JSONResponse:
    """
    SSE endpoint: streams pull progress from ``ollama.Client().pull(name, stream=True)``.

    Each progress dict from the ollama library is forwarded as a ``data:`` line.
    A final ``event: done`` line is sent when the pull completes or on error.
    The client-side EventSource listens for the ``done`` event to close the connection.
    """
    if not model.strip():
        return JSONResponse({"error": "model name required"}, status_code=400)

    async def _generate() -> AsyncGenerator[bytes, None]:
        # ollama.pull with stream=True is a synchronous generator that yields progress
        # dicts as the download proceeds.  We run the full pull in a thread-pool executor
        # so it doesn't block the event loop, collecting all progress events into a list
        # first, then yielding them.  True per-event streaming would require a separate
        # thread with a queue bridge (same pattern as ExperimentRunner + _sse.py); for a
        # model download that progress is coarse-grained enough that batch-yield is fine.
        try:
            loop = asyncio.get_event_loop()

            def _run_pull() -> list:
                events = []
                for progress in ollama.Client().pull(model.strip(), stream=True):
                    events.append(progress)
                return events

            events = await loop.run_in_executor(None, _run_pull)
            for progress in events:
                payload = json.dumps(
                    {
                        "status": getattr(progress, "status", str(progress)),
                        "completed": getattr(progress, "completed", None),
                        "total": getattr(progress, "total", None),
                    }
                )
                yield f"data: {payload}\n\n".encode()
        except Exception as exc:
            payload = json.dumps({"error": str(exc)})
            yield f"data: {payload}\n\n".encode()
            yield b"event: done\ndata: \n\n"
            return
        yield b"event: done\ndata: \n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/delete")
async def models_delete(model: str = "") -> JSONResponse:
    """
    Delete an installed Ollama model.

    Uses ``ollama.Client().delete()`` directly (the Python library call, same as
    the legacy Streamlit tab).  Returns 204 on success, 400/500 on error.
    """
    if not model.strip():
        return JSONResponse({"error": "model name required"}, status_code=400)
    try:
        ollama.Client().delete(model.strip())
        return JSONResponse({}, status_code=204)
    except ollama.ResponseError as exc:
        return JSONResponse({"error": str(exc)}, status_code=exc.status_code or 500)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

"""
api.routers.model_probe
========================

Interactive model probe for the fuzzing workflow: send a raw prompt to any locally
available Ollama model and immediately see the raw response + Layer 0 classification
(and Layer 1 echo score when a bias text is provided).

This is the web-UI companion to ``tests/unit/test_model_fuzz_catalog.py``:
the catalog records confirmed failure modes; this page is where you discover them
interactively before adding them to the catalog.

The ``POST /model_probe/run`` endpoint is also a clean API endpoint -- the JSON
response shape is stable enough to drive scripted probing sessions.
"""

import time

import ollama
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from api._paths import TEMPLATES_DIR
from core.adapters.ollama_client import OllamaClient
from core.adapters.structured_judge import _SYSTEM_PROMPT as _JUDGE_SYSTEM_PROMPT
from core.analysis.response_classification import classify_response, is_echo_response

router = APIRouter(prefix="/model_probe", tags=["model_probe"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_DEFAULT_SYSTEM_PROMPT = (
    'Respond ONLY with a JSON object in exactly this shape and no other text: {"text": "<your response here>"}.'
)

_client = OllamaClient()


def _available_models() -> list[str]:
    """Return model names from the local Ollama instance, sorted."""
    try:
        return sorted(m.model for m in ollama.Client().list().models)
    except Exception:
        return []


class ProbeRequest(BaseModel):
    model: str
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    user_prompt: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=1, le=4096)
    bias_text: str = ""


@router.get("", response_class=HTMLResponse)
async def model_probe_page(request: Request) -> HTMLResponse:
    """Full model probe page: form + result panel."""
    models = _available_models()
    return templates.TemplateResponse(
        request,
        "model_probe.html",
        {
            "models": models,
            "default_system_prompt": _DEFAULT_SYSTEM_PROMPT,
            "judge_system_prompt": _JUDGE_SYSTEM_PROMPT,
        },
    )


@router.post("/run", response_class=HTMLResponse)
async def model_probe_run(request: Request) -> HTMLResponse:
    """
    Run one probe: call the model, classify the response, return the result fragment.

    Accepts ``application/x-www-form-urlencoded`` from the HTMX form POST.
    Returns the ``_probe_result.html`` fragment.
    """
    form = await request.form()
    model = str(form.get("model", "")).strip()
    system_prompt = str(form.get("system_prompt", _DEFAULT_SYSTEM_PROMPT)).strip()
    user_prompt = str(form.get("user_prompt", "")).strip()
    bias_text = str(form.get("bias_text", "")).strip()
    try:
        temperature = float(form.get("temperature", 0.7))
    except (ValueError, TypeError):
        temperature = 0.7
    try:
        max_tokens = int(form.get("max_tokens", 256))
    except (ValueError, TypeError):
        max_tokens = 256

    if not model or not user_prompt:
        return templates.TemplateResponse(
            request,
            "_probe_result.html",
            {"error": "Model and user prompt are required."},
        )

    t0 = time.monotonic()
    try:
        result = _client.generate(
            model,
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        raw_text = result.text or ""
        api_error = None
    except Exception as exc:
        raw_text = ""
        api_error = str(exc)

    elapsed_ms = round((time.monotonic() - t0) * 1000)

    classification = classify_response(raw_text) if not api_error else None
    classification_name = classification.value if classification is not None else "API_ERROR"

    # Layer 1 echo score -- only meaningful when bias_text is provided
    layer1_echo_score: float | None = None
    layer1_echo_detected: bool = False
    if bias_text and raw_text and not api_error:
        try:
            from core.analysis.calculate_advanced_linguistic_metrics import _semantic_similarity

            overlap = _semantic_similarity(bias_text, raw_text)
            layer1_echo_score = round(overlap, 4)
            layer1_echo_detected = is_echo_response(overlap)
        except Exception:
            pass

    return templates.TemplateResponse(
        request,
        "_probe_result.html",
        {
            "model": model,
            "raw_text": raw_text,
            "api_error": api_error,
            "classification": classification_name,
            "layer1_echo_score": layer1_echo_score,
            "layer1_echo_detected": layer1_echo_detected,
            "elapsed_ms": elapsed_ms,
            "user_prompt": user_prompt,
        },
    )


@router.post("/run/json")
async def model_probe_run_json(body: ProbeRequest) -> JSONResponse:
    """
    JSON API endpoint for the same probe: accepts JSON body, returns JSON result.

    Useful for scripted probing sessions or connecting external tooling.
    """
    t0 = time.monotonic()
    try:
        result = _client.generate(
            body.model,
            body.system_prompt,
            body.user_prompt,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            json_mode=True,
        )
        raw_text = result.text or ""
        api_error = None
    except Exception as exc:
        raw_text = ""
        api_error = str(exc)

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    classification = classify_response(raw_text) if not api_error else None
    classification_name = classification.value if classification is not None else "API_ERROR"

    layer1_echo_score: float | None = None
    layer1_echo_detected: bool = False
    if body.bias_text and raw_text and not api_error:
        try:
            from core.analysis.calculate_advanced_linguistic_metrics import _semantic_similarity

            overlap = _semantic_similarity(body.bias_text, raw_text)
            layer1_echo_score = round(overlap, 4)
            layer1_echo_detected = is_echo_response(overlap)
        except Exception:
            pass

    return JSONResponse(
        {
            "model": body.model,
            "classification": classification_name,
            "raw_text": raw_text,
            "layer1_echo_score": layer1_echo_score,
            "layer1_echo_detected": layer1_echo_detected,
            "elapsed_ms": elapsed_ms,
            "api_error": api_error,
        }
    )

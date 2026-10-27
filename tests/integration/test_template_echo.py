"""
Template-echo regression test -- every locally installed Ollama model, requires Ollama running.

The smoke probe's own example placeholder (``{"text": "<one sentence here>"}``) makes qwen echo it
back (20/20 in the 2026-10-27 prompt-echo experiment; the concrete-example and no-example variants
gave 0/20). So the placeholder in the prompt, not the model, drives that echo. This test checks the
other direction: with a control prompt that has no placeholder, no installed model may return a
catalogued template echo.

Models come from what Ollama reports as installed, not from a fixed list, so a newly pulled model is
tested without editing this file. Starts with the models already downloaded; more test datasets
(unique prompts per model) are a planned extension, not part of this test yet.
"""

import json

import ollama
import pytest

from core.adapters.ollama_client import OllamaClient, _native_host
from utils import config_loader_short

# Control prompt: same instruction shape as the smoke probe, but the example is a real value,
# not a placeholder. Variant B in the 2026-10-27 experiment (0 echoes for qwen).
_CONTROL_SYSTEM_PROMPT = (
    "You are a cooperative assistant. "
    'Respond ONLY with a JSON object in exactly this shape and no other text: {"text": "The sky is blue."}.'
)
_USER_PROMPT = "Write one sentence describing the color blue."
_REPS = 5

# Placeholders recorded in tests/unit/test_model_fuzz_catalog.py.
_KNOWN_TEMPLATE_ECHOES = {"<one sentence here>", "<rewritten output>"}


def _installed_models() -> list[str]:
    """Names of the models Ollama reports as installed; empty when Ollama is unreachable."""
    try:
        host = _native_host(config_loader_short.OPENAI_BASE_URL)
        return [m.model for m in ollama.Client(host=host).list().models]
    except Exception:
        return []


_MODELS = _installed_models()


def _echoed_placeholder(raw: str):
    try:
        text = json.loads(raw).get("text")
    except (ValueError, AttributeError):
        return None
    return text if text in _KNOWN_TEMPLATE_ECHOES else None


@pytest.mark.parametrize("model", _MODELS or ["<no-ollama>"])
@pytest.mark.req("REQ-CASC-L0-04")
def test_installed_model_does_not_echo_a_template_with_a_control_prompt(model):
    """No response to a placeholder-free control prompt may be a catalogued template echo.

    Failures show every echoed response, so the model and text are visible in the report.
    A model that echoes here would be a model property, not a prompt effect.
    """
    if model == "<no-ollama>":
        pytest.skip("Ollama is not reachable -- no installed models to test")

    client = OllamaClient()
    echoes = []
    for _ in range(_REPS):
        raw = client.generate(
            model,
            _CONTROL_SYSTEM_PROMPT,
            _USER_PROMPT,
            json_mode=True,
            max_tokens=128,
            temperature=0.1,
        ).text
        placeholder = _echoed_placeholder(raw)
        if placeholder is not None:
            echoes.append(raw)

    assert not echoes, (
        f"Model {model!r} echoed a catalogued template in {len(echoes)}/{_REPS} control runs "
        f"with a placeholder-free prompt: {echoes!r}. Record it in tests/unit/test_model_fuzz_catalog.py."
    )

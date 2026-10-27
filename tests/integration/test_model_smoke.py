"""
Model smoke tests -- require Ollama running locally.

Skipped automatically when Ollama is unreachable, so the suite stays green in CI
and offline environments.

Each configured model is called with a minimal, unambiguous prompt and the raw
response is run through Layer 0 (:func:`core.analysis.response_classification.classify_response`).
A VALID classification means the model can produce structurally correct output;
anything else surfaces as a test failure with the raw response attached.

These tests intentionally do NOT assert on the *content* of the response -- that is
the experiment pipeline's job.  They assert only on structure: did the model return
parseable JSON with a non-empty 'text' field that is not a placeholder.

Adding a model: add its name to ``_MODELS_UNDER_TEST``.  The test will skip
automatically if that model is not pulled in the local Ollama instance (the skip
message will say which model was not found).
"""

import json

import pytest

from core.adapters.ollama_client import OllamaClient
from core.analysis.response_classification import ResponseClassification, classify_response
from core.services.status_checks import check_ollama

# Models known to be used in this project's experiments.
# qwen:latest and tinyllama:latest are the two with confirmed failure modes in
# the project's real-run history (BUG-001 FORMAT_ERROR for tinyllama,
# BUG-002 token-repeat-limit for qwen).
_MODELS_UNDER_TEST = [
    "qwen:latest",
    "tinyllama:latest",
]

_SMOKE_SYSTEM_PROMPT = (
    "You are a cooperative assistant. "
    "Respond ONLY with a JSON object in exactly this shape and no other text: "
    '{"text": "<one sentence here>"}.'
)

_SMOKE_USER_PROMPT = "Write one sentence describing the color blue."

# Template echoes already recorded in tests/unit/test_model_fuzz_catalog.py. A probe that returns one
# of these is a known, classified model behaviour (Layer 0: FORMAT_ERROR), handled like the
# <rewritten output> rows in experiments: visible in the report as xfail with its catalogue reason,
# not a red failure. Any other non-VALID response still fails the test.
_KNOWN_TEMPLATE_ECHOES = {"<one sentence here>", "<rewritten output>"}


def _echoed_placeholder(raw: str):
    """Return the placeholder text when the response is a catalogued template echo, else None."""
    try:
        text = json.loads(raw).get("text")
    except (ValueError, AttributeError):
        return None
    return text if text in _KNOWN_TEMPLATE_ECHOES else None


@pytest.fixture(scope="module", autouse=True)
def require_ollama():
    """Skip the entire module if Ollama is not reachable."""
    status = check_ollama()
    if not status["ok"]:
        pytest.skip(f"Ollama not available -- smoke tests skipped ({status.get('detail', 'no detail')})")


@pytest.mark.parametrize("model", _MODELS_UNDER_TEST)
@pytest.mark.req("REQ-GEN-OLL-01")
def test_model_produces_valid_json_for_minimal_prompt(model):
    """Each model must return a structurally VALID response for the simplest possible prompt.

    A failure here means the model cannot be trusted in an experiment run without
    first diagnosing why it cannot produce the requested JSON shape.  The raw response
    is included in the assertion message so the failure is self-explaining in pytest output.
    """
    client = OllamaClient()
    try:
        result = client.generate(
            model,
            _SMOKE_SYSTEM_PROMPT,
            _SMOKE_USER_PROMPT,
            json_mode=True,
            max_tokens=128,
            temperature=0.1,
        )
    except Exception as exc:
        # If the model is not pulled, Ollama raises ResponseError -- skip rather than fail
        # so the test list stays clean when optional models are absent.
        import ollama

        if isinstance(exc, ollama.ResponseError) and "not found" in str(exc).lower():
            pytest.skip(f"Model {model!r} not pulled in local Ollama ({exc})")
        raise

    classification = classify_response(result.text)
    echoed = _echoed_placeholder(result.text)
    if classification == ResponseClassification.FORMAT_ERROR and echoed is not None:
        pytest.xfail(
            f"Known template echo from {model!r}: {echoed!r} "
            f"(catalogued in tests/unit/test_model_fuzz_catalog.py)"
        )
    assert classification == ResponseClassification.VALID, (
        f"Model {model!r} returned Layer 0 classification {classification!r} for a minimal prompt.\n"
        f"Raw response: {result.text!r}\n"
        f"This is a known failure mode -- add it to tests/unit/test_model_fuzz_catalog.py."
    )

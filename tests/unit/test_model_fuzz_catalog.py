"""
LLM model failure catalog -- unit-level, no Ollama required.

Append-only catalog of confirmed (and near-confirmed) model failure patterns.
Each test documents provenance: which model, which run or date, what failure rate
was observed.  When a new failure mode is confirmed from a real run, it goes here.

Tests use :func:`core.analysis.response_classification.classify_response` directly,
i.e. they test Layer 0's classification of the raw string the model returned -- not
the full cascade.  These are the cheapest, most stable tests in the suite: no model
calls, no fixtures, no embeddings.

Tests marked ``xfail(strict=True)`` document *known gaps* in the current Layer 0
implementation -- failure patterns that are not yet caught.  They will loudly fail
as xfail the moment the gap is filled, forcing removal of the xfail marker.
"""

import json

import pytest

from core.analysis.response_classification import ResponseClassification, classify_response

# ---------------------------------------------------------------------------
# FORMAT_ERROR patterns — confirmed in real runs
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-04")
def test_fuzz_tinyllama_rewritten_output_placeholder():
    """tinyllama:latest, run-1792697949526, 2026-10-25.
    38% of rows (24/63) returned exactly this string -- the most common
    confirmed FORMAT_ERROR pattern in this project's real data.
    """
    assert classify_response(json.dumps({"text": "<rewritten output>"})) == ResponseClassification.FORMAT_ERROR


@pytest.mark.req("REQ-CASC-L0-04")
def test_fuzz_tinyllama_output_tag_variant():
    """tinyllama:latest, run-1792697949526, 2026-10-25.
    Shorter variant of the same template-echo pattern: a single bare <output> tag.
    """
    assert classify_response(json.dumps({"text": "<output>"})) == ResponseClassification.FORMAT_ERROR


@pytest.mark.req("REQ-CASC-L0-04")
def test_fuzz_angle_bracket_placeholder_with_spaces():
    """Generic placeholder variant: any single XML-tag-like string with internal spaces.
    Not confirmed from a specific run but structurally identical to the tinyllama pattern
    and caught by the same fullmatch regex.
    """
    assert classify_response(json.dumps({"text": "<insert text here>"})) == ResponseClassification.FORMAT_ERROR


# ---------------------------------------------------------------------------
# EMPTY patterns
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-01")
def test_fuzz_empty_text_field():
    """Any model, any run.  A zero-token-budget or early-stop condition -- model returns
    valid JSON but the text value is blank.
    """
    assert classify_response(json.dumps({"text": ""})) == ResponseClassification.EMPTY


@pytest.mark.req("REQ-CASC-L0-01")
def test_fuzz_whitespace_only_text_field():
    """Same as empty, but the model filled the field with whitespace -- common when models
    produce minimal output that collapses to nothing after strip().
    """
    assert classify_response(json.dumps({"text": "   "})) == ResponseClassification.EMPTY


# ---------------------------------------------------------------------------
# TRUNCATED patterns — hit token limit mid-generation
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-02")
def test_fuzz_truncated_mid_sentence():
    """Any model, confirmed in 3/500 rows of a large run.  Unbalanced braces indicate
    the response was cut off before JSON was closed -- a token-limit hit during generation,
    not a format misunderstanding.
    """
    assert classify_response('{"text": "The model was cut off mid-sen') == ResponseClassification.TRUNCATED


@pytest.mark.req("REQ-CASC-L0-02")
def test_fuzz_truncated_unbalanced_quotes():
    """Unbalanced quotes are another signature of mid-generation truncation."""
    assert classify_response('{"text": "Started but never') == ResponseClassification.TRUNCATED


# ---------------------------------------------------------------------------
# MALFORMED_JSON patterns — model ignored the JSON instruction
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-02")
def test_fuzz_plain_prose_no_json_wrapper():
    """Any model, seen in runs where temperature is high or the system prompt is short.
    The model generated good prose but didn't wrap it in the requested JSON envelope.
    """
    assert (
        classify_response("The model ignored the JSON instruction entirely and responded in prose.")
        == ResponseClassification.MALFORMED_JSON
    )


# ---------------------------------------------------------------------------
# SCHEMA_ERROR patterns — model returned JSON but with the wrong key
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-03")
def test_fuzz_wrong_json_key():
    """Any model.  Valid JSON but the key is not 'text' -- model followed a different
    schema than the one requested in the system prompt.
    """
    assert classify_response(json.dumps({"result": "wrong key entirely"})) == ResponseClassification.SCHEMA_ERROR


@pytest.mark.req("REQ-CASC-L0-03")
def test_fuzz_json_array_not_object():
    """Some models return a JSON array when asked for an object.  Syntactically valid JSON,
    but not the expected {"text": ...} shape.
    """
    assert classify_response('["not", "an", "object"]') == ResponseClassification.SCHEMA_ERROR


# ---------------------------------------------------------------------------
# Known gaps -- FORMAT_ERROR patterns not yet caught by the current regex
#
# The current regex is: re.fullmatch(r"<[^>]+>", text_val)
# It only catches angle-bracket placeholders.  The tests below document patterns
# that slip through as VALID today.  They are xfail(strict=True) so the moment
# the regex is extended to cover them, the xfail marker must be removed.
# ---------------------------------------------------------------------------


@pytest.mark.req("REQ-CASC-L0-04")
@pytest.mark.xfail(
    strict=True,
    reason="FORMAT_ERROR regex <[^>]+> does not cover all-caps fill-in-the-blank placeholders",
)
def test_fuzz_insert_text_here_not_yet_caught():
    """Generic LLM behavior: model echoes a fill-in-the-blank placeholder from training data.
    Seen in GPT-family outputs; not yet confirmed in this project's local Ollama runs.
    Not caught by the current <[^>]+> regex -- returns VALID today.
    """
    assert classify_response(json.dumps({"text": "INSERT TEXT HERE"})) == ResponseClassification.FORMAT_ERROR


@pytest.mark.req("REQ-CASC-L0-04")
@pytest.mark.xfail(
    strict=True,
    reason="FORMAT_ERROR regex <[^>]+> does not cover Jinja/mustache-style placeholders",
)
def test_fuzz_jinja_style_placeholder_not_yet_caught():
    """Jinja/mustache template echo: model returns double-brace placeholder instead of content.
    A plausible failure mode for models fine-tuned on template-heavy corpora.
    Not caught by the current <[^>]+> regex -- returns VALID today.
    """
    assert classify_response(json.dumps({"text": "{{placeholder}}"})) == ResponseClassification.FORMAT_ERROR

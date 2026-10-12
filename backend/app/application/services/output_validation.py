"""Output validation, repair and retry for model responses (Issue 4c).

The pipeline a task goes through:

    infer → validate → (repair → validate)* → deterministic fallback

1. :func:`validate_output` checks a raw answer against the task's contract —
   strict JSON schema for analysis tasks, validated markdown sections for
   generation tasks. It returns structured violations, never a bare boolean,
   so the repair prompt can name the exact problems.
2. :func:`generate_validated` drives the router, and if the first answer is
   invalid it re-prompts with the specific violations for up to
   ``max_repairs`` rounds.
3. If the output is still invalid, the caller gets a labelled
   ``DeterministicResult`` — an honest, structured "could not comply" — so a
   malformed model answer is never handed to the UI as if it were valid.

Nothing here invents content: an empty-but-valid answer stays valid, and the
fallback says so rather than filling gaps.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from app.infrastructure.ai.prompt_templates import (
    CONTRACT_JSON,
    CONTRACT_MARKDOWN,
    contract_for_task,
    markdown_sections_present,
)

logger = logging.getLogger(__name__)

# Model answers sometimes wrap JSON in a fence despite the instruction.
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)

DEFAULT_MAX_REPAIRS = 2


@dataclass
class ValidationResult:
    """Outcome of validating one raw model answer."""

    ok: bool
    kind: str
    violations: list[str] = field(default_factory=list)
    data: Mapping[str, Any] | None = None
    text: str | None = None


@dataclass
class ValidatedGeneration:
    """Final result of ``generate_validated``."""

    ok: bool
    task: str
    model_id: str | None
    kind: str
    content: str
    data: Mapping[str, Any] | None = None
    attempts: int = 1
    repaired: bool = False
    repair_violations: list[str] = field(default_factory=list)
    fallback: bool = False
    fallback_reason: str | None = None
    fallback_chain: list[str] = field(default_factory=list)
    routing_score: float | None = None


def _strip_json_fence(raw: str) -> str:
    """Bare JSON object extracted from a possibly fenced/annotated answer."""
    if not (raw or "").strip():
        return ""
    fence = _JSON_FENCE.search(raw)
    if fence:
        return fence.group(1).strip()
    obj = _JSON_OBJ.search(raw)
    if obj:
        return obj.group(0).strip()
    return raw.strip()


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _check_type(value: Any, expected: str) -> bool:
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_against_schema(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
    violations: list[str],
) -> None:
    """Minimal JSON-schema subset check (type/required/props/additional)."""
    expected = schema.get("type")
    if expected and not _check_type(value, expected):
        violations.append(f"{path or 'root'} must be {expected}, got {_type_name(value)}")
        return

    if not isinstance(value, dict):
        return

    required = schema.get("required") or []
    for key in required:
        if key not in value:
            violations.append(f"missing required key '{key}'")

    properties = schema.get("properties") or {}
    for key, subschema in properties.items():
        if key in value and value[key] is not None:
            _validate_against_schema(value[key], subschema, f"{path}{key}." if path else f"{key}.", violations)

    if schema.get("additionalProperties") is False:
        extra = sorted(set(value) - set(properties))
        if extra:
            violations.append(f"unexpected keys not in the schema: {', '.join(extra)}")


def validate_output(task: str, raw: str) -> ValidationResult:
    """Validate ``raw`` against the contract for ``task``."""
    contract = contract_for_task(task)
    raw = raw or ""

    if contract.kind == CONTRACT_JSON:
        if not raw.strip():
            return ValidationResult(False, CONTRACT_JSON, ["empty output — no JSON object was returned"])
        payload = _strip_json_fence(raw)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            return ValidationResult(
                False,
                CONTRACT_JSON,
                [f"output is not valid JSON ({exc.msg} at line {exc.lineno})"],
            )

        violations: list[str] = []
        _validate_against_schema(data, contract.json_schema or {}, "", violations)
        if violations:
            return ValidationResult(False, CONTRACT_JSON, violations)
        return ValidationResult(True, CONTRACT_JSON, [], data=data, text=json.dumps(data, ensure_ascii=False))

    # Markdown contract
    if not raw.strip():
        return ValidationResult(False, CONTRACT_MARKDOWN, ["empty output — no markdown was returned"])
    missing = markdown_sections_present(raw, contract.markdown_sections)
    if missing:
        return ValidationResult(
            False,
            CONTRACT_MARKDOWN,
            [f"missing required section(s): {', '.join(missing)}"],
        )
    return ValidationResult(True, CONTRACT_MARKDOWN, [], data=None, text=raw.strip())


def _empty_value_for(schema: Mapping[str, Any]) -> Any:
    """A type-correct empty value for a schema node (0, "", [], {}, None)."""
    expected = schema.get("type")
    if expected == "array":
        return []
    if expected == "object":
        return {key: _empty_value_for(sub) for key, sub in (schema.get("properties") or {}).items()}
    if expected == "integer":
        return 0
    if expected == "number":
        return 0
    if expected == "string":
        return ""
    return None


def deterministic_unavailable_content(task: str, reason: str, *, language: str = "en") -> dict:
    """Honest structured payload when no valid answer could be produced.

    Built **from the contract** rather than hardcoded, so the result always
    satisfies the task's schema regardless of how contracts evolve. It holds
    no extra status keys — the status and reason travel separately on the
    :class:`ValidatedGeneration` (``fallback`` / ``fallback_reason``).
    """
    contract = contract_for_task(task)
    note = {
        "en": "The AI did not return a valid result. " f"Reason: {reason}. Please retry or rephrase.",
        "de": "Die KI hat kein gültiges Ergebnis geliefert. "
        f"Grund: {reason}. Bitte erneut versuchen oder umformulieren.",
        "fr": "L'IA n'a pas renvoyé de résultat valide. " f"Raison : {reason}. Veuillez réessayer ou reformuler.",
    }.get(language, "")

    if contract.kind == CONTRACT_JSON:
        schema = contract.json_schema or {}
        payload: dict[str, Any] = {}
        for key in schema.get("required") or []:
            payload[key] = _empty_value_for((schema.get("properties") or {}).get(key, {}))
        # Put the explanation in the first string-typed field so the reader
        # sees *why* it is empty, without adding a key the schema forbids.
        for key, subschema in (schema.get("properties") or {}).items():
            if key in payload and subschema.get("type") == "string":
                payload[key] = note
                break
        return payload

    sections = contract.markdown_sections
    if not sections:
        return {"content": note}
    body = "\n\n".join(f"## {name}\n{note if name == sections[0] else ''}" for name in sections)
    return {"content": body.strip()}


def generate_validated(
    task: str,
    *,
    prompt: str,
    language: str = "en",
    token_budget: int = 1024,
    preferred_languages: tuple[str, ...] = ("en", "de", "fr"),
    preferred_model_id: str | None = None,
    max_repairs: int = DEFAULT_MAX_REPAIRS,
    generate: Callable[..., Mapping[str, Any]] | None = None,
    repair_generate: Callable[..., Mapping[str, Any]] | None = None,
) -> ValidatedGeneration:
    """Infer, validate, repair up to ``max_repairs`` times, else fall back.

    ``generate`` / ``repair_generate`` are injectable so tests can drive this
    without a live model. ``generate`` performs normal inference and must
    return a mapping with at least ``content`` and ``model_id``;
    ``repair_generate`` receives ``repair_prompt`` and returns the same shape.
    """
    if generate is None:
        raise ValueError("generate callback is required")

    inference = generate(
        task=task,
        prompt=prompt,
        token_budget=token_budget,
        preferred_languages=preferred_languages,
        preferred_model_id=preferred_model_id,
    )
    raw = str(inference.get("content") or "")
    result = validate_output(task, raw)

    repair_violations: list[str] = []
    attempts = 1
    repaired = False

    while not result.ok and attempts <= max_repairs:
        violations = list(result.violations)
        repair_violations = violations
        attempts += 1
        logger.info(
            "ai.outputcontract repair task=%s attempt=%d violations=%s",
            task,
            attempts,
            violations,
        )
        if repair_generate is None:
            break
        repair_prompt = _repair_prompt_for(task, previous_output=raw, violations=violations, language=language)
        repaired_inference = repair_generate(
            task=task,
            prompt=repair_prompt,
            token_budget=token_budget,
            preferred_languages=preferred_languages,
            preferred_model_id=preferred_model_id,
        )
        raw = str(repaired_inference.get("content") or "")
        inference = {**inference, **repaired_inference}
        result = validate_output(task, raw)
        repaired = True

    if result.ok:
        return ValidatedGeneration(
            ok=True,
            task=task,
            model_id=inference.get("model_id"),
            kind=result.kind,
            content=result.text or "",
            data=result.data,
            attempts=attempts,
            repaired=repaired,
            repair_violations=repair_violations,
            fallback=False,
            fallback_chain=inference.get("fallback_chain", []) or [],
            routing_score=inference.get("routing_score"),
        )

    reason = "; ".join(result.violations) or "output did not match the required format"
    logger.warning("ai.outputcontract exhausted task=%s reason=%s", task, reason)
    return ValidatedGeneration(
        ok=False,
        task=task,
        model_id=inference.get("model_id"),
        kind=result.kind,
        content=str(result.text or ""),
        data=None,
        attempts=attempts,
        repaired=repaired,
        repair_violations=repair_violations,
        fallback=True,
        fallback_reason=reason,
        fallback_chain=inference.get("fallback_chain", []) or [],
        routing_score=inference.get("routing_score"),
    )


def _repair_prompt_for(
    task: str,
    *,
    previous_output: str,
    violations: list[str],
    language: str,
) -> str:
    """Kept as a thin wrapper so the repair prompt lives in one place."""
    from app.infrastructure.ai.prompt_templates import build_repair_prompt

    return build_repair_prompt(
        task,
        previous_output=previous_output,
        violations=violations,
        language=language,
    )

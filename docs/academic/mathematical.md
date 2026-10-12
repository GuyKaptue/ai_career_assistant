# Formal models

This document states the mathematical models used by the AI routing
subsystem and the ATS scoring pipeline. All models are deterministic
given their inputs.

## 1. Token budget (§9)

The required context for a generation request is:

```
required_context = input_tokens + reserved_output_tokens
                 + system_tokens + safety_margin
```

where:

- `input_tokens` = tokens in the user prompt
- `reserved_output_tokens` = caller-supplied output budget
- `system_tokens` = tokens in the system prompt
- `safety_margin` = fixed safety buffer

A model is eligible only when:

```
required_context <= context_window
```

If `context_window` is `None` (unknown), the fit is **not verifiable**;
the model is not eliminated for this reason — the unknown is recorded,
never fabricated.

## 2. Routing score (§11)

Each eligible model `m` receives a weighted score:

```
Score(m, r) = Σ w_i · component_i(m, r)
```

where `r` is the routing request (task, context requirement, preferred
languages, weights) and `w_i` are configurable weights from
`ROUTING_WEIGHTS`. Components include context fit, license approval,
health, and capability coverage.

Selection is **eliminate-then-rank**:

1. Eliminate models that fail hard filters (task, license, context).
2. Rank the survivors by `Score(m, r)`.
3. Select the highest-scoring model.

## 3. Fallback chain (§12)

The fallback chain for a task is the ranked survivors, bounded by
`AI_MAX_FALLBACK_DEPTH`. It is **dynamically generated** per request —
the spec's example chains are never hard-coded as universal truth.

Failover is taxonomy-driven (§14). Each failure maps to a typed
category with a deterministic action:

| Failure | Action |
|---------|--------|
| `RATE_LIMITED` | Bounded retry on the **same** model with exponential backoff |
| `TIMEOUT` | Bounded retry on the **same** model with exponential backoff |
| `SCHEMA_VALIDATION_FAILED` | Bounded retry on the **same** model with exponential backoff |
| `CONTEXT_LENGTH_EXCEEDED` | Switch to the next candidate |
| `QUOTA_EXCEEDED` | Switch to the next candidate |
| `RESOURCE_EXHAUSTED` | Switch to the next candidate |
| `MODEL_UNAVAILABLE` | Mark model unhealthy, open circuit breaker, switch |

## 4. Circuit breaker (§14)

States: `CLOSED → OPEN → HALF_OPEN → CLOSED`.

- `OPEN`: fail fast; a probe is allowed after `reset_timeout`.
- `HALF_OPEN`: one probe request; success → `CLOSED`, failure → `OPEN`.

## 5. ATS aggregation (§19)

The ATS score is a weighted aggregation of sub-scores:

```
score = 0.5 × keyword_overlap
      + 0.25 × formatting_score
      + 0.25 × readability_score
```

Each sub-score is bounded 0–100.

### 5.1 Keyword overlap

```
keyword_overlap = |matched ∩ required| / |required| × 100
```

where `matched` is the set of keywords present in the resume and
`required` is the set of keywords required by the job description.
Keywords are normalized (lowercase, punctuation-stripped).

### 5.2 Formatting score

Heuristics over the resume text:

- Presence of a contact block (email, phone).
- Presence of named sections (summary, experience, skills).
- Length within a plausible range.
- Absence of placeholder-like tokens.

### 5.3 Readability score

A linear combination of surface statistics, normalized to 0–100:

- Sentence length variance.
- Word-length distribution.
- Section density.

## 6. Unknown values

A field whose value is unknown is `None`. It is **never** replaced by
a default or an average. `ModelMetadata.unknown_fields()` enumerates
the fields that are unknown for audit purposes.

## Related documents

- [ats.md](ats.md)
- [ai-generation.md](ai-generation.md)
- [system.md](system.md)
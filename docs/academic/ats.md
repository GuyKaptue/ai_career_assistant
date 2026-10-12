# ATS scoring theory

The ATS (Applicant Tracking System) checker estimates how well a resume
matches a job description. It is a **heuristic**, not a prediction of
hiring outcome. Every component is documented and bounded.

## 1. Inputs

- `resume_text`: free text provided by the user.
- `job_description`: free text of the target role.
- Optional: target keywords (derived from the job description).

## 2. Outputs (9 keys)

| Key | Type | Meaning |
|-----|------|---------|
| `score` | 0–100 | Weighted aggregate |
| `matched_keywords` | list | Keywords in both resume and JD |
| `missing_keywords` | list | Keywords in JD but not resume |
| `strengths` | list | Human-readable observations |
| `suggestions` | list | Actionable improvements |
| `keyword_overlap` | 0–100 | Keyword sub-score |
| `formatting_score` | 0–100 | Format sub-score |
| `readability_score` | 0–100 | Readability sub-score |
| `explanation` | str | Methodology summary |

## 3. Aggregation

```
score = 0.5 × keyword_overlap
      + 0.25 × formatting_score
      + 0.25 × readability_score
```

The keyword component dominates because matching the job description is
the primary signal; format and readability are secondary corrections.

## 4. Keyword extraction

Keywords are extracted from the job description by:

1. Normalizing text (lowercase, punctuation-stripped).
2. Filtering to content words (nouns, verbs, technical terms).
3. De-duplicating.

The same normalization is applied to the resume so matching is
normalization-invariant.

## 5. Formatting heuristics

The formatting score rewards:

- A contact block (email and/or phone present).
- Named sections (summary, experience, skills, education).
- A plausible total length (not empty, not a wall of text).
- Absence of placeholder-like tokens (`lorem ipsum`, `TODO`, `[...]`).

Each heuristic contributes a bounded sub-score; the sum is normalized
to 0–100.

## 6. Readability heuristics

The readability score rewards:

- Moderate sentence length (not one long sentence, not fragments).
- Moderate word length (technical terms are fine; excessive jargon is penalized).
- Section density (each named section has content).

The score is normalized to 0–100.

## 7. Anti-fabrication

The checker **never** invents experience, education, metrics,
certifications, or skills. If a metric is not provided, it is omitted.
Suggestions are generic (e.g. "add a summary section") and never
assert facts about the user.

## 8. Limitations

- The score is a heuristic estimate, not a hiring prediction.
- Keyword matching is lexical; synonyms are not matched (semantic
  matching is a future roadmap item, RD-04).
- Formatting heuristics are English-centric.
- The score is not comparable across different job descriptions.

## Related documents

- [mathematical.md](mathematical.md)
- [system.md](system.md)
- [limitations.md](limitations.md)
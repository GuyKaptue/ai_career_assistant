# Third-party licenses

Last audit: 2026-10-09 (generated from `backend/requirements.txt` + `frontend/package.json`; versions pinned in requirements, ranges in pyproject).

This project is distributed under the **MIT License** (see `LICENSE`).
Every dependency below is permissive (MIT / Apache-2.0 / BSD-3-Clause /
BSD), so no copyleft obligations apply.

## Python dependencies (`backend/requirements.txt`)

| Package | Version | License | Compatible with MIT use |
|---------|---------|---------|-------------------------|
| bandit | 1.7.10 | Apache-2.0 | Yes |
| fastapi | 0.142.2 | MIT | Yes |
| httpx | 0.27.2 | BSD-3-Clause | Yes |
| huggingface_hub | 0.34.3 | Apache-2.0 | Yes |
| mypy | 1.13.0 | MIT | Yes |
| pip-audit | 2.7.3 | Apache-2.0 | Yes |
| Pillow | 12.3.0 | MIT-CMU (HPND) | Yes |
| pydantic | 2.11.7 | MIT | Yes |
| python-multipart | 0.0.20 | Apache-2.0 | Yes |
| pypdf | 6.19.0 | BSD-3-Clause | Yes |
| pytest | 9.0.3 | MIT | Yes |
| pytest-cov | 5.0.0 | MIT | Yes |
| python-docx | 1.2.0 | MIT | Yes |
| python-dotenv | 1.2.2 | BSD-3-Clause | Yes |
| PyJWT | 2.15.0 | MIT | Yes |
| PyYAML | 6.0.1 | MIT | Yes |
| reportlab | 4.4.4 | BSD | Yes |
| ruff | 0.7.3 | MIT | Yes |
| starlette | 1.3.1 | BSD-3-Clause | Yes |
| tokenizers | 0.20.0 | Apache-2.0 | Yes |
| types-PyYAML | 6.0.12 | Apache-2.0 | Yes |
| uvicorn | 0.30.6 | BSD-3-Clause | Yes |

All licenses are permissive. No GPL/LGPL/Affero obligations apply.

## Frontend dependencies (`frontend/package.json`)

| Package | Version | License | Compatible with MIT use |
|---------|---------|---------|-------------------------|
| @supabase/supabase-js | ^2.109.0 | MIT | Yes |
| react | ^18.3.1 | MIT | Yes |
| react-dom | ^18.3.1 | MIT | Yes |
| @vitejs/plugin-react | ^4.3.1 | MIT | Yes |
| vite | ^5.4.10 | MIT | Yes |

## Audit method

```
python3 -m piplicenses --format=json   # backend dependencies
npm ls --all                          # frontend dependencies
```

Re-run with `make licenses` to refresh this file.

## Template assets

- **Reactive Resume direction (MIT):** original template implementations; attribution preserved where applicable.
- **Resumaker.ai (reference only):** proprietary. Used solely as publicly observable inspiration (typography hierarchy, section organization, spacing). No source code, CSS, assets, APIs, or backend logic copied; no runtime dependency; never presented as an official integration.

## Rule for new assets

Permissive licenses only (MIT, Apache-2.0, BSD family, CC BY-SA where applicable).
Every third-party font/asset/design fragment gets license + attribution here and in `docs/legal/licensing/third-party-assets.md` before release.

## Related documents

- `docs/legal/licensing/third-party-assets.md` — template-base decision and attribution
- `LICENSE` — project license
- `docs/requirements/requirements.md` — licensing requirement
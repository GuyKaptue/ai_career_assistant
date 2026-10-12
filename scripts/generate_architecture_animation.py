#!/usr/bin/env python3
"""Generate the animated full-system architecture visualization (Phase 11).

The animation is built from real Graphviz layout rather than a static asset:
every stage renders its own DOT frame with the already-revealed components
highlighted and the not-yet-revealed components ghosted, so node positions stay
stable while the verified data flow is progressively revealed.

Outputs (all derived from the definitions below, so they cannot drift apart):

* ``docs/images/full_system_architecture.gif``  — multi-frame animated GIF (loops)
* ``docs/images/full_system_architecture.svg``  — vector overview of the complete system
* ``docs/diagrams/full_system_architecture.dot``— editable source of the complete system

Requires Graphviz ``dot`` on PATH and Pillow. Usage::

    python3 scripts/generate_architecture_animation.py

Automated tests only check that the committed ``.gif`` is a real multi-frame
animation; this module holds the design/data definition and thin render helpers.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = REPO_ROOT / "docs" / "images"
DIAGRAMS_DIR = REPO_ROOT / "docs" / "diagrams"
GIF_PATH = IMAGES_DIR / "full_system_architecture.gif"
SVG_PATH = IMAGES_DIR / "full_system_architecture.svg"
DOT_PATH = DIAGRAMS_DIR / "full_system_architecture.dot"

DPI = 96
FOCUS_MS = 450
HOLD_MS = 1100

# --- visual palette (one entry per component category) -----------------------
PALETTE: dict[str, tuple[str, str, str]] = {
    "actor": ("#ECEFF1", "#37474F", "#263238"),
    "frontend": ("#E3F2FD", "#1565C0", "#0D47A1"),
    "api": ("#E8F5E9", "#2E7D32", "#1B5E20"),
    "jobs": ("#FFF9C4", "#F9A825", "#8D6E00"),
    "client": ("#FFF3E0", "#EF6C00", "#BF360C"),
    "external": ("#FCE4EC", "#AD1457", "#880E4F"),
    "data": ("#EDE7F6", "#4527A0", "#311B92"),
    "ai": ("#E0F7FA", "#00838F", "#006064"),
    "security": ("#FFEBEE", "#C62828", "#8E1D1D"),
}
GHOST = ("#F7F8FA", "#CFD8DC", "#9AA5B1")
EDGE_COLOR = "#546E7A"
EDGE_GHOST = "#ECEFF1"

# --- components (id -> (label, category)) ------------------------------------
NODES: dict[str, tuple[str, str]] = {
    "user": ("User\n(Browser)", "actor"),
    "fe_search": ("Job discovery UI\nquery · location · load more", "frontend"),
    "fe_results": ("Job results\ntitle · company · location\nprovider · remote · salary · date\npartial-failure notice", "frontend"),
    "fe_state": ("hooks/\nuseAsync · useSession\nuseStatus · useApplications", "frontend"),
    "fe_api": ("lib/api.js\nREST client (+ JWT)", "frontend"),
    "fe_i18n": ("i18n\nen / de / fr", "frontend"),
    "api_jobs": ("GET /api/v1/jobs/search\n(+ documents · profiles\napplications · resume/check)", "api"),
    "api_valid": ("Pydantic validation\ntyped errors: 400 / 401 / 404\n422 / 500 / 502 / 503", "api"),
    "core_sec": ("core: JWT HS256 · user scoping\nrate limiting · security headers\nstructured logs", "security"),
    "agg": ("search_jobs()\naggregator\nThreadPoolExecutor", "jobs"),
    "cache": ("TTL cache (3600 s)\nkey = query|location|page\n|limit|providers|filters\nRLock · deep copy", "jobs"),
    "retry": ("reliability\n8 s request timeout\n25 s aggregate timeout\n3 retries · backoff + jitter\nRetry-After (429)", "jobs"),
    "job_model": ("Unified Job schema\nfrozen dataclass\nunknown fields stay null\nsource + provider_id kept", "jobs"),
    "dedup": ("deduplicate\ncompany + title + location\n-> canonical URL -> source+id", "jobs"),
    "sort": ("sort newest first\nISO / epoch / DE dates\nundated jobs sort last", "jobs"),
    "partial": ("partial failures\noutcome per provider\nerrors carry category only\n502 only if all providers fail", "jobs"),
    "cl_adzuna": ("AdzunaProvider\nADZUNA_APP_ID/KEY\n/de/search", "client"),
    "cl_aa": ("ArbeitsagenturProvider\nX-API-Key jobboerse-jobsuche\nv6/jobs · v4/jobdetails", "client"),
    "cl_an": ("ArbeitnowProvider\npublic feed\nfollows links.next (<= 5)", "client"),
    "ext_adzuna": ("api.adzuna.com\n(quota-limited)", "external"),
    "ext_aa": ("rest.arbeitsagentur.de\njobboerse/jobsuche-service", "external"),
    "ext_an": ("arbeitnow.com\n/api/job-board-api", "external"),
    "db": ("Supabase PostgreSQL\n+ pgvector · RLS\nprofiles · documents\napplications · embeddings", "data"),
    "hf": ("Hugging Face\nInference API\n+ embeddings (optional)", "ai"),
    "gen": ("document generation\nATS check · semantic match\n(RD-03 / RD-04 / RD-05)", "ai"),
}

CLUSTERS: list[tuple[str, list[str]]] = [
    ("Frontend — React 18 + Vite SPA (:5173)", ["fe_search", "fe_results", "fe_state", "fe_api", "fe_i18n"]),
    ("Backend — FastAPI (:8000)", ["api_jobs", "api_valid"]),
    ("Job aggregation — domain/jobs/service.py", ["agg", "cache", "retry", "job_model", "dedup", "sort", "partial"]),
    ("Provider clients — infrastructure/job_providers", ["cl_adzuna", "cl_aa", "cl_an"]),
    ("External APIs", ["ext_adzuna", "ext_aa", "ext_an"]),
    ("Persistence & AI", ["db", "hf", "gen"]),
    ("Cross-cutting core", ["core_sec"]),
]

# --- directed relationships (src, dst, label) --------------------------------
EDGES: list[tuple[str, str, str]] = [
    ("user", "fe_search", "HTTPS"),
    ("fe_search", "fe_state", ""),
    ("fe_search", "fe_results", ""),
    ("fe_search", "fe_i18n", ""),
    ("fe_state", "fe_api", "fetch"),
    ("fe_api", "api_jobs", "REST /api/v1\nBearer JWT"),
    ("fe_api", "db", "supabase-js\nauth + anon key"),
    ("api_jobs", "api_valid", "validate"),
    ("api_jobs", "agg", "search_jobs()"),
    ("agg", "cache", "lookup / store"),
    ("agg", "retry", "policy"),
    ("agg", "cl_adzuna", "parallel"),
    ("agg", "cl_aa", "parallel"),
    ("agg", "cl_an", "parallel"),
    ("cl_adzuna", "ext_adzuna", "search"),
    ("cl_aa", "ext_aa", "search"),
    ("cl_an", "ext_an", "feed"),
    ("ext_adzuna", "job_model", "jobs"),
    ("ext_aa", "job_model", "jobs"),
    ("ext_an", "job_model", "jobs"),
    ("job_model", "dedup", ""),
    ("dedup", "sort", ""),
    ("sort", "partial", "outcomes"),
    ("partial", "api_jobs", "results + provider_status"),
    ("api_jobs", "fe_api", "JSON"),
    ("fe_api", "fe_results", ""),
    ("fe_results", "user", "rendered results"),
    ("api_jobs", "db", "persist (tracked jobs)"),
    ("gen", "hf", "use_ai=true"),
    ("gen", "db", "embeddings + RAG"),
    ("core_sec", "api_jobs", "guards"),
]

# --- progressive reveal: (caption, nodes, edges) -----------------------------
STAGES: list[tuple[str, set[str], set[tuple[str, str]]]] = [
    ("application and entry points", {"user", "fe_search"}, {("user", "fe_search")}),
    (
        "frontend components and user interaction",
        {"fe_results", "fe_state", "fe_api", "fe_i18n"},
        {("fe_search", "fe_state"), ("fe_search", "fe_results"), ("fe_search", "fe_i18n"), ("fe_state", "fe_api")},
    ),
    (
        "backend API, validation and cross-cutting core",
        {"api_jobs", "api_valid", "core_sec"},
        {("fe_api", "api_jobs"), ("api_jobs", "api_valid"), ("core_sec", "api_jobs")},
    ),
    ("aggregator entry point and one-hour cache", {"agg", "cache"}, {("api_jobs", "agg"), ("agg", "cache")}),
    (
        "three job clients (Adzuna, Bundesagentur, Arbeitnow)",
        {"cl_adzuna", "cl_aa", "cl_an"},
        {("agg", "cl_adzuna"), ("agg", "cl_aa"), ("agg", "cl_an")},
    ),
    (
        "provider sources returning job data",
        {"ext_adzuna", "ext_aa", "ext_an"},
        {("cl_adzuna", "ext_adzuna"), ("cl_aa", "ext_aa"), ("cl_an", "ext_an")},
    ),
    (
        "normalization into the unified Job schema",
        {"job_model"},
        {("ext_adzuna", "job_model"), ("ext_aa", "job_model"), ("ext_an", "job_model")},
    ),
    ("deduplication and newest-first date sorting", {"dedup", "sort"}, {("job_model", "dedup"), ("dedup", "sort")}),
    (
        "timeouts, retries and partial-failure handling",
        {"retry", "partial"},
        {("agg", "retry"), ("sort", "partial")},
    ),
    (
        "normalized response returning to the browser",
        set(),
        {("partial", "api_jobs"), ("api_jobs", "fe_api"), ("fe_api", "fe_results"), ("fe_results", "user")},
    ),
    (
        "persistence, AI integration and security boundaries",
        {"db", "hf", "gen"},
        {("api_jobs", "db"), ("gen", "hf"), ("gen", "db"), ("fe_api", "db")},
    ),
    ("complete verified system overview", set(NODES), {(src, dst) for src, dst, _ in EDGES}),
]


# --- rendering --------------------------------------------------------------


def render_dot(caption: str, revealed: set[str], revealed_edges: set[tuple[str, str]],
               current: set[str], current_edges: set[tuple[str, str]], final: bool = False) -> str:
    """Return DOT source that ghosts every not-yet-revealed component."""
    lines = [
        "digraph full_system_architecture {",
        '  graph [rankdir=LR, bgcolor="white", fontname="Helvetica", fontsize=13, labelloc="t",',
        f'         label="AI Career Assistant — Full System Architecture\\n{caption}",',
        "         pad=0.35, nodesep=0.32, ranksep=0.6];",
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, margin="0.11,0.07"];',
        '  edge [fontname="Helvetica", fontsize=8, arrowsize=0.7];',
        "",
    ]

    def node_line(node_id: str) -> str:
        label, category = NODES[node_id]
        fill, border, font = PALETTE[category] if node_id in revealed else GHOST
        penwidth = "2.4" if node_id in current and not final else "1.2"
        return (
            f'  {node_id} [label="{label}", fillcolor="{fill}", color="{border}", '
            f"fontcolor=\"{font}\", penwidth={penwidth}];"
        )

    clustered = {node for _, members in CLUSTERS for node in members}
    lines.extend(node_line(node_id) for node_id in NODES if node_id not in clustered)
    lines.append("")

    for index, (title, members) in enumerate(CLUSTERS):
        lines.append(f"  subgraph cluster_{index} {{")
        lines.append(f'    label="{title}";')
        lines.append('    style="rounded,filled"; fillcolor="#FCFDFF"; color="#E0E6ED";')
        lines.append('    fontsize=11; fontname="Helvetica";')
        lines.extend(f"  {node_line(node_id)}" for node_id in members)
        lines.append("  }")
        lines.append("")

    for source, target, label in EDGES:
        key = (source, target)
        if key in current_edges and not final:
            style = f'color="{EDGE_COLOR}", fontcolor="{EDGE_COLOR}", penwidth=2.4'
        elif key in revealed_edges:
            style = f'color="{EDGE_COLOR}", fontcolor="{EDGE_COLOR}", penwidth=1.1'
        else:
            style = f'color="{EDGE_GHOST}", fontcolor="{EDGE_GHOST}", penwidth=0.6'
        attribute = f'label="{label}", {style}' if label else style
        lines.append(f"  {source} -> {target} [{attribute}];")

    def render_file(source: str, target: Path, fmt: str, dpi: int | None = None) -> None:
    command = ["dot", f"-T{fmt}"]
    if dpi is not None:
        command.append(f"-Gdpi={dpi}")
    command.extend(["-o", str(target)])
    subprocess.run(command, input=source, text=True, check=True)


def build() -> tuple[Path, Path, Path, int]:
    """Render every animation frame plus the complete-system DOT and SVG."""
    if shutil.which("dot") is None:
        raise SystemExit("Graphviz 'dot' is required (brew install graphviz / apt install graphviz).")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

    complete_dot = render_dot(
        "complete verified system overview",
        set(NODES),
        {(src, dst) for src, dst, _ in EDGES},
        set(),
        set(),
        final=True,
    )
    DOT_PATH.write_text(complete_dot, encoding="utf-8")
    render_file(complete_dot, SVG_PATH, "svg")

    revealed: set[str] = set()
    revealed_edges: set[tuple[str, str]] = set()
    frames: list[Image.Image] = []
    durations: list[int] = []

    with tempfile.TemporaryDirectory() as workspace:
        workdir = Path(workspace)
        for index, (caption, nodes, edges) in enumerate(STAGES, start=1):
            revealed |= nodes
            revealed_edges |= edges
            last_stage = index == len(STAGES)
            for suffix, current_nodes, current_edges, duration in (
                ("focus", nodes, edges, FOCUS_MS),
                ("settled", set(), set(), HOLD_MS if last_stage else FOCUS_MS + 150),
            ):
                frame_path = workdir / f"frame_{index:02d}_{suffix}.png"
                source = render_dot(
                    f"step {index}/{len(STAGES)} · {caption}", revealed, revealed_edges, current_nodes, current_edges
                )
                render_file(source, frame_path, "png", DPI)
                frames.append(Image.open(frame_path).convert("RGB"))
                durations.append(duration)

    palette_frames = [frame.convert("P", palette=Image.ADAPTIVE, colors=64) for frame in frames]
    palette_frames[0].save(
        GIF_PATH,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return GIF_PATH, SVG_PATH, DOT_PATH, len(palette_frames)


def main() -> int:
    gif_path, svg_path, dot_path, frames = build()
    print(f"wrote {gif_path.relative_to(REPO_ROOT)} ({frames} frames, {len(STAGES)} stages)")
    print(f"wrote {svg_path.relative_to(REPO_ROOT)}")
    print(f"wrote {dot_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
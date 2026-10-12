from pathlib import Path


def test_ci_and_makefile_cover_quality_gates() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "ci.yml"
    makefile = repo_root / "Makefile"

    assert workflow.exists()
    assert makefile.exists()

    workflow_text = workflow.read_text(encoding="utf-8")
    makefile_text = makefile.read_text(encoding="utf-8")

    for token in ("ruff", "mypy", "pytest", "bandit", "pip-audit"):
        assert token in workflow_text.lower()

    for target in ("lint", "typecheck", "test", "coverage", "security", "docker-build"):
        assert f"{target}:" in makefile_text

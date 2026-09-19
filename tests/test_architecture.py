"""Stage isolation guard (CLAUDE.md sections 3.1 and 3.4, SPECS SEC-4).

Never relax this file to make a build pass (CONSTRAINTS.md F3): extending it to
cover a new boundary is fine; allow-lists, skips and early returns are not.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "architecture_fixtures"

# (directory to walk, directory its absolute imports resolve from). The backend
# is imported as `app` because pytest and uvicorn put `backend/` on the path.
# A missing directory is skipped, so the fixtures need not mirror all four.
SCAN_ROOTS = [
    ("stages", "."),
    ("contracts", "."),
    ("shared", "."),
    ("backend/app", "backend"),
]

BACKEND_PACKAGES = {"app", "backend"}
FRAMEWORKS = {"fastapi", "starlette", "sqlalchemy", "alembic"}


@dataclass(frozen=True)
class Violation:
    path: str  # POSIX, relative to the root passed to find_violations
    line: int
    imported: str
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} imports {self.imported} ({self.rule})"


def python_files(repo_root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield (file, import base) for every file under the guarded roots."""
    for directory, import_base in SCAN_ROOTS:
        scan_dir = repo_root / directory
        if scan_dir.is_dir():
            for file in sorted(scan_dir.rglob("*.py")):
                yield file, repo_root / import_base


def _resolve_from(node: ast.ImportFrom, package: list[str]) -> str | None:
    if node.level == 0:
        return node.module
    # Level 1 is the file's own package; each extra level climbs one parent.
    climb = node.level - 1
    if climb > len(package):
        return None  # beyond the top package: Python itself rejects this
    parts = package[: len(package) - climb]
    if node.module:
        parts = [*parts, node.module]
    return ".".join(parts) or None


def _dynamic_import(node: ast.Call) -> str | None:
    # importlib.import_module("x") / import_module("x") / __import__("x"), with
    # a literal name; a computed name cannot be resolved statically.
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in {"import_module", "__import__"} or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        if not first.value.startswith("."):
            return first.value
    return None


def _imports(tree: ast.AST, package: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield (line, candidates) per import. For `from M import a, b` the
    candidates are M, M.a, M.b: `from stages import analyze` imports a stage
    even though the module part alone is the neutral `stages` package."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, [alias.name]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(node, package)
            if base is not None:
                names = [a.name for a in node.names if a.name != "*"]
                yield node.lineno, [base, *(f"{base}.{n}" for n in names)]
        elif isinstance(node, ast.Call):
            target = _dynamic_import(node)
            if target is not None:
                yield node.lineno, [target]


def _broken_rule(location: tuple[str, ...], imported: str) -> str | None:
    """The rule `imported` breaks when imported from `location` (the file's
    path parts relative to the repo root), or None if it is allowed."""
    target = imported.split(".")
    top = target[0]
    if location[0] == "stages":
        # stages/<name>/... belongs to stage <name>; a file directly in stages/
        # belongs to none, so it may not become a back door between stages.
        owner = location[1] if len(location) > 2 else None
        if top == "stages" and len(target) > 1 and target[1] != owner:
            return "cross-stage import (CLAUDE.md 3.1)"
        if top in BACKEND_PACKAGES:
            return "stage imports the backend (CLAUDE.md 3.4, SEC-4)"
        if top in FRAMEWORKS:
            return "stage imports a web/DB framework (CLAUDE.md 3.4)"
    elif location[0] == "contracts":
        if top in {"stages", "shared"} | BACKEND_PACKAGES | FRAMEWORKS:
            return "contracts must stay a leaf package (CLAUDE.md 3.1)"
    elif location[0] == "shared":
        if top == "stages" or top in BACKEND_PACKAGES:
            return "shared imports a stage or the backend (CLAUDE.md 3.1, SEC-4)"
    return None


def find_violations(repo_root: Path) -> list[Violation]:
    violations = []
    for file, import_base in python_files(repo_root):
        location = file.relative_to(repo_root).parts
        package = list(file.relative_to(import_base).parts[:-1])
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for line, candidates in _imports(tree, package):
            for imported in candidates:
                rule = _broken_rule(location, imported)
                if rule is not None:
                    path = file.relative_to(repo_root).as_posix()
                    violations.append(Violation(path, line, imported, rule))
                    break  # `from stages import a, b` is reported once
    return violations


# --- planted violations (tests/architecture_fixtures/) ------------------------

# (fixture file, import it must be flagged for), one violation per file.
EXPECTED_FIXTURE_VIOLATIONS = [
    ("stages/ingest/cross_absolute.py", "stages.analyze.metrics_core"),
    ("stages/ingest/cross_relative.py", "stages.analyze"),
    ("stages/ingest/cross_from_package.py", "stages.analyze"),
    ("stages/ingest/cross_plain_import.py", "stages.diagnose"),
    ("stages/ingest/cross_type_checking.py", "stages.report"),
    ("stages/ingest/cross_dynamic.py", "stages.predict"),
    ("stages/ingest/backend_app.py", "app.config"),
    ("stages/ingest/backend_prefixed.py", "backend.app.main"),
    ("stages/ingest/framework_fastapi.py", "fastapi"),
    ("stages/ingest/framework_sqlalchemy.py", "sqlalchemy.orm"),
    ("stages/new_stage/cross_from_new_stage.py", "stages.ingest"),
    ("stages/root_module.py", "stages.ingest"),
    ("contracts/imports_stage.py", "stages.ingest"),
    ("contracts/imports_shared.py", "shared"),
    ("contracts/imports_backend.py", "app.config"),
    ("contracts/imports_framework.py", "fastapi"),
    ("shared/imports_stage.py", "stages.ingest"),
    ("shared/imports_backend.py", "backend.app"),
]


@pytest.mark.parametrize(
    ("relative_path", "imported"),
    EXPECTED_FIXTURE_VIOLATIONS,
    ids=[path for path, _ in EXPECTED_FIXTURE_VIOLATIONS],
)
def test_planted_violation_is_caught(relative_path: str, imported: str) -> None:
    violations = find_violations(FIXTURES / "violations")

    flagged = [(v.path, v.imported) for v in violations if v.path == relative_path]

    assert flagged == [(relative_path, imported)]


def test_every_violation_fixture_is_expected() -> None:
    # A fixture file nobody lists here would prove nothing; a fixture the walker
    # flags twice would hide a wrong resolution.
    violations = find_violations(FIXTURES / "violations")

    assert sorted((v.path, v.imported) for v in violations) == sorted(
        EXPECTED_FIXTURE_VIOLATIONS
    )


def test_allowed_imports_are_not_flagged() -> None:
    assert find_violations(FIXTURES / "clean") == []


# --- the real repository ------------------------------------------------------


def test_repository_has_no_forbidden_imports() -> None:
    violations = find_violations(REPO_ROOT)

    assert violations == [], "forbidden imports:\n" + "\n".join(map(str, violations))


def test_scan_reaches_every_guarded_root() -> None:
    # Without this, a typo in SCAN_ROOTS would scan nothing and pass.
    scanned = {f.relative_to(REPO_ROOT).as_posix() for f, _ in python_files(REPO_ROOT)}

    assert {
        "stages/ingest/__init__.py",
        "contracts/_base.py",
        "shared/__init__.py",
        "backend/app/main.py",
    } <= scanned


def test_fixtures_are_outside_the_real_scan() -> None:
    scanned = [f for f, _ in python_files(REPO_ROOT)]

    assert not [f for f in scanned if FIXTURES in f.parents]

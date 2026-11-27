"""The layering rules, enforced.

The point of ports and adapters is that the core never learns which adapter it
is talking to. That only stays true if something fails when a stray import
creeps in, so this walks every import in the package and checks it against the
rules below.

`KNOWN` lists violations that exist today and are scheduled to go. The test
fails if a *new* one appears, and also if a listed one disappears without being
removed from the list, so the list can only shrink.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "backend" / "saathi"

#: importer package -> packages it may import (itself is always allowed).
#: A package missing from this table is unchecked for now.
ALLOWED: dict[str, set[str]] = {
    "domain": set(),
    "ports": {"domain"},
    # Adapters implement ports; they may use the domain and each other's ports,
    # but never reach up into the HTTP layer or the composition root.
    "adapters": {"domain", "ports", "db", "ledger"},
    # The product core: pure decision logic and its helpers.
    "planner": {"domain", "ports", "graph", "readiness", "language"},
    "language": {"domain", "ports", "planner", "guide"},
    "readiness": {"domain"},
    "guide": {"domain"},
    "orchestrator": {"domain"},
    "graph": {"domain"},
    "engagement": {"domain"},
    "ledger": {"domain", "ports"},
    "consent": {"domain", "ports"},
}

#: Third-party packages the pure layers must not import.
INFRASTRUCTURE = {
    "fastapi",
    "starlette",
    "httpx",
    "sqlalchemy",
    "groq",
    "anthropic",
    "langgraph",
    "uvicorn",
}
PURE_LAYERS = {"domain", "ports"}

#: (importer module, imported top-level package) pairs that break the rules
#: today. Each one has a phase that removes it.
KNOWN: set[tuple[str, str]] = {
    # The planner still builds a default in-memory ledger when none is given.
    # Phase 2 moves ledger writes out of the planner.
    ("planner.graph", "ledger"),
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> list[tuple[str, str | None]]:
    """(top-level saathi package or third-party root, None) for each import."""
    module = _module_name(path)
    is_package = path.name == "__init__.py"
    pkg_parts = module.split(".") if module else []
    if not is_package:
        pkg_parts = pkg_parts[:-1]

    found: list[tuple[str, str | None]] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "saathi":
                    inner = alias.name.split(".")[1:2]
                    found.append((inner[0] if inner else "", "saathi"))
                else:
                    found.append((root, None))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                root = (node.module or "").split(".")[0]
                if root == "saathi":
                    inner = (node.module or "").split(".")[1:2]
                    found.append((inner[0] if inner else "", "saathi"))
                else:
                    found.append((root, None))
            else:
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                target = base + (node.module.split(".") if node.module else [])
                if target:
                    found.append((target[0], "saathi"))
                else:
                    # `from .. import name`: the package itself is the import
                    for alias in node.names:
                        found.append((alias.name, "saathi"))
    return found


def _violations() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        module = _module_name(path)
        layer = module.split(".")[0]
        if layer not in ALLOWED and layer not in PURE_LAYERS:
            continue
        for name, origin in _imports(path):
            if origin == "saathi":
                if name != layer and name not in ALLOWED.get(layer, set()):
                    out.add((module, name))
            elif layer in PURE_LAYERS and name in INFRASTRUCTURE:
                out.add((module, name))
    return out


def test_no_new_layering_violations():
    new = _violations() - KNOWN
    assert not new, (
        "layering violations (importer, imported):\n"
        + "\n".join(f"  {a} -> {b}" for a, b in sorted(new))
    )


def test_known_violations_are_still_real():
    gone = KNOWN - _violations()
    assert not gone, (
        "these are fixed — delete them from KNOWN:\n"
        + "\n".join(f"  {a} -> {b}" for a, b in sorted(gone))
    )


def test_the_pure_layers_import_nothing_from_the_product():
    """domain and ports are the contract; they depend on nothing that implements it."""
    offenders = [
        (m, n)
        for m, n in _violations()
        if m.split(".")[0] in PURE_LAYERS
    ]
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# The molecular register sits outside the logistics core.
#
# The package-level table above cannot express this, because the register
# lives in `domain` and `ports` — packages the planner is rightly allowed to
# import. The rule is about one module, not one package: a planner that read a
# molecular report and moved a visit because of it would be making a clinical
# decision dressed as a scheduling one, and the whole separation this project
# rests on would be gone with nothing failing.

#: Modules nobody in the decision path may import, however convenient.
CLINICAL_ONLY = {
    "domain.molecular",
    "ports.molecular",
    "adapters.molecular",
    "api.molecular",
}

#: Everything that decides when a family travels, or acts on that decision.
DECISION_PATH = {"planner", "orchestrator", "live", "engagement", "readiness", "graph"}


def _dotted_imports(path: Path) -> set[str]:
    """Every in-package module this file imports, as a dotted path under saathi."""
    module = _module_name(path)
    pkg_parts = module.split(".") if module else []
    if path.name != "__init__.py":
        pkg_parts = pkg_parts[:-1]

    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "saathi":
                    out.add(alias.name.split(".", 1)[1] if "." in alias.name else "")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                name = node.module or ""
                if name.split(".")[0] == "saathi":
                    out.add(name.split(".", 1)[1] if "." in name else "")
            else:
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                target = base + ((node.module or "").split(".") if node.module else [])
                out.add(".".join(target))
                # `from ..domain import molecular` names the module in the alias.
                for alias in node.names:
                    out.add(".".join([*target, alias.name]))
    return out


def test_the_decision_path_cannot_read_molecular_records():
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        module = _module_name(path)
        if module.split(".")[0] not in DECISION_PATH:
            continue
        for imported in _dotted_imports(path):
            if imported in CLINICAL_ONLY:
                offenders.append((module, imported))
    assert not offenders, (
        "the molecular register must stay out of the scheduling path — a visit "
        "moved because of a report is a clinical decision:\n"
        + "\n".join(f"  {a} -> {b}" for a, b in sorted(offenders))
    )


def test_the_molecular_rule_resolves_relative_imports():
    """The rule above is only worth having if its resolver actually works.

    `api/molecular.py` imports the register through a relative path — the same
    shape a stray planner import would take. If the resolver cannot see it
    here, it would not see it there either, and the rule would pass by being
    blind rather than by being obeyed.
    """
    seen = _dotted_imports(PACKAGE / "api" / "molecular.py")
    assert "domain.molecular" in seen, sorted(seen)

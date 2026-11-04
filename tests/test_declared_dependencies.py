"""Everything the backend imports is declared, so a clean install can start.

A dependency that is installed on a developer's machine but missing from
pyproject.toml passes every test and then crashes the deployed image at start.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: import name -> distribution name, where they differ.
DISTRIBUTION = {
    "jwt": "pyjwt",
    "argon2": "argon2-cffi",
    "pydantic_settings": "pydantic-settings",
    "multipart": "python-multipart",
}

#: Imported only inside an optional extra's adapter.
OPTIONAL = {"neo4j", "asyncpg", "psycopg"}


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    names = set()
    for requirement in project["dependencies"]:
        base = re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0]
        names.add(_normal(base))
    return names


def _imported() -> set[str]:
    found = set()
    for path in (ROOT / "backend" / "saathi").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found - set(sys.stdlib_module_names) - {"saathi"} - OPTIONAL


def test_every_third_party_import_is_a_declared_dependency():
    declared = _declared()
    missing = sorted(
        name for name in _imported() if _normal(DISTRIBUTION.get(name, name)) not in declared
    )

    assert not missing, f"imported by backend/saathi but not in pyproject.toml: {missing}"

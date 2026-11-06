"""Keep optional extras in the committed lock without requiring uv to run the tests."""

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def test_optional_extras_and_their_dependencies_are_locked():
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((BACKEND / "uv.lock").read_text(encoding="utf-8"))
    root = next(p for p in lock["package"] if p["name"] == project["name"])
    packages = {p["name"]: p for p in lock["package"]}
    extras = project.get("optional-dependencies", {})

    assert set(root["metadata"]["provides-extras"]) == set(extras)
    for extra, requirements in extras.items():
        locked = root["optional-dependencies"][extra]
        assert {_name(r) for r in requirements} == {entry["name"] for entry in locked}

        # Check transitive optional dependencies too (psycopg -> binary wheel + Windows tzdata).
        pending = [entry["name"] for entry in locked]
        visited = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            package = packages[name]
            pending.extend(dep["name"] for dep in package.get("dependencies", []))
            for dependencies in package.get("optional-dependencies", {}).values():
                pending.extend(dep["name"] for dep in dependencies)

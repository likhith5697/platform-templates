#!/usr/bin/env python3
"""Validate a routes.yaml file against the route schema and platform rules.

Usage: python validate_routes.py routes.yaml [more.yaml ...]
Exit code 0 if every file is valid, 1 otherwise. All errors are printed, not just the first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "schema" / "route.schema.json"
ALLOWED_AUTH = ("custom", "none")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_VALIDATOR = Draft202012Validator(load_schema())


def _label(routes: list, index: int) -> str:
    """'routes[2] (orders-get)' when the route has a name, else 'routes[2]'."""
    route = routes[index] if index < len(routes) else None
    name = route.get("name") if isinstance(route, dict) else None
    return f"routes[{index}] ({name})" if isinstance(name, str) else f"routes[{index}]"


def _schema_errors(data) -> list[str]:
    """Schema violations, rewritten into short messages."""
    errors = []
    routes = data.get("routes") if isinstance(data, dict) else None
    routes = routes if isinstance(routes, list) else []

    for err in sorted(_VALIDATOR.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        loc = list(err.absolute_path)  # e.g. ["routes", 0, "path"]
        where = _label(routes, loc[1]) if len(loc) >= 2 and loc[0] == "routes" else "file"
        field = loc[2] if len(loc) >= 3 else None

        if err.validator == "required":
            missing = err.message.split("'")[1]
            errors.append(f"{where}: missing field '{missing}'")
        elif err.validator == "additionalProperties" and isinstance(err.instance, dict):
            allowed = err.schema.get("properties", {})
            for extra in sorted(k for k in err.instance if k not in allowed):
                hint = " (set by the platform, not by routes)" if extra == "parentRefs" else ""
                errors.append(f"{where}: unknown field '{extra}'{hint}")
        elif field == "path" and err.validator == "pattern":
            errors.append(f"{where}: path {err.instance!r} must start with '/'")
        elif field == "auth" and err.validator == "enum":
            errors.append(
                f"{where}: unknown auth value {err.instance!r} (allowed: {', '.join(ALLOWED_AUTH)})"
            )
        elif field:
            errors.append(f"{where}: {field}: {err.message}")
        else:
            errors.append(f"{where}: {err.message}")
    return errors


def _rule_errors(routes: list) -> list[str]:
    """Rules JSON Schema can't express: unique method + path, and no auth 'none'."""
    errors = []
    seen: dict[tuple[str, str], int] = {}

    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            continue

        # Same path with different methods is fine (GET /orders vs POST /orders);
        # same method AND path is a conflict, matching API Gateway's unique route keys.
        method, path = route.get("method"), route.get("path")
        if isinstance(method, str) and isinstance(path, str):
            key = (method, path)
            if key in seen:
                errors.append(
                    f"{_label(routes, i)}: duplicate route '{method} {path}' "
                    f"(already used by {_label(routes, seen[key])})"
                )
            else:
                seen[key] = i

        if route.get("auth") == "none":
            errors.append(f"{_label(routes, i)}: auth 'none' is not allowed; use 'custom'")
    return errors


def validate_routes(data) -> list[str]:
    """Return a list of error messages for parsed routes data. Empty list means valid."""
    if not isinstance(data, dict):
        return ["file: expected a mapping with a 'routes' list"]
    errors = _schema_errors(data)
    routes = data.get("routes")
    if isinstance(routes, list):
        errors += _rule_errors(routes)
    return errors


def validate_file(path: str | Path) -> list[str]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"file not found: {path}"]
    except yaml.YAMLError as exc:
        return [f"invalid YAML: {exc}"]
    return validate_routes(data)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: validate_routes.py routes.yaml [more.yaml ...]", file=sys.stderr)
        return 2

    failed = False
    for path in argv:
        errors = validate_file(path)
        if errors:
            failed = True
            print(f"FAIL {path}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

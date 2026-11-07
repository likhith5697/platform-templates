#!/usr/bin/env python3
"""Render routes.yaml into Kubernetes Gateway API HTTPRoutes, one per entry.

Usage: python render_httproutes.py routes.yaml [-o httproutes.yaml]

The input is validated first (validate_routes.py); invalid input renders nothing and exits 1.
The platform, not the route author, decides which Gateway a route attaches to:
parentRefs always points at Gateway "public-gateway" in namespace "gateway-system".
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from validate_routes import validate_routes

# Injected into every HTTPRoute. Route entries cannot override these.
GATEWAY_NAME = "public-gateway"
GATEWAY_NAMESPACE = "gateway-system"

_PARAM = re.compile(r"\{[^/{}]+\}")  # "{id}" in "/orders/{id}"


class InvalidRoutesError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("invalid routes:\n" + "\n".join(f"  - {e}" for e in errors))
        self.errors = errors


def _parent_refs() -> list[dict]:
    """Built fresh each time, so callers can't mutate a shared value."""
    return [
        {
            "group": "gateway.networking.k8s.io",
            "kind": "Gateway",
            "name": GATEWAY_NAME,
            "namespace": GATEWAY_NAMESPACE,
        }
    ]


def _path_match(path: str) -> dict:
    """Literal paths match exactly; "{param}" segments become a one-segment regex."""
    if not _PARAM.search(path):
        return {"type": "Exact", "value": path}
    parts = _PARAM.split(path)
    regex = "[^/]+".join(re.escape(p) for p in parts)
    return {"type": "RegularExpression", "value": regex}


def render_route(route: dict) -> dict:
    """Build one HTTPRoute. Reads only the allowed fields, so any extra keys
    (parentRefs, hostnames, filters, ...) in the entry are ignored, never copied."""
    return {
        "apiVersion": "gateway.networking.k8s.io/v1",
        "kind": "HTTPRoute",
        "metadata": {
            "name": route["name"],
            "namespace": route["namespace"],
            "labels": {"app.kubernetes.io/managed-by": "render_httproutes"},
        },
        "spec": {
            "parentRefs": _parent_refs(),
            "rules": [
                {
                    "matches": [{"path": _path_match(route["path"]), "method": route["method"]}],
                    "backendRefs": [{"name": route["service"], "port": route["port"]}],
                }
            ],
        },
    }


def render(data) -> str:
    """Validate, then render every entry as a multi-document YAML string."""
    errors = validate_routes(data)
    if errors:
        raise InvalidRoutesError(errors)
    docs = [render_route(r) for r in data["routes"]]
    return yaml.safe_dump_all(docs, sort_keys=False, explicit_start=True, default_flow_style=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("routes_file")
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")
    args = parser.parse_args(argv)

    try:
        data = yaml.safe_load(Path(args.routes_file).read_text(encoding="utf-8"))
        out = render(data)
    except FileNotFoundError:
        print(f"file not found: {args.routes_file}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"invalid YAML: {exc}", file=sys.stderr)
        return 1
    except InvalidRoutesError as exc:
        print(f"refusing to render {args.routes_file}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

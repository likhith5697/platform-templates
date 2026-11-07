import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_routes import main, validate_file, validate_routes  # noqa: E402

VALID_ROUTE = {
    "name": "orders-list",
    "path": "/orders",
    "method": "GET",
    "namespace": "orders",
    "service": "orders",
    "port": 8080,
    "auth": "custom",
}


def make(*overrides):
    """Build {'routes': [...]}; each override dict is merged into a copy of VALID_ROUTE."""
    routes = []
    for i, o in enumerate(overrides or [{}]):
        r = copy.deepcopy(VALID_ROUTE)
        r["name"] = f"route-{i}"
        r["path"] = f"/r{i}"
        r.update(o)
        routes.append(r)
    return {"routes": routes}


def test_valid_routes_pass():
    assert validate_routes(make({}, {"path": "/orders/{id}", "method": "POST"})) == []


def test_example_file_is_valid():
    example = Path(__file__).resolve().parent.parent / "examples" / "routes.yaml"
    assert validate_file(example) == []


# --- duplicate method + path -------------------------------------------------

def test_same_path_different_methods_passes():
    assert validate_routes(
        make(
            {"path": "/orders", "method": "GET"},
            {"path": "/orders", "method": "POST"},
            {"path": "/orders", "method": "DELETE"},
        )
    ) == []


def test_rejects_same_method_and_path():
    errors = validate_routes(make({"path": "/orders"}, {"path": "/orders"}))
    assert errors == [
        "routes[1] (route-1): duplicate route 'GET /orders' (already used by routes[0] (route-0))"
    ]


def test_rejects_every_repeat_of_a_duplicate_route():
    errors = validate_routes(make({"path": "/a"}, {"path": "/a"}, {"path": "/a"}))
    assert len([e for e in errors if "duplicate route" in e]) == 2


def test_duplicate_only_flagged_for_matching_pair():
    errors = validate_routes(
        make(
            {"path": "/orders", "method": "GET"},
            {"path": "/orders", "method": "POST"},
            {"path": "/orders", "method": "POST"},
        )
    )
    assert errors == [
        "routes[2] (route-2): duplicate route 'POST /orders' (already used by routes[1] (route-1))"
    ]


# --- path must start with "/" -------------------------------------------------

@pytest.mark.parametrize("bad_path", ["orders", "", "orders/", " /orders"])
def test_rejects_path_not_starting_with_slash(bad_path):
    errors = validate_routes(make({"path": bad_path}))
    assert errors == [f"routes[0] (route-0): path {bad_path!r} must start with '/'"]


# --- unknown auth values ------------------------------------------------------

@pytest.mark.parametrize("bad_auth", ["jwt", "Custom", "", "basic"])
def test_rejects_unknown_auth_value(bad_auth):
    errors = validate_routes(make({"auth": bad_auth}))
    assert errors == [
        f"routes[0] (route-0): unknown auth value {bad_auth!r} (allowed: custom, none)"
    ]


# --- auth "none" --------------------------------------------------------------

def test_rejects_auth_none():
    errors = validate_routes(make({}, {"auth": "none"}))
    assert errors == ["routes[1] (route-1): auth 'none' is not allowed; use 'custom'"]


# --- missing fields -----------------------------------------------------------

@pytest.mark.parametrize("field", ["name", "path", "method", "namespace", "service", "port", "auth"])
def test_rejects_missing_field(field):
    data = make()
    del data["routes"][0][field]
    errors = validate_routes(data)
    label = "routes[0]" if field == "name" else "routes[0] (route-0)"
    assert errors == [f"{label}: missing field '{field}'"]


def test_rejects_missing_routes_key():
    assert validate_routes({}) == ["file: missing field 'routes'"]


# --- multiple problems are all reported; CLI exit codes ----------------------

def test_reports_all_errors_at_once():
    errors = validate_routes(make({"path": "x", "auth": "none"}, {"path": "/r1", "auth": "jwt"}))
    assert len(errors) == 3


def test_cli_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.yaml"
    good.write_text(
        "routes:\n  - {name: a, path: /a, method: GET, namespace: n, service: s, port: 80, auth: custom}\n"
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "routes:\n  - {name: a, path: a, method: GET, namespace: n, service: s, port: 80, auth: none}\n"
    )
    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "must start with '/'" in out and "auth 'none' is not allowed" in out

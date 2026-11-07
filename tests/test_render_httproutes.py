import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from render_httproutes import (  # noqa: E402
    GATEWAY_NAME,
    GATEWAY_NAMESPACE,
    InvalidRoutesError,
    main,
    render,
    render_route,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

EXPECTED_PARENT_REFS = [
    {
        "group": "gateway.networking.k8s.io",
        "kind": "Gateway",
        "name": "public-gateway",
        "namespace": "gateway-system",
    }
]


def route(**overrides):
    r = {
        "name": "orders-list",
        "path": "/orders",
        "method": "GET",
        "namespace": "orders",
        "service": "orders",
        "port": 8080,
        "auth": "custom",
    }
    r.update(overrides)
    return r


def load_fixture_routes():
    return yaml.safe_load((FIXTURES / "routes.yaml").read_text(encoding="utf-8"))


# --- golden file -------------------------------------------------------------

def test_output_matches_expected_yaml_exactly():
    expected = (FIXTURES / "expected_httproutes.yaml").read_text(encoding="utf-8")
    assert render(load_fixture_routes()) == expected


def test_output_matches_expected_yaml_structurally():
    expected = list(yaml.safe_load_all((FIXTURES / "expected_httproutes.yaml").read_text()))
    actual = list(yaml.safe_load_all(render(load_fixture_routes())))
    assert actual == expected
    assert len(actual) == 3  # one HTTPRoute per entry


def test_cli_writes_expected_file(tmp_path):
    out = tmp_path / "out.yaml"
    assert main([str(FIXTURES / "routes.yaml"), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == (FIXTURES / "expected_httproutes.yaml").read_text(
        encoding="utf-8"
    )


# --- what the entry controls vs what the script injects -----------------------

def test_entry_fields_map_to_httproute():
    doc = render_route(route(name="pay", namespace="payments", path="/pay", method="POST",
                             service="payments-api", port=9000))
    assert doc["metadata"] == {
        "name": "pay",
        "namespace": "payments",
        "labels": {"app.kubernetes.io/managed-by": "render_httproutes"},
    }
    rule = doc["spec"]["rules"][0]
    assert rule["matches"] == [{"path": {"type": "Exact", "value": "/pay"}, "method": "POST"}]
    assert rule["backendRefs"] == [{"name": "payments-api", "port": 9000}]


def test_parent_refs_always_injected():
    for doc in yaml.safe_load_all(render(load_fixture_routes())):
        assert doc["spec"]["parentRefs"] == EXPECTED_PARENT_REFS
    assert (GATEWAY_NAME, GATEWAY_NAMESPACE) == ("public-gateway", "gateway-system")


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/orders", {"type": "Exact", "value": "/orders"}),
        ("/orders/{id}", {"type": "RegularExpression", "value": "/orders/[^/]+"}),
        ("/a/{x}/b/{y}", {"type": "RegularExpression", "value": "/a/[^/]+/b/[^/]+"}),
        ("/v1.0/{id}", {"type": "RegularExpression", "value": r"/v1\.0/[^/]+"}),
    ],
)
def test_path_match_types(path, expected):
    assert render_route(route(path=path))["spec"]["rules"][0]["matches"][0]["path"] == expected


# --- a route cannot set its own parentRefs -----------------------------------

def test_route_cannot_set_its_own_parent_refs():
    attacker_refs = [{"name": "internal-admin-gateway", "namespace": "kube-system"}]
    data = {"routes": [route(parentRefs=attacker_refs)]}

    # 1. The validator rejects the unknown key, so nothing is rendered.
    with pytest.raises(InvalidRoutesError) as exc:
        render(data)
    assert exc.value.errors == [
        "routes[0] (orders-list): unknown field 'parentRefs' (set by the platform, not by routes)"
    ]

    # 2. Even if validation were bypassed, the renderer never copies the key:
    #    parentRefs still points at the platform Gateway.
    doc = render_route(route(parentRefs=attacker_refs))
    assert doc["spec"]["parentRefs"] == EXPECTED_PARENT_REFS
    assert "internal-admin-gateway" not in yaml.safe_dump(doc)


# --- invalid input is refused ------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        {"routes": [route(path="orders")]},
        {"routes": [route(auth="none")]},
        {"routes": [route(), route(name="dup")]},  # same GET /orders twice
        {"routes": [{k: v for k, v in route().items() if k != "port"}]},
    ],
)
def test_refuses_to_render_invalid_input(bad):
    with pytest.raises(InvalidRoutesError):
        render(bad)


def test_cli_refuses_invalid_file_and_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"routes": [route(auth="none")]}))
    out = tmp_path / "out.yaml"
    assert main([str(bad), "-o", str(out)]) == 1
    assert not out.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refusing to render" in captured.err and "auth 'none'" in captured.err

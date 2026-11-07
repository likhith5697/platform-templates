# platform-templates

Schema and validator for gateway route files (`routes.yaml`).

## Files

| File | What it is |
|---|---|
| `schema/route.schema.json` | JSON Schema (draft 2020-12) for a routes file and each route entry. |
| `validate_routes.py` | CLI and library: checks a routes.yaml against the schema plus platform rules. |
| `tests/test_validate_routes.py` | Unit tests, at least one for each rejection rule. |
| `examples/routes.yaml` | A valid example for the orders service. |
| `render_httproutes.py` | Renders routes.yaml into Gateway API HTTPRoutes (validates first). |
| `tests/test_render_httproutes.py` | Golden-file tests (`tests/fixtures/`), plus a test that routes can't set parentRefs. |

## Route entry

```yaml
routes:
  - name: orders-get        # lowercase, digits, dashes
    path: /orders/{id}      # must start with "/"
    method: GET             # GET POST PUT PATCH DELETE HEAD OPTIONS; method + path must be unique
    namespace: orders       # Kubernetes namespace
    service: orders         # Kubernetes Service name
    port: 8080              # 1-65535
    auth: custom            # known values: custom, none; "none" is rejected
```

## What gets rejected

| Rule | Example error |
|---|---|
| Missing field | `routes[4] (e): missing field 'port'` |
| Path doesn't start with `/` | `routes[2] (c): path 'health' must start with '/'` |
| Unknown auth value | `routes[3] (d): unknown auth value 'jwt' (allowed: custom, none)` |
| `auth: none` on any route | `routes[2] (c): auth 'none' is not allowed; use 'custom'` |
| Same method AND path twice | `routes[1] (b): duplicate route 'GET /orders' (already used by routes[0] (a))` |

The schema also rejects wrong types, unknown fields, bad methods and ports outside 1–65535. Every error in a file is reported, not just the first.

**Duplicates:** a route is a duplicate only when both its method AND path match another route, the same rule API Gateway uses for route keys. `GET /orders` and `POST /orders` together are fine; two `GET /orders` entries are rejected. Paths are compared exactly, so `/orders` and `/orders/` are different.

## Render Gateway API HTTPRoutes

`render_httproutes.py` turns each routes.yaml entry into one Kubernetes Gateway API `HTTPRoute` (`gateway.networking.k8s.io/v1`).

```bash
python render_httproutes.py examples/routes.yaml                  # to stdout
python render_httproutes.py examples/routes.yaml -o httproutes.yaml
kubectl apply -f httproutes.yaml
```

| HTTPRoute field | Comes from |
|---|---|
| `metadata.name` / `metadata.namespace` | entry `name` / `namespace` |
| `rules[].matches[].path` + `method` | entry `path` + `method` |
| `rules[].backendRefs[]` | entry `service` + `port` |
| **`spec.parentRefs`** | **always injected by the script**: Gateway `public-gateway` in `gateway-system` |

- **Validated first.** The validator runs before anything is rendered. Invalid input prints the errors to stderr, exits 1, and writes nothing.
- **Routes can't pick their Gateway.** A `parentRefs` key in an entry fails validation (`unknown field 'parentRefs'`), and the renderer only ever reads the allowed fields.
- **Path matching.** Literal paths become an `Exact` match. Paths with `{param}` become a `RegularExpression` that matches one segment (`/orders/{id}` → `/orders/[^/]+`); regex matching is implementation-specific in Gateway API, so check your controller supports it.
- **Not rendered:** `auth` is enforced at the API Gateway layer, not in the HTTPRoute.
- **Gateway requirement:** `public-gateway` must allow routes from other namespaces (`allowedRoutes.namespaces.from: All` or a selector), or the routes won't attach.

## Reusable workflow: trigger-apply

`.github/workflows/trigger-apply.yml` (`workflow_call`) sends a single `repository_dispatch` event, type `trigger-apply`, to `likhith5697/gateway-infra`:

```json
{ "event_type": "trigger-apply", "client_payload": { "sha": "<caller commit SHA>", "repo": "<owner/caller-repo>" } }
```

It holds no AWS credentials, uses no third-party actions, and sets `permissions: {}`. gateway-infra decides what to apply.

### How routes-repo calls it

Add this file to **routes-repo**:

```yaml
# routes-repo/.github/workflows/trigger-apply.yml
name: trigger-apply

on:
  push:
    branches: [main]          # only merged changes trigger an apply
    paths: [routes.yaml]      # and only when the routes actually changed

permissions: {}               # the caller needs no GITHUB_TOKEN permissions either

jobs:
  trigger-apply:
    uses: likhith5697/platform-templates/.github/workflows/trigger-apply.yml@v0.1.0
    secrets:
      dispatch_token: ${{ secrets.GATEWAY_INFRA_DISPATCH_TOKEN }}
```

One-time setup in routes-repo:
1. Settings → Secrets and variables → Actions → **New repository secret** named `GATEWAY_INFRA_DISPATCH_TOKEN`, holding the token described below.
2. Merge a change to `routes.yaml` on `main`. gateway-infra then receives `trigger-apply` with `{sha, repo: "likhith5697/routes-repo"}`.

**Versioning:** callers pin to a tag (`@v0.1.0`). Use a full commit SHA for an immutable pin. Avoid `@main`: a change to this repo would instantly change what runs in every caller.

### The token

The built-in `GITHUB_TOKEN` can't be used: it only works on the repo that's running the workflow, and it can't trigger workflows in another repo. Use a **fine-grained personal access token**:

| Setting | Value |
|---|---|
| Resource owner | `likhith5697` |
| Repository access | **Only select repositories → `gateway-infra`** |
| Repository permissions | **Contents: Read and write** (Metadata: Read-only is added automatically) |
| Everything else | No access |
| Expiration | Short, e.g. 90 days; rotate it |

Store it as a secret named `GATEWAY_INFRA_DISPATCH_TOKEN` in each **calling** repo (not in platform-templates).

**Why Contents: write.** That's the permission GitHub requires for `POST /repos/{owner}/{repo}/dispatches`, and there's no narrower one. It also allows pushing to gateway-infra, so protect `main` there with a ruleset that requires pull requests and has **no bypass list**. A PAT acts as you, the repo owner, and owners can bypass rules unless the bypass list is empty. That way a leaked token can trigger runs but can't change code on `main`.
**Stronger option:** a GitHub App installed only on gateway-infra with Contents: write. Its tokens expire after 1 hour, instead of a long-lived PAT.

## Run

```bash
pip install -r requirements.txt
python validate_routes.py examples/routes.yaml        # exit 0 = valid, 1 = invalid
python -m pytest -q                                  # run tests
```

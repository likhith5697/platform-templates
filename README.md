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
| `.github/workflows/validate.yml` | Reusable: validate + dry-run render + terraform fmt/validate for a caller's routes.yaml. |
| `.github/workflows/trigger-apply.yml` | Reusable: notifies gateway-infra (repository_dispatch) after a merge. |
| `.github/workflows/ci.yml` | This repo's CI: dogfoods validate.yml, pytest, terraform test, release guard. |
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

## Reusable workflow: validate (v0.1.1+)

`.github/workflows/validate.yml` (`workflow_call`) checks a caller's routes file with this repo's tools. It's read-only: no secrets, `contents: read`.

1. Checks out the **caller's** repo at the caller's commit.
2. Checks out **platform-templates at `templates_ref`** (default = this file's own release tag), so `@v0.1.1` runs v0.1.1's validator and modules, never `main`.
3. Runs `validate_routes.py` on `routes_file` (default `routes.yaml`).
4. Runs `render_httproutes.py` as a **dry run**, writing the HTTPRoutes to the job summary without applying them.
5. Runs `terraform fmt -check` and `terraform validate` on every module in `modules/`.

| Input | Default | Notes |
|---|---|---|
| `routes_file` | `routes.yaml` | Relative path inside the caller repo (no `..`, no absolute paths) |
| `templates_ref` | the release tag (e.g. `v0.1.1`) | Leave it. Only this repo's own CI overrides it, with the commit under test |

**Why the version is written into the file:** a reusable workflow can't discover which commit of itself is running (there is no `github` context property for it), so `templates_ref` defaults to the release tag. `ci.yml` has a **release guard**: pushing tag `vX.Y.Z` fails unless that default equals `vX.Y.Z`.

## Reusable workflow: trigger-apply

`.github/workflows/trigger-apply.yml` (`workflow_call`) sends a single `repository_dispatch` event, type `trigger-apply`, to `likhith5697/gateway-infra`:

```json
{ "event_type": "trigger-apply", "client_payload": { "sha": "<caller commit SHA>", "repo": "<owner/caller-repo>" } }
```

It holds no AWS credentials, uses no third-party actions, and sets `permissions: {}`. gateway-infra decides what to apply.

### How routes-repo calls both workflows

```yaml
# routes-repo/.github/workflows/ci.yml
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  validate:                                   # every PR
    if: github.event_name == 'pull_request'
    uses: likhith5697/platform-templates/.github/workflows/validate.yml@v0.1.1
  trigger-apply:                              # merged to main
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    uses: likhith5697/platform-templates/.github/workflows/trigger-apply.yml@v0.1.1
    secrets:
      dispatch_token: ${{ secrets.GATEWAY_INFRA_DISPATCH_TOKEN }}
```

One-time setup in routes-repo:
1. Settings → Secrets and variables → Actions → **New repository secret** named `GATEWAY_INFRA_DISPATCH_TOKEN`, holding the token described below.
2. Branch protection on `main`: require PRs, and require the `validate` check.

## Versioning and pinning

Releases are **immutable tags**. A published tag is never moved or re-created; fixes ship as a new tag.

| Version | Contents |
|---|---|
| `v0.1.0` | schema, validator, renderer, `api-gateway-routes` module, `trigger-apply.yml` |
| `v0.1.1` | + `validate.yml` (reusable), `ci.yml` (pytest, terraform test, release guard) |

How a caller pins, from most to least strict:

```yaml
# 1. Commit SHA: immutable even if someone moved the tag. Keep the tag in a comment for humans/Dependabot.
uses: likhith5697/platform-templates/.github/workflows/validate.yml@<full-40-char-sha> # v0.1.1

# 2. Tag: readable; fine for repos you control (protect tags with a ruleset so v* can't be moved or deleted).
uses: likhith5697/platform-templates/.github/workflows/validate.yml@v0.1.1

# 3. Branch: DON'T. Every push here would instantly change what runs in every caller.
uses: likhith5697/platform-templates/.github/workflows/validate.yml@main
```

- **Get a tag's commit SHA:** `git ls-remote https://github.com/likhith5697/platform-templates.git 'refs/tags/v0.1.1^{}'`
- **Terraform module consumers pin the same way:** `source = "github.com/likhith5697/platform-templates//modules/api-gateway-routes?ref=v0.1.1"` (or `?ref=<sha>`).
- **Upgrading is a deliberate PR in the caller:** bump `@v0.1.0` to `@v0.1.1` and let CI run.

**Release checklist:**
1. Bump the `templates_ref` default in `validate.yml` to the new tag.
2. Merge.
3. `git tag -a vX.Y.Z -m ... && git push origin vX.Y.Z`.
4. `ci.yml`'s release guard confirms the version in the file matches the tag.

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

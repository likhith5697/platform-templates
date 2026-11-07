# api-gateway-routes

Creates API Gateway **HTTP API** routes and private integrations from a list of route entries (the same shape as `routes.yaml`), one of each per route, using `for_each`.

```
client -> HTTP API route ("GET /orders/{id}") -> [Lambda authorizer if auth = custom]
       -> integration (HTTP_PROXY over VPC Link) -> internal ALB/NLB listener -> service
```

## Inputs

| Name | Description |
|---|---|
| `api_id` | Existing HTTP API ID. |
| `routes` | List of `{name, path, method, namespace, service, port, auth}`. Names must be unique, each method + path must be unique, paths must start with `/`, and auth must be `custom` or `none`. |
| `authorizer_id` | Lambda authorizer ID, attached to every `auth = "custom"` route. Required if any route uses `custom`. |
| `vpc_link_id` | API Gateway VPC Link ID. |
| `listener_arn` | ARN of the internal load balancer listener. |

## Outputs

`route_ids`, `integration_ids` and `route_keys`, each a map keyed by route name.

## Behaviour

- **auth = custom:** `authorization_type = CUSTOM` with your authorizer. **auth = none:** an open route. The policy that bans `none` lives in `validate_routes.py`; the module just maps the value.
- **Path and headers:** the original path is passed through unchanged. Each integration sets `x-backend-namespace`, `x-backend-service` and `x-backend-port` headers, so the load balancer or ingress behind the listener can route by them.
- **for_each keys:** routes are keyed by `name`, so renaming a route re-creates it. Adding or removing one route leaves the others untouched.

## Usage

```hcl
module "orders_routes" {
  source = "github.com/likhith5697/platform-templates//modules/api-gateway-routes"

  api_id        = aws_apigatewayv2_api.gateway.id
  authorizer_id = aws_apigatewayv2_authorizer.lambda.id
  vpc_link_id   = aws_apigatewayv2_vpc_link.this.id
  listener_arn  = aws_lb_listener.internal.arn
  routes        = yamldecode(file("routes.yaml")).routes
}
```

A runnable example with placeholder IDs is in `examples/api-gateway-routes/`. It's for `validate` only.

## Verify (no AWS calls, nothing applied)

```bash
terraform init -backend=false && terraform validate
terraform test     # 6 tests with a mocked AWS provider
```

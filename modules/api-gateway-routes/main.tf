locals {
  # Keyed by route name, so adding or removing one route never re-creates the others.
  routes = { for r in var.routes : r.name => r }
}

# One private integration per route: API Gateway -> VPC Link -> internal load balancer listener.
# The original path is passed through, and the backend headers tell the load balancer or ingress where to send it.
resource "aws_apigatewayv2_integration" "this" {
  for_each = local.routes

  api_id      = var.api_id
  description = "${each.value.method} ${each.value.path} -> ${each.value.service}.${each.value.namespace}:${each.value.port}"

  integration_type       = "HTTP_PROXY"
  integration_method     = upper(each.value.method)
  integration_uri        = var.listener_arn
  connection_type        = "VPC_LINK"
  connection_id          = var.vpc_link_id
  payload_format_version = "1.0" # the only version HTTP_PROXY supports

  request_parameters = {
    "overwrite:header.x-backend-namespace" = each.value.namespace
    "overwrite:header.x-backend-service"   = each.value.service
    "overwrite:header.x-backend-port"      = tostring(each.value.port)
  }
}

# The route itself ("GET /orders/{id}"), pointing at its integration.
# auth = "custom" attaches the Lambda authorizer; auth = "none" leaves the route open.
resource "aws_apigatewayv2_route" "this" {
  for_each = local.routes

  api_id    = var.api_id
  route_key = "${upper(each.value.method)} ${each.value.path}"
  target    = "integrations/${aws_apigatewayv2_integration.this[each.key].id}"

  authorization_type = each.value.auth == "custom" ? "CUSTOM" : "NONE"
  authorizer_id      = each.value.auth == "custom" ? var.authorizer_id : null

  lifecycle {
    precondition {
      condition     = each.value.auth != "custom" || var.authorizer_id != null
      error_message = "Route ${each.key} has auth = \"custom\" but no authorizer_id was passed to the module."
    }
  }
}

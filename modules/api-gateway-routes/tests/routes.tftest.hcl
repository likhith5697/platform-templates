# Run with: terraform test   (uses a mocked AWS provider: no credentials, nothing is created)

mock_provider "aws" {}

variables {
  api_id        = "api123"
  authorizer_id = "auth123"
  vpc_link_id   = "vlink123"
  listener_arn  = "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/internal/abc/def"
  routes = [
    { name = "orders-create", path = "/orders", method = "POST", namespace = "orders", service = "orders", port = 8080, auth = "custom" },
    { name = "orders-list", path = "/orders", method = "GET", namespace = "orders", service = "orders", port = 8080, auth = "none" },
  ]
}

run "custom_auth_attaches_authorizer" {
  command = plan

  assert {
    condition     = aws_apigatewayv2_route.this["orders-create"].authorization_type == "CUSTOM"
    error_message = "auth=custom should give authorization_type CUSTOM"
  }
  assert {
    condition     = aws_apigatewayv2_route.this["orders-create"].authorizer_id == "auth123"
    error_message = "auth=custom should attach the authorizer"
  }
  assert {
    condition     = aws_apigatewayv2_route.this["orders-list"].authorization_type == "NONE"
    error_message = "auth=none should give authorization_type NONE"
  }
  assert {
    condition     = aws_apigatewayv2_route.this["orders-create"].route_key == "POST /orders"
    error_message = "route_key should be 'METHOD path'"
  }
}

run "integration_targets_vpc_link_and_listener" {
  command = plan

  assert {
    condition = alltrue([for i in aws_apigatewayv2_integration.this :
    i.connection_type == "VPC_LINK" && i.connection_id == "vlink123" && i.integration_uri == var.listener_arn])
    error_message = "every integration should go through the VPC link to the listener"
  }
  assert {
    condition     = aws_apigatewayv2_integration.this["orders-create"].request_parameters["overwrite:header.x-backend-service"] == "orders"
    error_message = "backend service header should be set"
  }
}

run "rejects_custom_auth_without_authorizer" {
  command = plan
  variables { authorizer_id = null }
  expect_failures = [aws_apigatewayv2_route.this]
}

run "rejects_duplicate_method_and_path" {
  command = plan
  variables {
    routes = [
      { name = "a", path = "/x", method = "GET", namespace = "n", service = "s", port = 80, auth = "custom" },
      { name = "b", path = "/x", method = "GET", namespace = "n", service = "s", port = 80, auth = "custom" },
    ]
  }
  expect_failures = [var.routes]
}

run "rejects_unknown_auth" {
  command = plan
  variables {
    routes = [{ name = "a", path = "/x", method = "GET", namespace = "n", service = "s", port = 80, auth = "jwt" }]
  }
  expect_failures = [var.routes]
}

run "rejects_path_without_slash" {
  command = plan
  variables {
    routes = [{ name = "a", path = "x", method = "GET", namespace = "n", service = "s", port = 80, auth = "custom" }]
  }
  expect_failures = [var.routes]
}

output "route_ids" {
  description = "Route name => API Gateway route ID."
  value       = { for k, r in aws_apigatewayv2_route.this : k => r.id }
}

output "integration_ids" {
  description = "Route name => API Gateway integration ID."
  value       = { for k, i in aws_apigatewayv2_integration.this : k => i.id }
}

output "route_keys" {
  description = "Route name => route key, e.g. \"GET /orders/{id}\"."
  value       = { for k, r in aws_apigatewayv2_route.this : k => r.route_key }
}

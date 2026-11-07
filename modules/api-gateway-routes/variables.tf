variable "api_id" {
  description = "ID of the existing API Gateway HTTP API (aws_apigatewayv2_api, protocol_type = HTTP)."
  type        = string
}

variable "routes" {
  description = "Route entries, same shape as platform-templates/schema/route.schema.json."
  type = list(object({
    name      = string
    path      = string
    method    = string
    namespace = string
    service   = string
    port      = number
    auth      = string
  }))

  validation {
    condition     = length(distinct([for r in var.routes : r.name])) == length(var.routes)
    error_message = "Route names must be unique (they are the for_each keys)."
  }

  validation {
    condition     = length(distinct([for r in var.routes : "${upper(r.method)} ${r.path}"])) == length(var.routes)
    error_message = "Each method + path pair must be unique (API Gateway route keys can't repeat)."
  }

  validation {
    condition     = alltrue([for r in var.routes : startswith(r.path, "/")])
    error_message = "Every path must start with '/'."
  }

  validation {
    condition     = alltrue([for r in var.routes : contains(["custom", "none"], r.auth)])
    error_message = "auth must be \"custom\" or \"none\"."
  }
}

variable "authorizer_id" {
  description = "ID of the Lambda (REQUEST) authorizer on this API. Attached to every route with auth = \"custom\"."
  type        = string
  default     = null
}

variable "vpc_link_id" {
  description = "ID of the API Gateway VPC Link (aws_apigatewayv2_vpc_link) into the VPC."
  type        = string
}

variable "listener_arn" {
  description = "ARN of the internal ALB or NLB listener that the VPC Link forwards to."
  type        = string
}

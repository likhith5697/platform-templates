# Example root module: feeds examples/routes.yaml into the module.
# The IDs below are placeholders, used only for `terraform validate`. Do not apply.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.72.0"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}

locals {
  # Same file that validate_routes.py checks.
  routes = yamldecode(file("${path.module}/../routes.yaml")).routes
}

module "orders_routes" {
  source = "../../modules/api-gateway-routes"

  api_id        = "abc123defg"
  authorizer_id = "auth12"
  vpc_link_id   = "vlink1"
  listener_arn  = "arn:aws:elasticloadbalancing:us-east-2:123456789012:listener/app/internal-alb/0123456789abcdef/0123456789abcdef"
  routes        = local.routes
}

output "route_keys" {
  value = module.orders_routes.route_keys
}

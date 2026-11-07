terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to the 6.72.x patch line; the root module's lock file pins the exact build.
      version = "~> 6.72.0"
    }
  }
}

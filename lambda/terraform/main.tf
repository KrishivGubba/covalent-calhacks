# Terraform configuration for AI Gateway Lambda
# 
# Usage:
#   cd lambda/terraform
#   terraform init
#   terraform plan
#   terraform apply
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Terraform installed (v1.0+)

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Uncomment to use S3 backend for state management
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "covalent/ai-gateway/terraform.tfstate"
  #   region = "us-west-2"
  # }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "covalent"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Variables
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 256
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "covalent-ai-gateway-lambda-role-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for Bedrock access
resource "aws_iam_role_policy" "bedrock_policy" {
  name = "bedrock-access"
  role = aws_iam_role.lambda_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.*",
          "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.*"
        ]
      }
    ]
  })
}

# CloudWatch Logs policy
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda function
resource "aws_lambda_function" "ai_gateway" {
  function_name = "covalent-ai-gateway"
  role          = aws_iam_role.lambda_role.arn
  handler       = "ai-gateway.lambda_handler"
  runtime       = "python3.11"
  memory_size   = var.lambda_memory
  timeout       = var.lambda_timeout
  
  # Placeholder - actual code deployed via GitHub Actions
  filename = data.archive_file.lambda_placeholder.output_path
  
  environment {
    variables = {
      BEDROCK_REGION      = var.aws_region
      DEFAULT_MODEL       = "anthropic.claude-sonnet-4-20250514-v1:0"
      DEFAULT_MAX_TOKENS  = "4096"
      DEFAULT_TEMPERATURE = "0.7"
    }
  }
  
  lifecycle {
    ignore_changes = [
      # Ignore code changes - handled by GitHub Actions
      filename,
      source_code_hash,
    ]
  }
}

# Placeholder zip for initial deployment
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  
  source {
    content  = "def lambda_handler(event, context): return {'statusCode': 200, 'body': 'Placeholder'}"
    filename = "ai-gateway.py"
  }
}

# Lambda Function URL (simpler than API Gateway for basic use cases)
resource "aws_lambda_function_url" "ai_gateway_url" {
  function_name      = aws_lambda_function.ai_gateway.function_name
  authorization_type = "NONE"  # TODO: Change to AWS_IAM for production
  
  cors {
    allow_credentials = false
    allow_origins     = ["*"]  # TODO: Restrict in production
    allow_methods     = ["POST", "GET", "OPTIONS"]
    allow_headers     = ["Content-Type", "Authorization"]
    max_age           = 86400
  }
}

# Optional: API Gateway for more control
resource "aws_apigatewayv2_api" "ai_gateway" {
  name          = "covalent-ai-gateway-${var.environment}"
  protocol_type = "HTTP"
  
  cors_configuration {
    allow_origins = ["*"]  # TODO: Restrict in production
    allow_methods = ["POST", "GET", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.ai_gateway.id
  name        = "$default"
  auto_deploy = true
  
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_logs.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/apigateway/covalent-ai-gateway-${var.environment}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id             = aws_apigatewayv2_api.ai_gateway.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.ai_gateway.invoke_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "invoke" {
  api_id    = aws_apigatewayv2_api.ai_gateway.id
  route_key = "POST /invoke"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.ai_gateway.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.ai_gateway.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ai_gateway.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ai_gateway.execution_arn}/*/*"
}

# Outputs
output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.ai_gateway.function_name
}

output "lambda_function_url" {
  description = "Lambda Function URL (direct)"
  value       = aws_lambda_function_url.ai_gateway_url.function_url
}

output "api_gateway_url" {
  description = "API Gateway URL"
  value       = aws_apigatewayv2_api.ai_gateway.api_endpoint
}

output "lambda_role_arn" {
  description = "Lambda IAM role ARN (for GitHub Actions OIDC)"
  value       = aws_iam_role.lambda_role.arn
}

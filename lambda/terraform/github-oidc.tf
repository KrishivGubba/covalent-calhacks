# GitHub OIDC provider for keyless AWS authentication
#
# This allows GitHub Actions to assume an IAM role without storing
# long-lived AWS credentials as secrets.

variable "github_org" {
  description = "GitHub organization or username"
  type        = string
  default     = "your-github-org"  # TODO: Update this
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "covalent-calhacks"
}

# GitHub OIDC Provider (create only once per AWS account)
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
  
  client_id_list = ["sts.amazonaws.com"]
  
  # GitHub's OIDC thumbprint
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# IAM Role for GitHub Actions
resource "aws_iam_role" "github_actions" {
  name = "covalent-github-actions-${var.environment}"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            # Only allow this repo's workflows to assume the role
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })
}

# Policy allowing GitHub Actions to deploy Lambda
resource "aws_iam_role_policy" "github_actions_lambda" {
  name = "lambda-deploy"
  role = aws_iam_role.github_actions.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaUpdate"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:PublishVersion"
        ]
        Resource = aws_lambda_function.ai_gateway.arn
      },
      {
        Sid    = "LambdaWait"
        Effect = "Allow"
        Action = [
          "lambda:GetFunction"
        ]
        Resource = aws_lambda_function.ai_gateway.arn
      }
    ]
  })
}

output "github_actions_role_arn" {
  description = "ARN to use in GitHub Actions (set as AWS_ROLE_ARN secret)"
  value       = aws_iam_role.github_actions.arn
}

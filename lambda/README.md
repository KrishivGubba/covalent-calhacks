# AI Gateway Lambda

AWS Lambda function that serves as a secure gateway for LLM requests to AWS Bedrock.

## Why?

Desktop apps can't safely store API credentials. This Lambda acts as a secure proxy:
- Desktop app → Lambda → Bedrock
- No API keys in the client
- Centralized rate limiting and logging
- Model allowlisting for cost control

## API

### POST /invoke

Invoke a Bedrock model.

```json
{
  "model": "anthropic.claude-sonnet-4-20250514-v1:0",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "system": "You are a helpful assistant.",
  "max_tokens": 4096,
  "temperature": 0.7
}
```

Response:
```json
{
  "content": "Hello! How can I help you today?",
  "model": "anthropic.claude-sonnet-4-20250514-v1:0",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 8
  },
  "stop_reason": "end_turn"
}
```

### GET /health

Health check endpoint.

## Deployment

### Option 1: Terraform (Recommended)

```bash
cd lambda/terraform

# Update variables
# - github_org in github-oidc.tf
# - aws_region in main.tf

terraform init
terraform plan
terraform apply
```

This creates:
- Lambda function
- IAM role with Bedrock permissions
- API Gateway HTTP API
- Lambda Function URL
- GitHub OIDC for keyless deployments

### Option 2: Manual Setup

1. **Create Lambda function:**
   ```bash
   # Package
   cd lambda
   pip install -r requirements.txt -t package/
   cp ai-gateway.py budget_metadata.py package/
   cd package && zip -r ../deployment.zip . && cd ..
   
   # Create function (AWS Console or CLI)
   aws lambda create-function \
     --function-name covalent-ai-gateway \
     --runtime python3.11 \
     --handler ai-gateway.lambda_handler \
     --role <YOUR_LAMBDA_ROLE_ARN> \
     --zip-file fileb://deployment.zip \
     --timeout 60 \
     --memory-size 256
   ```

2. **Create IAM role** with this policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "bedrock:InvokeModel",
           "bedrock:InvokeModelWithResponseStream",
           "bedrock:Converse",
           "bedrock:ConverseStream"
         ],
         "Resource": [
           "arn:aws:bedrock:us-west-2::foundation-model/anthropic.*",
           "arn:aws:bedrock:us-west-2::foundation-model/amazon.*"
         ]
       }
     ]
   }
   ```

3. **Add Lambda Function URL** or API Gateway

### GitHub Actions Setup

The workflow at `.github/workflows/deploy-lambda.yml` auto-deploys on push to `lambda/`.

**Required secrets:**

For OIDC (recommended):
- `AWS_ROLE_ARN` - Output from Terraform: `github_actions_role_arn`

Or for access keys:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_REGION` | `us-west-2` | AWS region for Bedrock |
| `DEFAULT_MODEL` | `anthropic.claude-sonnet-4-20250514-v1:0` | Default model |
| `DEFAULT_MAX_TOKENS` | `4096` | Default max tokens |
| `DEFAULT_TEMPERATURE` | `0.7` | Default temperature |

## Allowed Models

For security, only these models are allowed:

**Claude 3.5/4:**
- `anthropic.claude-sonnet-4-20250514-v1:0`
- `anthropic.claude-3-5-sonnet-20241022-v2:0`
- `anthropic.claude-3-5-haiku-20241022-v1:0`

**Claude 3:**
- `anthropic.claude-3-opus-20240229-v1:0`
- `anthropic.claude-3-sonnet-20240229-v1:0`
- `anthropic.claude-3-haiku-20240307-v1:0`

**Amazon Titan:**
- `amazon.titan-text-express-v1`
- `amazon.titan-text-lite-v1`

To add models, edit `ALLOWED_MODELS` in `ai-gateway.py`.

## Local Testing

```bash
# Test the handler locally (requires AWS credentials)
cd lambda
python -c "
import importlib
ai_gateway = importlib.import_module('ai-gateway')
print(ai_gateway.handle_health())
"
```

## TODO

- [ ] Add JWT authentication
- [ ] Add request logging to CloudWatch/S3
- [ ] Add cost tracking per user
- [ ] Add streaming support
- [ ] Add rate limiting

#!/bin/bash
# Deploy script for AI Gateway Lambda
#
# Usage:
#   ./deploy.sh [function-name]
#
# If function-name is not provided, defaults to 'covalent-ai-gateway'

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FUNCTION_NAME="${1:-covalent-ai-gateway}"

echo "=========================================="
echo "AI Gateway Lambda Deployment"
echo "=========================================="
echo "Function: $FUNCTION_NAME"
echo ""

# Step 1: Install dependencies
echo "Step 1: Installing dependencies..."
cd "$SCRIPT_DIR"
pip install -r requirements.txt -t package/ --quiet --upgrade
echo "  ✓ Dependencies installed"

# Step 2: Copy Lambda code
echo "Step 2: Copying Lambda code..."
cp ai-gateway.py package/
echo "  ✓ Code copied"

# Step 3: Create deployment zip
echo "Step 3: Creating deployment zip..."
cd package
rm -f ../deployment.zip
zip -r ../deployment.zip . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*" > /dev/null
cd ..
echo "  ✓ Created deployment.zip ($(du -h deployment.zip | cut -f1))"

# Step 4: Deploy to AWS
echo "Step 4: Deploying to AWS Lambda..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://deployment.zip \
    --output text > /dev/null

echo "  ✓ Code deployed"

# Step 5: Wait for update to complete
echo "Step 5: Waiting for function to be ready..."
aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "  ✓ Function ready"

# Step 6: Update environment variables via Terraform (optional)
echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "Note: If you need to update environment variables (AUTH0_DOMAIN, etc.),"
echo "run: cd terraform && terraform apply"
echo ""

# Get the function URL
FUNCTION_URL=$(aws lambda get-function-url-config --function-name "$FUNCTION_NAME" --query 'FunctionUrl' --output text 2>/dev/null || echo "")
if [ -n "$FUNCTION_URL" ]; then
    echo "Function URL: $FUNCTION_URL"
fi

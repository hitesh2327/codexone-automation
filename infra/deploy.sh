#!/usr/bin/env bash
# Deploy the dashboard: API image -> ECR, CloudFormation stack, web app -> S3, cache refresh.
# Run from the repo root:  bash infra/deploy.sh      (AWS_PROFILE defaults to "shhh")
# Safe to re-run. First run: put secrets in SSM first (python infra/put_secrets.py --apply).
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows would otherwise rewrite "/codexone/..." into a C:/ path

export AWS_PROFILE="${AWS_PROFILE:-shhh}" AWS_REGION="${AWS_REGION:-us-east-1}" AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
STACK="${STACK:-codexone-dashboard}"; REPO="codexone-api"; PREFIX="/codexone/"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
TAG="$(git rev-parse --short HEAD)-$(date +%s)"
IMAGE="$REGISTRY/$REPO:$TAG"

echo "== account $ACCOUNT, region $AWS_REGION, stack $STACK"
aws ssm get-parameter --name "${PREFIX}JWT_SECRET" --query Parameter.Name --output text >/dev/null \
  || { echo "secrets missing - run: python infra/put_secrets.py --apply"; exit 1; }

echo "== 1/5 container image"
aws ecr describe-repositories --repository-names "$REPO" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --image-scanning-configuration scanOnPush=true >/dev/null
# keep only the 5 newest images so storage stays at pennies
aws ecr put-lifecycle-policy --repository-name "$REPO" --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"keep 5","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":5},"action":{"type":"expire"}}]}' >/dev/null
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker build --provenance=false -q -f api/Dockerfile.lambda -t "$IMAGE" .   # Lambda rejects multi-platform manifests
docker push -q "$IMAGE" >/dev/null

echo "== 2/5 stack"
# Shared secret between CloudFront and the Lambda; created once, kept in SSM outside the app's prefix.
VERIFY_PARAM="/codexone-deploy/origin-verify"
aws ssm get-parameter --name "$VERIFY_PARAM" >/dev/null 2>&1 || aws ssm put-parameter --name "$VERIFY_PARAM" \
  --type SecureString --value "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" >/dev/null
VERIFY="$(aws ssm get-parameter --name "$VERIFY_PARAM" --with-decryption --query Parameter.Value --output text)"
aws cloudformation deploy --stack-name "$STACK" --template-file infra/template.yaml --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset --parameter-overrides "ImageUri=$IMAGE" "OriginVerify=$VERIFY" \
  ${PUBLISH_ENABLED:+PublishEnabled=$PUBLISH_ENABLED} ${TELEGRAM_SYNC:+TelegramSync=$TELEGRAM_SYNC}
out() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
SITE="$(out SiteUrl)"; BUCKET="$(out BucketName)"; DIST="$(out DistributionId)"; FN="$(out FunctionName)"

echo "== 3/5 public URL for sign-in redirects: $SITE"
aws ssm put-parameter --name "${PREFIX}PUBLIC_URL" --type String --overwrite --value "$SITE" >/dev/null
# Functions read SSM once per container; a new image tag above already forces fresh containers.

echo "== 4/5 web app"
( cd web && ([ -d node_modules ] || npm install --no-audit --no-fund) && PATH="$PWD/node_modules/.bin:$PATH" npm run build )
aws s3 sync web/dist "s3://$BUCKET" --delete --exclude index.html --cache-control "public,max-age=31536000,immutable" >/dev/null
aws s3 cp web/dist/index.html "s3://$BUCKET/index.html" --cache-control "no-cache" >/dev/null

echo "== 5/5 cache refresh"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/index.html" >/dev/null

echo; echo "Done. Dashboard: $SITE"
echo "Google sign-in needs this redirect URI registered:  $SITE/api/auth/google/callback"

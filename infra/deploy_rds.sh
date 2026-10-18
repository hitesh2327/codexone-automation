#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy_rds.sh — Create or update the RDS CloudFormation stack
#
# Usage:
#   bash infra/deploy_rds.sh                  # dry-run (shows changeset, does NOT deploy)
#   bash infra/deploy_rds.sh --apply          # create/update the stack
#
# This is a ONE-TIME setup step. After the stack exists, use migrate_db.sh
# to copy data from Neon, then redeploy Lambda with bash infra/deploy.sh.
#
# The RDS instance takes ~10 minutes to create. The script waits and prints
# the endpoint when done.
# ---------------------------------------------------------------------------
set -euo pipefail

APPLY=false
for arg in "$@"; do
  [[ "$arg" == "--apply" ]] && APPLY=true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RDS_STACK="${RDS_STACK:-codexone-rds}"
AWS_PROFILE="${AWS_PROFILE:-shhh}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TEMPLATE="$SCRIPT_DIR/rds.yaml"

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[deploy-rds] $*"; }

command -v aws &>/dev/null || die "aws CLI not found"
[[ -f "$TEMPLATE" ]] || die "Template not found: $TEMPLATE"

# ── prompt for password ────────────────────────────────────────────────────
if [[ -z "${DB_PASSWORD:-}" ]]; then
  echo ""
  echo "Choose a master password for the new RDS instance."
  echo "Requirements: 8-128 chars, no @, /, or spaces."
  echo "Save it in a password manager — you will need it for migrate_db.sh."
  echo ""
  while true; do
    echo -n "Password: "; read -rs DB_PASSWORD; echo ""
    echo -n "Confirm:  "; read -rs DB_CONFIRM; echo ""
    [[ "$DB_PASSWORD" == "$DB_CONFIRM" ]] && break
    echo "Passwords do not match, try again."
  done
fi
[[ ${#DB_PASSWORD} -ge 8 ]] || die "Password too short (minimum 8 characters)."

# ── dry-run: show changeset ────────────────────────────────────────────────
if [[ "$APPLY" == "false" ]]; then
  echo ""
  info "DRY-RUN: validating template and showing what would be created..."
  aws cloudformation validate-template \
    --template-body "file://$TEMPLATE" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output table 2>&1 | head -40 || true
  echo ""
  echo "┌─────────────────────────────────────────────────────────────────────┐"
  echo "│  DRY-RUN — no AWS resources will be created                         │"
  echo "├─────────────────────────────────────────────────────────────────────┤"
  echo "│  Stack:    $RDS_STACK"
  echo "│  Region:   $AWS_REGION"
  echo "│  Profile:  $AWS_PROFILE"
  echo "│  Template: $TEMPLATE"
  echo "├─────────────────────────────────────────────────────────────────────┤"
  echo "│  Re-run with --apply to create the RDS instance (~10 min, ~$13/mo) │"
  echo "└─────────────────────────────────────────────────────────────────────┘"
  exit 0
fi

# ── deploy ─────────────────────────────────────────────────────────────────
info "Deploying RDS stack: $RDS_STACK (region: $AWS_REGION, profile: $AWS_PROFILE)"
info "This will take ~10 minutes for the RDS instance to become available..."

aws cloudformation deploy \
  --stack-name "$RDS_STACK" \
  --template-file "$TEMPLATE" \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --no-fail-on-empty-changeset \
  --parameter-overrides "DatabasePassword=$DB_PASSWORD"

# ── print outputs ──────────────────────────────────────────────────────────
info "Stack created/updated. Fetching outputs..."

ENDPOINT="$(aws cloudformation describe-stacks \
  --stack-name "$RDS_STACK" \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DbEndpoint'].OutputValue" \
  --output text)"

PORT="$(aws cloudformation describe-stacks \
  --stack-name "$RDS_STACK" \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DbPort'].OutputValue" \
  --output text)"

DB_NAME="${DB_NAME:-codexone}"
DB_USER="${DB_USER:-codexone}"
DB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${ENDPOINT}:${PORT}/${DB_NAME}?sslmode=require"

echo ""
echo "┌─────────────────────────────────────────────────────────────────────┐"
echo "│  RDS stack deployed!                                                │"
echo "├─────────────────────────────────────────────────────────────────────┤"
echo "│  Endpoint: $ENDPOINT"
echo "│  Port:     $PORT"
echo "├─────────────────────────────────────────────────────────────────────┤"
echo "│  Next steps:                                                        │"
echo "│  1. Migrate data:  bash infra/migrate_db.sh --apply                │"
echo "│  2. Redeploy app:  bash infra/deploy.sh                            │"
echo "└─────────────────────────────────────────────────────────────────────┘"
echo ""
echo "DATABASE_URL (put in .env locally and in SSM after migration):"
echo "$DB_URL"

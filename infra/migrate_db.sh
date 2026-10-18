#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# migrate_db.sh — Migrate codexone database from Neon to RDS
#
# Usage:
#   bash infra/migrate_db.sh                  # dry-run (no writes, prints plan)
#   bash infra/migrate_db.sh --apply          # run the actual migration
#
# What it does:
#   1. Reads the source DATABASE_URL from .env (Neon)
#   2. Reads the RDS endpoint from CloudFormation stack outputs
#   3. pg_dump from Neon → pg_restore to RDS (schema + data)
#   4. Verifies row counts match
#   5. On --apply: updates SSM /codexone/DATABASE_URL with the RDS URL
#
# Requirements (install locally):
#   - PostgreSQL client tools (pg_dump, pg_restore, psql) — same major version as RDS
#   - aws CLI with profile "shhh" configured
#   - python-dotenv (pip install python-dotenv) OR source .env manually
#
# The script never modifies Neon; it is safe to re-run.
# ---------------------------------------------------------------------------
set -euo pipefail

APPLY=false
for arg in "$@"; do
  [[ "$arg" == "--apply" ]] && APPLY=true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
DUMP_FILE="/tmp/codexone_neon_dump_$(date +%Y%m%d_%H%M%S).dump"
RDS_STACK="${RDS_STACK:-codexone-rds}"
AWS_PROFILE="${AWS_PROFILE:-shhh}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# ── helpers ────────────────────────────────────────────────────────────────
die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[migrate] $*"; }
warn() { echo "WARN: $*" >&2; }

need_cmd() { command -v "$1" &>/dev/null || die "Required command not found: $1"; }

# ── pre-flight ─────────────────────────────────────────────────────────────
need_cmd pg_dump
need_cmd pg_restore
need_cmd psql
need_cmd aws

[[ -f "$ENV_FILE" ]] || die ".env not found at $PROJECT_ROOT/.env"

# Load DATABASE_URL (Neon source) from .env
NEON_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
[[ -n "$NEON_URL" ]] || die "DATABASE_URL not found in .env"

# Strip any surrounding quotes
NEON_URL="${NEON_URL#\"}"
NEON_URL="${NEON_URL%\"}"
NEON_URL="${NEON_URL#\'}"
NEON_URL="${NEON_URL%\'}"

info "Source (Neon): ${NEON_URL%%@*}@..."   # print URL without password

# ── get RDS endpoint from CloudFormation ───────────────────────────────────
info "Reading RDS stack outputs from CloudFormation (stack: $RDS_STACK)..."

RDS_ENDPOINT="$(aws cloudformation describe-stacks \
  --stack-name "$RDS_STACK" \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DbEndpoint'].OutputValue" \
  --output text 2>/dev/null)" || die "CloudFormation stack '$RDS_STACK' not found. Deploy it first with:
  bash infra/deploy_rds.sh"

RDS_PORT="$(aws cloudformation describe-stacks \
  --stack-name "$RDS_STACK" \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='DbPort'].OutputValue" \
  --output text)"

[[ -n "$RDS_ENDPOINT" ]] || die "RDS endpoint not found in stack outputs."

info "Target (RDS): $RDS_ENDPOINT:$RDS_PORT"

# ── prompt for RDS password ────────────────────────────────────────────────
# We cannot read the password from CloudFormation (NoEcho); read from stdin.
if [[ -z "${RDS_PASSWORD:-}" ]]; then
  echo ""
  echo "Enter the RDS master password (the one you used when creating the stack):"
  read -rs RDS_PASSWORD
  echo ""
fi
[[ -n "$RDS_PASSWORD" ]] || die "RDS_PASSWORD is empty."

# Extract DB name and username from the Neon URL
# postgresql://user:pass@host:port/dbname?params
NEON_DBNAME="$(echo "$NEON_URL" | sed -E 's|.*//[^@]+@[^/]+/([^?]+).*|\1|')"
RDS_DBNAME="${NEON_DBNAME:-codexone}"
RDS_USER="${RDS_USER:-codexone}"
RDS_URL="postgresql://${RDS_USER}:${RDS_PASSWORD}@${RDS_ENDPOINT}:${RDS_PORT}/${RDS_DBNAME}?sslmode=require"

info "RDS database: $RDS_DBNAME"

if [[ "$APPLY" == "false" ]]; then
  echo ""
  echo "┌─────────────────────────────────────────────────────────────────────┐"
  echo "│  DRY-RUN — no changes will be made                                  │"
  echo "├─────────────────────────────────────────────────────────────────────┤"
  echo "│  Source: Neon  →  DATABASE_URL from .env                            │"
  echo "│  Target: RDS   →  $RDS_ENDPOINT"
  echo "│  Dump file:    →  $DUMP_FILE"
  echo "│  SSM key:      →  /codexone/DATABASE_URL (updated on --apply)       │"
  echo "├─────────────────────────────────────────────────────────────────────┤"
  echo "│  Re-run with --apply to perform the migration.                      │"
  echo "└─────────────────────────────────────────────────────────────────────┘"
  echo ""
  exit 0
fi

# ── step 1: pg_dump from Neon ──────────────────────────────────────────────
info "Dumping Neon → $DUMP_FILE (custom format, schema + data)..."
PGPASSWORD="" pg_dump \
  --dbname="$NEON_URL" \
  --format=custom \
  --no-privileges \
  --no-owner \
  --file="$DUMP_FILE"

DUMP_SIZE="$(du -sh "$DUMP_FILE" | cut -f1)"
info "Dump complete: $DUMP_FILE ($DUMP_SIZE)"

# ── step 2: create the target database if it doesn't exist ────────────────
info "Ensuring database '$RDS_DBNAME' exists on RDS..."
PGPASSWORD="$RDS_PASSWORD" psql \
  --host="$RDS_ENDPOINT" \
  --port="$RDS_PORT" \
  --username="$RDS_USER" \
  --dbname=postgres \
  --command="SELECT 1 FROM pg_database WHERE datname='$RDS_DBNAME';" \
  | grep -q 1 || \
PGPASSWORD="$RDS_PASSWORD" psql \
  --host="$RDS_ENDPOINT" \
  --port="$RDS_PORT" \
  --username="$RDS_USER" \
  --dbname=postgres \
  --command="CREATE DATABASE \"$RDS_DBNAME\";"

# ── step 3: pg_restore to RDS ─────────────────────────────────────────────
info "Restoring dump to RDS..."
PGPASSWORD="$RDS_PASSWORD" pg_restore \
  --host="$RDS_ENDPOINT" \
  --port="$RDS_PORT" \
  --username="$RDS_USER" \
  --dbname="$RDS_DBNAME" \
  --no-privileges \
  --no-owner \
  --clean \
  --if-exists \
  "$DUMP_FILE" || {
    # pg_restore exits non-zero even for non-fatal warnings; check for real errors
    warn "pg_restore returned non-zero (often just warnings about existing objects — verify below)"
  }

# ── step 4: verify row counts ─────────────────────────────────────────────
info "Verifying row counts..."

count_rows() {
  local url="$1" table="$2"
  psql "$url" --tuples-only --command="SELECT COUNT(*) FROM \"$table\";" 2>/dev/null | tr -d ' '
}

TABLES=(users posts)
ALL_OK=true
for TABLE in "${TABLES[@]}"; do
  NEON_COUNT="$(count_rows "$NEON_URL" "$TABLE" 2>/dev/null || echo "N/A")"
  RDS_COUNT="$(count_rows "$RDS_URL" "$TABLE" 2>/dev/null || echo "N/A")"
  if [[ "$NEON_COUNT" == "$RDS_COUNT" ]]; then
    info "  $TABLE: $NEON_COUNT rows ✓"
  else
    warn "  $TABLE: Neon=$NEON_COUNT  RDS=$RDS_COUNT  ← MISMATCH"
    ALL_OK=false
  fi
done

if [[ "$ALL_OK" == "false" ]]; then
  die "Row count mismatch — do NOT update SSM until you investigate."
fi

# ── step 5: update SSM ─────────────────────────────────────────────────────
info "Updating SSM /codexone/DATABASE_URL to point at RDS..."
aws ssm put-parameter \
  --name "/codexone/DATABASE_URL" \
  --type "SecureString" \
  --value "$RDS_URL" \
  --overwrite \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION"

info "SSM updated."
echo ""
echo "┌─────────────────────────────────────────────────────────────────────┐"
echo "│  Migration complete!                                                │"
echo "├─────────────────────────────────────────────────────────────────────┤"
echo "│  Next: redeploy Lambda so it picks up the new DATABASE_URL         │"
echo "│        bash infra/deploy.sh                                        │"
echo "│                                                                     │"
echo "│  Dump kept at: $DUMP_FILE"
echo "│  Delete it once you confirm everything works.                       │"
echo "└─────────────────────────────────────────────────────────────────────┘"

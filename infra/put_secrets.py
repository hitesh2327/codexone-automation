"""Copy the dashboard's secrets from .env into AWS SSM Parameter Store (SecureString).

    python infra/put_secrets.py            # dry run: lists names only, changes nothing
    python infra/put_secrets.py --apply    # writes them (profile/region from AWS_PROFILE / AWS_REGION)

Values are never printed. Re-running overwrites. Names the dashboard needs but that are missing from .env are
listed with what stops working without them (CONFIG_MASTER_KEY, GITHUB_REPOSITORY, GITHUB_DISPATCH_TOKEN).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

PREFIX = os.environ.get("SSM_PREFIX", "/codexone/")
PROFILE = os.environ.get("AWS_PROFILE", "shhh")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# What the API reads (api/app/settings.py, src/actions.py, src/approve_bot.py). DATABASE_URL is the direct
# Neon URL, deliberately not DATABASE_URL_POOLED (pgbouncer + prepared statements).
REQUIRED = ["DATABASE_URL", "JWT_SECRET", "SESSION_SECRET", "ADMIN_USERNAME", "ADMIN_PASSWORD"]
OPTIONAL = ["GOOGLE_WEB_CLIENT_ID", "GOOGLE_WEB_CLIENT_SECRET", "ALLOWED_GOOGLE_EMAILS",
            "TG_BOT_TOKEN", "TG_CHAT_ID", "MAIL_DRIVER", "SMTP_HOST", "SMTP_PORT", "SMTP_SECURE",
            "SMTP_USER", "SMTP_PASS", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_NAME",
            "MAIL_FROM", "MAIL_FROM_NAME",   # Telegram & SMTP optional settings
            "CONFIG_MASTER_KEY", "GITHUB_REPOSITORY", "GITHUB_DISPATCH_TOKEN"]
# Optional for the API to start, but features are silently off without them (QA-M-01).
NEEDED_BY = {
    "CONFIG_MASTER_KEY": "the Config page can't save secrets (python -m src.config_store generate-key; put the SAME "
                         "value in GitHub: repository secret CONFIG_MASTER_KEY)",
    "GITHUB_REPOSITORY": "Generate, Publish now, Retry and Regenerate can't start GitHub jobs (owner/name)",
    "GITHUB_DISPATCH_TOKEN": "Generate, Publish now, Retry and Regenerate can't start GitHub jobs "
                             "(fine-grained token, this repo only, Actions: read and write)",
}


def main() -> int:
    apply = "--apply" in sys.argv
    env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        print("missing required keys in .env:", ", ".join(missing))
        return 1
    names = REQUIRED + [k for k in OPTIONAL if env.get(k)]
    print(f"{'Writing' if apply else 'Would write'} {len(names)} SecureString parameters under {PREFIX} "
          f"(profile {PROFILE}, {REGION}):")
    for k in names:
        print("  ", k)
        if apply:
            subprocess.run(["aws", "ssm", "put-parameter", "--name", PREFIX + k, "--type", "SecureString",
                            "--overwrite", "--value", env[k], "--profile", PROFILE, "--region", REGION],
                           check=True, stdout=subprocess.DEVNULL)
    lacking = [k for k in NEEDED_BY if not env.get(k)]
    for k in lacking:
        print(f"WARNING: {k} is not in .env: {NEEDED_BY[k]}")
    if lacking:
        print("Add them to .env and re-run, or set them on the Config page after deploying "
              "(CONFIG_MASTER_KEY can only come from here).")
    if not apply:
        print("dry run only; add --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())

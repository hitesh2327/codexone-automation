"""Copy the dashboard's secrets from .env into AWS SSM Parameter Store (SecureString).

    python infra/put_secrets.py            # dry run: lists names only, changes nothing
    python infra/put_secrets.py --apply    # writes them (profile/region from AWS_PROFILE / AWS_REGION)

Values are never printed. Re-running overwrites. GITHUB_DISPATCH_TOKEN is not in .env; add it
separately (see infra/README.md) when you turn on publish-now / regenerate from the dashboard.
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
            "MAIL_FROM", "MAIL_FROM_NAME"]   # Telegram & SMTP optional settings


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
    if not apply:
        print("dry run only; add --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# AWS deployment (serverless)

## Architecture

```
Browser -> CloudFront (HTTPS) --/api/*--> Lambda (FastAPI, container image) --> PostgreSQL
                              \--/*-----> S3 (built React app, private)
```

**Phase 1 (current default):** PostgreSQL = Neon (external, internet-accessible). Cost ~$0-1/month.

**Phase 2:** PostgreSQL = RDS on AWS (self-managed, same open-internet model as Neon). Cost ~$13-15/month (db.t3.micro + 20 GB gp3). No VPC/NAT needed: Lambda stays outside the VPC and reaches RDS over the internet, exactly like it reaches Neon.

## Publishing model
The Lambda never publishes: it runs with `PUBLISH_VIA=dispatch`, so **publish-now** and **retry** mark the post
ready and start the GitHub Actions *Poll Telegram approvals* workflow (needs `GITHUB_DISPATCH_TOKEN`).
GitHub Actions stays the only publisher. Locally (`PUBLISH_VIA` unset) the API still publishes inline.

---

## First deploy (Phase 1 — Neon)

1. Put these in `.env` (besides the sign-in secrets), then `python infra/put_secrets.py` (dry run: it warns about
   anything missing) and `python infra/put_secrets.py --apply` — secrets → SSM SecureString:
   - `DATABASE_URL`: Neon connection string (`postgresql://user:pass@host/db?sslmode=require`)
   - `CONFIG_MASTER_KEY`: `python -m src.config_store generate-key`. Without it the Config page can't save
     secrets. Put the **same value** in GitHub (*Settings > Secrets and variables > Actions*, secret
     `CONFIG_MASTER_KEY`), otherwise GitHub Actions can't read what the Config page saves.
     Keep a copy in a password manager: without it saved secrets can't be recovered.
   - `GITHUB_REPOSITORY`: `owner/name` of this repository (there is no default).
   - `GITHUB_DISPATCH_TOKEN`: fine-grained token, only this repository, *Actions: Read and write*.
   Without the last two, Generate / Publish now / Retry / Regenerate can't start GitHub jobs (the dashboard says so
   and the next scheduled run picks the work up). Both can also be set later on the Config page.
2. `bash infra/deploy.sh` — builds/pushes the image, creates the stack, uploads the web app, prints the URL.
   It warns if any of the three names above is missing from SSM.
3. Add `<URL>/api/auth/google/callback` to the Google OAuth client's *Authorized redirect URIs*.
4. Configure email (SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_FROM): with `COOKIE_SECURE=true` the API refuses to send
   password-reset codes to its log (QA-M-07), so "Forgot password" is unavailable until SMTP is set.
5. To turn on publishing / Telegram sync: `PUBLISH_ENABLED=true TELEGRAM_SYNC=true bash infra/deploy.sh`.

---

## Phase 2 — Migrate database to RDS

Run these steps once. After the cutover Lambda reads from RDS via the same SSM key (`/codexone/DATABASE_URL`).

### Prerequisites
- PostgreSQL client tools on your machine: `pg_dump`, `pg_restore`, `psql` (must match or exceed the RDS engine version — 16).
  - Mac: `brew install libpq`
  - Ubuntu: `sudo apt install postgresql-client`
  - Windows: install PostgreSQL 16 locally or use the zip archive from postgresql.org.
- AWS CLI configured with profile `shhh`.

### Step 1 — Create the RDS stack (one-time, ~10 min, ~$13/month)

```bash
# Dry-run first — validates the template, prints what would be created:
bash infra/deploy_rds.sh

# Create the stack (you will be prompted for a master password):
bash infra/deploy_rds.sh --apply
```

The script prints the RDS endpoint and a `DATABASE_URL` template when done. Save the password in a password manager.

### Step 2 — Migrate data from Neon to RDS

```bash
# Dry-run: shows the plan without touching anything:
bash infra/migrate_db.sh

# Run the migration (reads Neon URL from .env, prompts for RDS password):
bash infra/migrate_db.sh --apply
```

What `migrate_db.sh --apply` does:
1. `pg_dump` from Neon → `/tmp/codexone_neon_dump_<timestamp>.dump`
2. `pg_restore` to RDS
3. Verifies row counts match between source and target
4. Updates SSM `/codexone/DATABASE_URL` to the RDS connection string

If row counts mismatch it exits without updating SSM — investigate before re-running.

### Step 3 — Redeploy Lambda

```bash
bash infra/deploy.sh
```

Lambda picks up the updated `DATABASE_URL` from SSM on cold start. That's the cutover.

### Step 4 — Update local .env

```
DATABASE_URL=postgresql://codexone:PASSWORD@<rds-endpoint>:5432/codexone?sslmode=require
```

### Step 5 — Run pending Alembic migrations

```bash
.venv/Scripts/python.exe -m alembic -c api/alembic.ini upgrade head
```

(Or on Mac/Linux: `.venv/bin/python -m alembic -c api/alembic.ini upgrade head`)

### Cleanup

Once you're satisfied with RDS, the Neon project can be put on the free tier or deleted.
The dump file at `/tmp/codexone_neon_dump_*.dump` can be deleted once RDS is confirmed healthy.

---

## Notes
- Lambda function URL auth is `NONE`, guarded by an `X-Origin-Verify` secret CloudFront adds (OAC + IAM auth
  breaks browser POSTs, which would need a signed body hash). Direct hits get 403.
- Migrations run in CI (`python api/migrate.py` = `alembic upgrade head`, but a database already ahead of the
  checked-out code is skipped with a warning, so a rollback or a re-run of an old workflow run keeps working),
  never in the Lambda. Push a migration before the code that needs it.
- Re-run `deploy.sh` for every change; it is idempotent. Tear down: empty the S3 bucket, delete the stack, delete
  the ECR repo and the `/codexone/` SSM parameters.
- **To delete the RDS stack**: first disable `DeletionProtection` on the RDS instance in the AWS console, then
  `aws cloudformation delete-stack --stack-name codexone-rds --profile shhh`. CloudFormation creates a final
  snapshot before deleting (DeletionPolicy: Snapshot).

# AWS deployment (serverless + Neon)

```
Browser -> CloudFront (HTTPS) --/api/*--> Lambda (FastAPI, container image) --> Neon Postgres
                              \--/*-----> S3 (built React app, private)
```
Cost is ~$0-1/month (free tiers). No VPC/NAT, no load balancer, no RDS: Neon stays the database.

## Publishing model
The Lambda never publishes: it runs with `PUBLISH_VIA=dispatch`, so **publish-now** and **retry** mark the post
ready and start the GitHub Actions *Poll Telegram approvals* workflow (needs `GITHUB_DISPATCH_TOKEN`).
GitHub Actions stays the only publisher. Locally (`PUBLISH_VIA` unset) the API still publishes inline.

## First deploy
1. Put these in `.env` (besides the sign-in secrets), then `python infra/put_secrets.py` (dry run: it warns about
   anything missing) and `python infra/put_secrets.py --apply` - secrets -> SSM SecureString:
   - `CONFIG_MASTER_KEY`: `python -m src.config_store generate-key`. Without it the Config page can't save
     secrets. Put the **same value** in GitHub (*Settings > Secrets and variables > Actions*, secret
     `CONFIG_MASTER_KEY`), otherwise GitHub Actions can't read what the Config page saves (readiness G9 says so).
     Keep a copy in a password manager: without it saved secrets can't be recovered.
   - `GITHUB_REPOSITORY`: `owner/name` of this repository (there is no default).
   - `GITHUB_DISPATCH_TOKEN`: fine-grained token, only this repository, *Actions: Read and write*.
   Without the last two, Generate / Publish now / Retry / Regenerate can't start GitHub jobs (the dashboard says so
   and the next scheduled run picks the work up). Both can also be set later on the Config page.
2. `bash infra/deploy.sh` - builds/pushes the image, creates the stack, uploads the web app, prints the URL.
   It warns if any of the three names above is missing from SSM.
3. Add `<URL>/api/auth/google/callback` to the Google OAuth client's *Authorized redirect URIs*.
4. Configure email (SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_FROM): with `COOKIE_SECURE=true` the API refuses to send
   password-reset codes to its log (QA-M-07), so "Forgot password" is unavailable until SMTP is set.
5. To turn on publishing / Telegram sync: `PUBLISH_ENABLED=true TELEGRAM_SYNC=true bash infra/deploy.sh`.

## Notes
- Lambda function URL auth is `NONE`, guarded by an `X-Origin-Verify` secret CloudFront adds (OAC + IAM auth
  breaks browser POSTs, which would need a signed body hash). Direct hits get 403.
- Migrations run in CI (`python api/migrate.py` = `alembic upgrade head`, but a database already ahead of the
  checked-out code is skipped with a warning, so a rollback or a re-run of an old workflow run keeps working),
  never in the Lambda. Push a migration before the code that needs it.
- Re-run `deploy.sh` for every change; it is idempotent. Tear down: empty the S3 bucket, delete the stack, delete
  the ECR repo and the `/codexone/` SSM parameters.

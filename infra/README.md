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
1. `python infra/put_secrets.py` (dry run), then `python infra/put_secrets.py --apply` - secrets -> SSM SecureString.
2. `bash infra/deploy.sh` - builds/pushes the image, creates the stack, uploads the web app, prints the URL.
3. Add `<URL>/api/auth/google/callback` to the Google OAuth client's *Authorized redirect URIs*.
4. To enable actions later: store a GitHub token (`aws ssm put-parameter --name /codexone/GITHUB_DISPATCH_TOKEN
   --type SecureString --value ...`, scope: Actions read/write on this repo) and redeploy with
   `PUBLISH_ENABLED=true TELEGRAM_SYNC=true bash infra/deploy.sh`.

## Notes
- Lambda function URL auth is `NONE`, guarded by an `X-Origin-Verify` secret CloudFront adds (OAC + IAM auth
  breaks browser POSTs, which would need a signed body hash). Direct hits get 403.
- Migrations run in CI (`alembic upgrade head`), never in the Lambda.
- Re-run `deploy.sh` for every change; it is idempotent. Tear down: empty the S3 bucket, delete the stack, delete
  the ECR repo and the `/codexone/` SSM parameters.

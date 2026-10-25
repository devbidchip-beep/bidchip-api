# BidChip AWS Infrastructure Setup

## Services required

- **ECS Fargate** — clusters: `bidchip-staging`, `bidchip-prod`
  - Services: `bidchip-api` (web), `bidchip-worker` (Celery), `bidchip-beat` (Celery Beat)
  - Task definitions: see `task-definition-web.json`, `task-definition-worker.json`, `task-definition-beat.json`
- **RDS PostgreSQL 16** — Multi-AZ in prod, automated 7-day backups, `db.t3.medium` (scale as needed)
- **ElastiCache Redis 7** — cluster mode disabled, one replica in prod, `cache.t3.micro` (scale as needed)
- **ECR repository**: `bidchip-api`
- **S3 buckets**:
  - `bidchip-documents-prod` — private, versioning enabled, lifecycle: move to Glacier after 90 days
  - `bidchip-documents-staging` — private, versioning enabled
- **SES**:
  - Verify `bidchip.com` domain; set up DKIM, SPF, DMARC records
  - Configure inbound rule: `sourcing@bidchip.com` → S3 → SNS → SQS
  - Request production access (lift SES sandbox) before launch
- **Secrets Manager** — store all secrets listed in the task definitions under `bidchip/prod/`
- **ACM** — request certificates for `api.bidchip.com` and `api-staging.bidchip.com`
- **ALB** — HTTPS listener on port 443, forward to ECS service target group on port 8000
- **CloudWatch Logs** — log groups: `/ecs/bidchip-api`, `/ecs/bidchip-worker`, `/ecs/bidchip-beat`

## IAM roles required

- `ecsTaskExecutionRole` — pull from ECR, write to CloudWatch Logs, read Secrets Manager
- `bidchipTaskRole` — S3 read/write on document buckets, SES send, SQS receive

## GitHub Secrets required

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | CI/CD IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | CI/CD IAM user secret key |
| `SUBNET_ID` | Staging VPC subnet ID (for ECS run-task) |
| `SECURITY_GROUP_ID` | Staging ECS task security group ID |
| `PROD_SUBNET_ID` | Production VPC subnet ID |
| `PROD_SECURITY_GROUP_ID` | Production ECS task security group ID |

## GitHub Environments

- **staging** — auto-deploy on push to `main` (no approval required)
- **production** — requires manual approval; add required reviewers in:
  GitHub → Settings → Environments → production → Required reviewers

## First deploy checklist

- [ ] Register task definitions in ECS (all three JSON files)
- [ ] Create ECS services in staging cluster, confirm tasks start
- [ ] Run ETL commands on staging in order:
  1. `python manage.py etl_import_companies --file companies.csv`
  2. `python manage.py etl_import_parts --file parts.csv`
  3. `python manage.py etl_import_inventory --file inventory.csv`
  4. `python manage.py etl_import_logos --source-bucket bidchip-auction --prefix logos/`
  5. `python manage.py etl_import_ratings --file ratings.csv`
- [ ] Run `python manage.py etl_verify_migration` — must exit 0
- [ ] Run `python manage.py security_check` — must exit 0
- [ ] Smoke test all critical paths (login, search parts, create listing, place bid, checkout)
- [ ] Enable Stripe webhook endpoint in Stripe dashboard pointing to `https://api-staging.bidchip.com/api/v1/payments/webhook/`
- [ ] Rotate all test API keys to production keys in Secrets Manager
- [ ] Verify SES sandbox lifted (request production access)
- [ ] Set up CloudWatch alarms:
  - 5xx error rate > 1%
  - p99 latency > 2s
  - ECS CPU utilization > 80%
  - RDS free storage < 10 GB
- [ ] Confirm Sentry project configured and `SENTRY_DSN` set in prod secrets
- [ ] Verify DMARC reports are arriving (check after 24h)
- [ ] Enable production deploy by approving the `deploy-prod` job in GitHub Actions

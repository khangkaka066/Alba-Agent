# Production deployment

1. Copy the root `.env.example` to `.env`, set unique database, Redis, API, and credential encryption secrets, and set `NEXUS_DOMAIN` to a public DNS name that resolves to this host. Open ports 80 and 443.
2. Set `NEXUS_BILLING_PLAN_LIMITS_JSON` only when the built-in FREE/PRO/ENTERPRISE limits need an operator override. Map payment products to Nexus plans with `NEXUS_BILLING_PRODUCT_PLANS_JSON`, for example `{"stripe":{"price_...":"PRO"},"polar":{"prod_...":"PRO"}}`. Configure provider webhook secrets and credit product mappings only for gateways in use.
3. Start the stack from the repository root with `docker compose -f docker-compose.prod.yml up -d --build`. Caddy provisions and renews HTTPS certificates; API and web ports remain private to the Compose network.
4. The database backup service writes compressed PostgreSQL custom-format dumps to the `nexus_prod_backups` volume once per day and deletes files older than `NEXUS_BACKUP_RETENTION_DAYS`. Export that volume to independent encrypted storage. Restore with `pg_restore --clean --if-exists --no-owner` after stopping API and worker services.

Built-in quota defaults are FREE: $10 monthly managed spend, 60 sandbox minutes, 1 workspace, 3 bots, and 10,000 vector chunks; PRO: $500, 3,000 minutes, 10 workspaces, 50 bots, and 1,000,000 chunks; ENTERPRISE: no configured quota cap. Overrides are applied per plan and use the field names in `/api/v1/billing/plan`.

## Offline Enterprise licenses

Keep the Ed25519 private key in a restricted offline operator environment. Issue a token with `python3 scripts/issue_enterprise_license.py --private-key /secure/path/license-signing-key.pem --subject customer-name --expires-in-days 365 --feature multi_workspace --feature sso --feature audit_logs`. Configure only the resulting token as `NEXUS_LICENSE_KEY`; configure the matching public key as base64 raw 32-byte Ed25519 material in `NEXUS_LICENSE_PUBLIC_KEY`. The API verifies signatures and expiry locally and makes no billing-server request. The issuer never deploys the signing key.

## Webhook mapping

All payment webhook handlers verify provider signatures and timestamp windows before accepting signed events. Attach `tenant_id` and `workspace_id` metadata to the provider customer/subscription/order records. Subscription plan mappings use the product or price identifier; only paid checkout/order events apply compute-credit top-ups. Custom VietQR events use `X-Nexus-Timestamp` and `X-Nexus-Signature: sha256=<hex HMAC-SHA256(timestamp.body)>`.

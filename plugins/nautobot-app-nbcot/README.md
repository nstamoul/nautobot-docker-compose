# NBCOT

NBCOT is a Nautobot app for Cisco Commerce Modern order tracking. It gives operators a Nautobot-native workflow to search Cisco orders on demand, start tracking selected orders, review current status and delivery milestones, inspect line-level fulfillment, and keep a local change history for tracked orders.

The phase 1 implementation is intentionally pragmatic:

- one global Cisco OAuth client-credentials integration
- UAT-first endpoint defaults
- ad hoc multi-key search with exact order-number lookup as the primary path
- persistence only for explicitly tracked orders
- scheduled/manual refresh with an internal service boundary that can later support GraphQL event subscriptions

## Current Features

- Cisco OAuth2 client-credentials token handling
- GraphQL search and order-detail client wrapper
- normalized `CiscoOrder`, `CiscoOrderLine`, and `CiscoOrderUpdate` models
- Nautobot tracked-order list and detail views
- custom search-and-track workflow at `Plugins > NBCOT > Order Search`
- refresh jobs for one tracked order or all tracked orders
- local smoke-test management command: `nbcot_smoke_test`

## Plugin Configuration

Configure NBCOT in `PLUGINS_CONFIG["nbcot"]` with:

- `environment`
- `token_url`
- `graphql_endpoint`
- `client_id`
- `client_secret`
- `tracked_order_refresh_interval_minutes`
- `enable_event_consumer`
- optional overrides for `search_query_document` and `order_details_query_document`

The generated development config at [development/nautobot_config.py](/opt/_tools/_automation/nautobot_cisco_order_tracking/development/nautobot_config.py) includes example environment-variable wiring for these settings. The client resolves missing credentials through the shared SHMS secret resolver:

- direct env/config fallback: `CISCO_MODERN_API_CLIENT_ID`, `CISCO_MODERN_API_SECRET`, `NBCOT_CLIENT_ID`, `NBCOT_CLIENT_SECRET`
- legacy Vault token fallback: `HASHICORP_VAULT_URL`, `HASHICORP_VAULT_TOKEN`, `CISCO_API_VAULT_MOUNT`, `CISCO_API_VAULT_PATH`
- future cert-auth shape: `VAULT_AUTH_METHOD=cert`, `VAULT_CERT_ROLE`, `VAULT_CLIENT_CERT`, `VAULT_CLIENT_KEY`, and `VAULT_CACERT` or `REQUESTS_CA_BUNDLE`

Keep `creds.env` token fallback explicit during migration; do not store client private keys or real tokens in Git.

## Verification

Containerized verification completed with:

```bash
docker compose -f development/docker-compose.base.yml \
  -f development/docker-compose.postgres.yml \
  -f development/docker-compose.redis.yml \
  -f development/docker-compose.dev.yml \
  run --rm nautobot nautobot-server test nbcot.tests --keepdb
```

Result: `93` tests passed, `2` skipped.

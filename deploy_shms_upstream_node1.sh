#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
remote_host="${1:-nb-ha-01}"
remote_root="${2:-/opt/nautobot}"
remote_user="${REMOTE_USER:-nstam}"
remote_target="${remote_user}@${remote_host}"
secret_file="/opt/_tools/_automation/__codex_tmp_project__/artifacts/nautobot-shms-secret-values.env"
start_stack="${START_STACK:-1}"
vault_tls_host="${VAULT_TLS_HOST:-vault.shms.local}"
vault_tls_port="${VAULT_TLS_PORT:-8200}"

if [[ ! -f "${secret_file}" ]]; then
  echo "secret file not found: ${secret_file}" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

chain_file="${tmpdir}/vault-chain.pem"
echo Q | openssl s_client -showcerts -connect "${vault_tls_host}:${vault_tls_port}" -servername "${vault_tls_host}" \
  >"${chain_file}" 2>/dev/null
python3 - <<'PY' "${chain_file}" "${tmpdir}/vault-ca.crt" "${vault_tls_host}" "${vault_tls_port}"
from pathlib import Path
import re
import sys

chain_file = Path(sys.argv[1])
ca_file = Path(sys.argv[2])
vault_host = sys.argv[3]
vault_port = sys.argv[4]

certs = re.findall(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    chain_file.read_text(),
    re.S,
)
if not certs:
    raise SystemExit(f"could not derive Vault TLS CA certificate from {vault_host}:{vault_port}")
ca_file.write_text(certs[-1] + "\n")
PY

python3 - <<'PY' "${tmpdir}" "${secret_file}"
from pathlib import Path
import sys

outdir = Path(sys.argv[1])
secret_file = Path(sys.argv[2])

secrets = {}
for line in secret_file.read_text().splitlines():
    if not line or "=" not in line:
        continue
    key, value = line.split("=", 1)
    secrets[key] = value

def compose_escape(value: str) -> str:
    return value.replace("$", "$$")

local_env = """NAUTOBOT_VERSION=3.1.0
PYTHON_VER=3.11

NAUTOBOT_ALLOWED_HOSTS=sot3.shms.local,sot.space.gr,nb-ha-01.shms.local,nb-ha-02.shms.local,localhost,127.0.0.1
NAUTOBOT_CSRF_TRUSTED_ORIGINS=http://sot3.shms.local,https://sot.space.gr
NAUTOBOT_SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
NAUTOBOT_BANNER_TOP=SHMS
NAUTOBOT_CHANGELOG_RETENTION=90
NAUTOBOT_CONFIG=/opt/nautobot/nautobot_config.py
NAUTOBOT_DB_HOST=nb-db-vip.shms.local
NAUTOBOT_DB_PORT=5432
NAUTOBOT_DB_NAME=nautobot
NAUTOBOT_DB_USER=nautobot
NAUTOBOT_DEBUG=False
NAUTOBOT_DJANGO_EXTENSIONS_ENABLED=False
NAUTOBOT_DJANGO_TOOLBAR_ENABLED=False
NAUTOBOT_HIDE_RESTRICTED_UI=True
NAUTOBOT_LOG_LEVEL=INFO
NAUTOBOT_METRICS_ENABLED=True
NAUTOBOT_NAPALM_TIMEOUT=5
NAUTOBOT_MAX_PAGE_SIZE=0
NAUTOBOT_BASE_URL=https://sot.space.gr
NAUTOBOT_RUNTIME_PATCHES_ENABLED=true
NAUTOBOT_RUNTIME_PATCHES_PATH=/opt/nautobot/patches_runtime
NAUTOBOT_DEVICE_ONBOARDING_DEFAULT_DEVICE_ROLE=placeholder_role
NAUTOBOT_NORNIR_NUM_WORKERS=50
NAUTOBOT_NORNIR_RUNNER_PLUGIN=threaded
NAUTOBOT_SSOT_ENABLE_MERAKI=false
NAUTOBOT_SSOT_ENABLE_ACI=false
NAUTOBOT_SSOT_ENABLE_BOOTSTRAP=false
NAUTOBOT_SSOT_ENABLE_VSPHERE=true
NAUTOBOT_AUTH_LDAP_SERVER_URI=ldap://172.20.11.30
NAUTOBOT_AUTH_LDAP_BIND_DN=CN=Sa Nautobot,CN=Users,DC=shms,DC=local
NAUTOBOT_AUTH_LDAP_SEARCH_DN=DC=shms,DC=local
NAUTOBOT_AUTH_LDAP_MIRROR_GROUPS=true
NAUTOBOT_AUTH_LDAP_FIND_GROUP_PERMS=true
NAUTOBOT_AUTH_LDAP_ALWAYS_UPDATE_USER=true
NAUTOBOT_AUTH_LDAP_CACHE_TIMEOUT=3600
NAUTOBOT_AUTH_LDAP_REQUIRE_GROUP=CN=NB-LOGIN,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local
NAUTOBOT_AUTH_LDAP_IS_ACTIVE_DN=CN=NB-LOGIN,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local
NAUTOBOT_AUTH_LDAP_IS_STAFF_DN=CN=NB-STAFF,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local
NAUTOBOT_AUTH_LDAP_IS_SUPERUSER_DN=CN=NB-SUPERUSERS,OU=Platform,OU=Nautobot,OU=Groups,DC=shms,DC=local
NBCOT_ENVIRONMENT=prod
NBCOT_TOKEN_URL=https://id.cisco.com/oauth2/default/v1/token
NBCOT_GRAPHQL_ENDPOINT=https://capi.cisco.com/commerce/apis
NBCOT_REFRESH_INTERVAL_MINUTES=60
NBCOT_ENABLE_EVENT_CONSUMER=false
NAUTOBOT_REDIS_HOST=nb-redis-vip.shms.local
NAUTOBOT_REDIS_PORT=6379
POSTGRES_USER=${NAUTOBOT_DB_USER}
POSTGRES_DB=${NAUTOBOT_DB_NAME}
REQUESTS_CA_BUNDLE=/opt/nautobot/certs/vault-ca.crt
SSL_CERT_FILE=/opt/nautobot/certs/vault-ca.crt
HASHICORP_VAULT_URL=https://vault.shms.local:8200
HASHICORP_VAULT_TOKEN=__VAULT_NAUTOBOT_TOKEN__
NAUTOBOT_MINIO_ENABLED=true
NAUTOBOT_MINIO_ENDPOINT_URL=http://s3.minio.shms.local
NAUTOBOT_MINIO_BUCKET_NAME=nautobot
NAUTOBOT_MINIO_REGION_NAME=us-east-1
NAUTOBOT_MINIO_VERIFY_SSL=false
ENABLE_VPN_ROUTING=false
VPN_QUEUE=vpn
VPN_CONTAINER_NAME=shms-vpn
VPN_NETWORK_NAME=shms_vpn_default
VPN_CONTROL_API_URL=http://vpn-control-api:5001
VPN_SET_DNS=false
PICONFIG_API_URL=https://piconfig.eztp.space.gr
PICONFIG_NAUTOBOT_CLIENT_CERT=/opt/nautobot/certs/piconfig/nautobot-service.crt
PICONFIG_NAUTOBOT_CLIENT_KEY=/opt/nautobot/certs/piconfig/nautobot-service.key
PICONFIG_CA_BUNDLE=/opt/nautobot/certs/vault-ca.crt
PICONFIG_VERIFY_TLS=true
"""
local_env = local_env.replace("__VAULT_NAUTOBOT_TOKEN__", compose_escape(secrets["VAULT_NAUTOBOT_TOKEN"]))

creds_env = f"""NAUTOBOT_CREATE_SUPERUSER=false
NAUTOBOT_DB_PASSWORD={compose_escape(secrets["NAUTOBOT_DB_PASSWORD"])}
NAUTOBOT_NAPALM_USERNAME=
NAUTOBOT_NAPALM_PASSWORD=
NAUTOBOT_REDIS_PASSWORD={compose_escape(secrets["REDIS_PASSWORD"])}
NAUTOBOT_SECRET_KEY={compose_escape(secrets["NAUTOBOT_SECRET_KEY"])}
NAUTOBOT_SUPERUSER_NAME={compose_escape(secrets["NAUTOBOT_ADMIN_USERNAME"])}
NAUTOBOT_SUPERUSER_EMAIL={compose_escape(secrets["NAUTOBOT_ADMIN_EMAIL"])}
NAUTOBOT_SUPERUSER_PASSWORD={compose_escape(secrets["NAUTOBOT_ADMIN_PASSWORD"])}
NAUTOBOT_SUPERUSER_API_TOKEN={compose_escape(secrets["NAUTOBOT_ADMIN_API_TOKEN"])}
NAUTOBOT_MINIO_ACCESS_KEY={compose_escape(secrets["MINIO_NAUTOBOT_ACCESS_KEY"])}
NAUTOBOT_MINIO_SECRET_KEY={compose_escape(secrets["MINIO_NAUTOBOT_SECRET_KEY"])}
NAUTOBOT_AUTH_LDAP_BIND_PASSWORD={compose_escape(secrets["NAUTOBOT_AUTH_LDAP_BIND_PASSWORD"])}
VPN_CONTROL_API_KEY={compose_escape(secrets["VPN_CONTROL_API_KEY"])}
CISCO_MODERN_API_CLIENT_ID=
CISCO_MODERN_API_SECRET=
POSTGRES_PASSWORD=${{NAUTOBOT_DB_PASSWORD}}
PGPASSWORD=${{NAUTOBOT_DB_PASSWORD}}
"""

(outdir / "local.shms.env").write_text(local_env)
(outdir / "creds.shms.env").write_text(creds_env)
(outdir / ".env").write_text(
    "NAUTOBOT_VERSION=3.1.0\n"
    "PYTHON_VER=3.11\n"
)
PY

rsync -az --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.pytest_cache' \
  --exclude '.DS_Store' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'certs' \
  --exclude 'git' \
  --exclude 'plugins/*/development/creds.env' \
  --exclude 'plugins/*/development/*.sqlite3' \
  -e "ssh -o StrictHostKeyChecking=no" \
  "${repo_root}/" "${remote_target}:${remote_root}/"

scp -o StrictHostKeyChecking=no "${tmpdir}/local.shms.env" "${remote_target}:${remote_root}/environments/local.shms.env" >/dev/null
scp -o StrictHostKeyChecking=no "${tmpdir}/creds.shms.env" "${remote_target}:${remote_root}/environments/creds.shms.env" >/dev/null
scp -o StrictHostKeyChecking=no "${tmpdir}/.env" "${remote_target}:${remote_root}/environments/.env" >/dev/null
ssh -o StrictHostKeyChecking=no "${remote_target}" "sudo install -d -m 755 /opt/nautobot/certs" >/dev/null
scp -o StrictHostKeyChecking=no "${tmpdir}/vault-ca.crt" "${remote_target}:/tmp/vault-ad-ca.crt" >/dev/null

ssh -o StrictHostKeyChecking=no "${remote_target}" "bash -lc '
  set -euo pipefail
  sudo install -d -m 755 /data/nautobot/media
  sudo install -d -m 755 /data/nautobot/static
  cat /etc/ssl/certs/ca-certificates.crt /tmp/vault-ad-ca.crt | sudo tee /opt/nautobot/certs/vault-ca.crt >/dev/null
  sudo chmod 644 /opt/nautobot/certs/vault-ca.crt
  rm -f /tmp/vault-ad-ca.crt
  sudo chown -R 999:999 /data/nautobot
  cd ${remote_root}/environments
  chmod 600 local.shms.env creds.shms.env .env
  set -a
  source .env
  set +a
  if [[ \"${start_stack}\" == \"1\" ]]; then
    docker compose -f docker-compose.shms-app.yml build
    docker compose -f docker-compose.shms-app.yml run --rm nautobot nautobot-server post_upgrade
    if [[ \"${remote_host}\" == \"nb-ha-01\" ]]; then
      docker compose -f docker-compose.shms-app.yml up -d
    else
      docker compose -f docker-compose.shms-app.yml up -d nautobot celery_worker
    fi
    docker compose -f docker-compose.shms-app.yml ps
  else
    echo \"Synced SHMS Nautobot tree to ${remote_root} without starting containers.\"
  fi
'"

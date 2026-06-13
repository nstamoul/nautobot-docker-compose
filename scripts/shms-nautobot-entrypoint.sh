#!/usr/bin/env sh
set -eu

if [ "${SHMS_VAULT_AGENT_ENABLED:-false}" = "true" ]; then
    token_file="${SHMS_VAULT_TOKEN_FILE:-/run/shms-vault/nautobot.token}"
    wait_seconds="${SHMS_VAULT_TOKEN_WAIT_SECONDS:-60}"
    elapsed=0

    while [ ! -s "$token_file" ]; do
        if [ "$elapsed" -ge "$wait_seconds" ]; then
            echo "Timed out waiting for Vault Agent token at $token_file" >&2
            exit 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    HASHICORP_VAULT_TOKEN="$(tr -d '\r\n' < "$token_file")"
    export HASHICORP_VAULT_TOKEN
    VAULT_TOKEN="$HASHICORP_VAULT_TOKEN"
    export VAULT_TOKEN
fi

git config --global --add safe.directory /opt/nautobot/git/shms_nautobot_jobs_repo >/dev/null 2>&1 || true

docker_entrypoint="${SHMS_DOCKER_ENTRYPOINT:-/docker-entrypoint.sh}"
if [ -x "$docker_entrypoint" ]; then
    exec "$docker_entrypoint" "$@"
fi

exec "$@"

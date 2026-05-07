#!/usr/bin/env python3
"""Minimal standalone Cisco CCW OAuth + GraphQL probe.

This intentionally avoids Nautobot imports and never prints client secrets or
access tokens. It can run on a host/container that has NBCOT/Cisco environment
variables or the same Vault variables used by the app.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
ENDPOINTS = {
    "prod": "https://capi.cisco.com/commerce/apis",
    "poe": "https://capitest.cisco.com/commerce/POE/apis",
    "uat": "https://capitest.cisco.com/commerce/UAT/apis",
}

ORDER_SEARCH_QUERY = """
query SearchOrders($input: OrderSearchInput) {
  searchOrder(input: $input) {
    businessStatus
    messages {
      code
      description
      severity
    }
    objects {
      ciscoSalesOrderReference {
        ciscoSalesOrderId
      }
      orderStatus
    }
  }
}
""".strip()


def first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def load_vault_credentials() -> tuple[str, str, str]:
    vault_url = os.getenv("HASHICORP_VAULT_URL")
    vault_token = os.getenv("HASHICORP_VAULT_TOKEN")
    if not vault_url or not vault_token:
        return "", "", "none"

    vault_mount = os.getenv("CISCO_API_VAULT_MOUNT", "kv").strip("/")
    vault_path = os.getenv("CISCO_API_VAULT_PATH", "CISCO_API_CONSOLE").strip("/")
    headers = {"X-Vault-Token": vault_token}
    vault_namespace = os.getenv("HASHICORP_VAULT_NAMESPACE") or os.getenv("VAULT_NAMESPACE")
    if vault_namespace:
        headers["X-Vault-Namespace"] = vault_namespace

    verify: str | bool = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE") or True
    response = requests.get(
        f"{vault_url.rstrip('/')}/v1/{vault_mount}/data/{vault_path}",
        headers=headers,
        verify=verify,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json().get("data", {}).get("data", {})
    return (
        data.get("CISCO_MODERN_API_CLIENT_ID") or data.get("API_TOKEN_CLIENT_ID") or "",
        data.get("CISCO_MODERN_API_SECRET") or data.get("API_TOKEN_CLIENT_PASS") or "",
        f"vault:{vault_mount}/{vault_path}",
    )


def load_credentials() -> tuple[str, str, str]:
    client_id = first_env("NBCOT_CLIENT_ID", "CISCO_MODERN_API_CLIENT_ID", "API_TOKEN_CLIENT_ID")
    client_secret = first_env("NBCOT_CLIENT_SECRET", "CISCO_MODERN_API_SECRET", "API_TOKEN_CLIENT_PASS")
    if client_id and client_secret:
        return client_id, client_secret, "environment"

    vault_client_id, vault_client_secret, source = load_vault_credentials()
    return client_id or vault_client_id, client_secret or vault_client_secret, source


def compact_body(response: requests.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict) and "access_token" in payload:
        payload = dict(payload)
        payload["access_token"] = "withheld"
    return payload


def order_search_input(order_number: str) -> dict[str, Any]:
    return {
        "orderSearchCriteria": [
            {"orderSearchKey": "SALES_ORDER_ID", "orderSearchValue": str(order_number)},
        ],
        "sortByOrderCharacteristics": "CREATION_DATE",
        "pagination": {"page": 1, "pageSize": 1, "sortOrder": "DESC"},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=sorted(ENDPOINTS), default="prod")
    parser.add_argument("--order-number", required=True)
    parser.add_argument("--header-matrix", action="store_true", help="Try common gateway client-id header variants.")
    args = parser.parse_args()

    token_url = os.getenv("NBCOT_TOKEN_URL", DEFAULT_TOKEN_URL)
    graphql_endpoint = os.getenv("NBCOT_GRAPHQL_ENDPOINT", ENDPOINTS[args.environment])
    client_id, client_secret, credential_source = load_credentials()

    report: dict[str, Any] = {
        "environment": args.environment,
        "token_url": token_url,
        "graphql_endpoint": graphql_endpoint,
        "credential_source": credential_source,
        "client_id_present": bool(client_id),
        "client_secret_present": bool(client_secret),
        "token": {"http_status": None, "acquired": False},
        "graphql": {"http_status": None},
    }

    if not client_id or not client_secret:
        print(json.dumps(report, indent=2))
        return 2

    with requests.Session() as session:
        token_response = session.post(
            token_url,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=30,
        )
        report["token"]["http_status"] = token_response.status_code
        report["token"]["body"] = compact_body(token_response)
        token = token_response.json().get("access_token") if token_response.ok else ""
        report["token"]["acquired"] = bool(token)
        if not token:
            print(json.dumps(report, indent=2))
            return 1

        base_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        graphql_payload = {"query": ORDER_SEARCH_QUERY, "variables": {"input": order_search_input(args.order_number)}}
        graphql_response = session.post(graphql_endpoint, json=graphql_payload, headers=base_headers, timeout=60)
        report["graphql"]["http_status"] = graphql_response.status_code
        report["graphql"]["body"] = compact_body(graphql_response)

        if args.header_matrix:
            report["header_matrix"] = {}
            for label, extra_headers in {
                "client_id": {"client_id": client_id},
                "x_client_id": {"X-Client-Id": client_id},
                "x_ibm_client_id": {"X-IBM-Client-Id": client_id},
            }.items():
                matrix_response = session.post(
                    graphql_endpoint,
                    json=graphql_payload,
                    headers=base_headers | extra_headers,
                    timeout=60,
                )
                report["header_matrix"][label] = {
                    "http_status": matrix_response.status_code,
                    "body": compact_body(matrix_response),
                }

    print(json.dumps(report, indent=2))
    return 0 if report["graphql"]["http_status"] and report["graphql"]["http_status"] < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())

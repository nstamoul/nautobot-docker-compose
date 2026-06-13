#!/usr/bin/env python3
"""Standalone Cisco Modern Commerce API repro for support escalation.

This script intentionally avoids Nautobot imports so it can be copied into an
email thread or run anywhere with Python + requests. It exercises the exact
operations currently failing for this deployment and prints sanitized results.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
ENVIRONMENT_ENDPOINTS = {
    "poe": "https://capitest.cisco.com/commerce/POE/apis",
    "prod": "https://capi.cisco.com/commerce/apis",
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
      metaData {
        createdOn
        lastUpdatedAt
      }
      buyerPurchaseOrderReference {
        purchaseOrderId
        purchaseOrderDate
      }
      ciscoSalesOrderReference {
        ciscoSalesOrderId
      }
      parties {
        id
        name
        type
        partnerType
      }
      orderStatus
      businessStatus
    }
  }
}
""".strip()


ORDER_DETAILS_QUERY = """
query GetOrderDetails($input: OrderSearchInput) {
  getOrderDetails(input: $input) {
    businessStatus
    messages {
      code
      description
      severity
    }
    objects {
      metaData {
        createdOn
        lastUpdatedAt
      }
      buyerPurchaseOrderReference {
        purchaseOrderId
        purchaseOrderDate
      }
      ciscoSalesOrderReference {
        ciscoSalesOrderId
        ciscoSalesOrderURL
      }
      parties {
        id
        name
        type
        partnerType
      }
      orderCharacteristics {
        customerReference
      }
      orderStatus
      businessStatus
      lines {
        orderLineReference {
          lineId
          userInterfaceLineId
          parentLineId
          webOrderId
        }
        item {
          sku
          description
        }
        quantity {
          measurement
          unitOfMeasure
        }
        orderLineStatus
        holdInformation {
          name
          description
          reason
          appliedDate
          isPartnerActionRequired
        }
        orderLineStatusHistory {
          orderLineStatus
          updatedOn
        }
        shippingAttributes {
          shipSetStatus
          shippedQty
          estimatedDeliveryDate
          actualDeliveryDate
          requestedDeliveryDate
          promisedDate
          estimatedShipDate
          requestedShipDate
          recommitDate
          recommitReason
        }
      }
    }
  }
}
""".strip()


SUBSCRIPTION_SEARCH_QUERY = """
query SearchSubscriptions($input: MySubscriptionSearchInput) {
  searchSubscription(input: $input) {
    businessStatus
    messages {
      code
      description
      severity
    }
    objects {
      id
      name
      businessStatus
      parties {
        id
        name
        type
      }
      mySubscriptionCharacteristics {
        startDate
        endDate
        renewalDate
        mySubscriptionStatus
      }
    }
  }
}
""".strip()


SUBSCRIPTION_DETAILS_QUERY = """
query GetSubscriptionDetails($input: MySubscriptionSearchInput) {
  getSubscriptionDetails(input: $input) {
    businessStatus
    messages {
      code
      description
      severity
    }
    objects {
      id
      name
      businessStatus
      mySubscriptionCharacteristics {
        startDate
        endDate
        renewalDate
        mySubscriptionStatus
      }
      lines {
        mySubscriptionLineReference {
          lineId
        }
        orderReference {
          webOrderId
          buyerPurchaseOrderReference {
            purchaseOrderId
          }
          ciscoSalesOrderReference {
            ciscoSalesOrderId
          }
        }
        item {
          sku
          description
          additionalAttributes {
            name
            value
          }
        }
      }
    }
  }
}
""".strip()


@dataclass
class CiscoContext:
    token_url: str
    graphql_endpoint: str
    client_id: str
    client_secret: str


def load_context(environment: str) -> CiscoContext:
    """Resolve runtime configuration from environment variables."""
    return CiscoContext(
        token_url=os.getenv("NBCOT_TOKEN_URL", DEFAULT_TOKEN_URL),
        graphql_endpoint=os.getenv("NBCOT_GRAPHQL_ENDPOINT", ENVIRONMENT_ENDPOINTS[environment]),
        client_id=os.getenv("CISCO_MODERN_API_CLIENT_ID") or os.getenv("NBCOT_CLIENT_ID", ""),
        client_secret=os.getenv("CISCO_MODERN_API_SECRET") or os.getenv("NBCOT_CLIENT_SECRET", ""),
    )


def mask(value: str) -> str:
    """Return a masked version of a sensitive token or identifier."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def get_access_token(session: requests.Session, context: CiscoContext) -> str:
    """Request an OAuth token from Cisco."""
    response = session.post(
        context.token_url,
        data={"grant_type": "client_credentials"},
        auth=(context.client_id, context.client_secret),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"Token response did not include access_token: {payload}")
    return token


def execute_graphql(
    session: requests.Session,
    context: CiscoContext,
    token: str,
    operation_name: str,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Execute one GraphQL operation and return a sanitized result block."""
    response = session.post(
        context.graphql_endpoint,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=60,
    )
    body: dict[str, Any] | str
    try:
        body = response.json()
    except ValueError:
        body = response.text

    return {
        "operation_name": operation_name,
        "http_status": response.status_code,
        "variables": variables,
        "body": body,
    }


def build_order_search_input(order_number: str) -> dict[str, Any]:
    """Construct the order input used in NBCOT."""
    return {
        "orderSearchCriteria": [
            {"orderSearchKey": "SALES_ORDER_ID", "orderSearchValue": str(order_number)},
        ],
        "sortByOrderCharacteristics": "CREATION_DATE",
        "pagination": {"page": 1, "pageSize": 20, "sortOrder": "DESC"},
    }


def build_subscription_detail_input(subscription_id: str) -> dict[str, Any]:
    """Construct an exact subscription detail lookup."""
    return {
        "mySubscriptionIds": [str(subscription_id)],
        "mySubscriptionSearchCriteria": [
            {"mySubscriptionSearchKey": "FROM_DATE", "mySubscriptionSearchValue": "2022-01-01"},
            {"mySubscriptionSearchKey": "TO_DATE", "mySubscriptionSearchValue": "2035-12-31"},
        ],
        "pagination": {"page": 1, "pageSize": 20, "sortOrder": "DESC"},
    }


def build_subscription_party_input(*, party_type: str, party_id: str | None = None, party_name: str | None = None) -> dict[str, Any]:
    """Construct a CCW-R party/date search payload."""
    party: dict[str, str] = {"type": party_type}
    if party_id:
        party["id"] = party_id
    if party_name:
        party["name"] = party_name
    return {
        "party": [party],
        "mySubscriptionSearchCriteria": [
            {"mySubscriptionSearchKey": "FROM_DATE", "mySubscriptionSearchValue": "2022-01-01"},
            {"mySubscriptionSearchKey": "TO_DATE", "mySubscriptionSearchValue": "2035-12-31"},
        ],
        "pagination": {"page": 1, "pageSize": 20, "sortOrder": "DESC"},
    }


def default_cases() -> list[dict[str, Any]]:
    """Return the current repro matrix."""
    return [
        {
            "label": "order_search_119998164",
            "operation_name": "searchOrder",
            "query": ORDER_SEARCH_QUERY,
            "variables": {"input": build_order_search_input("119998164")},
        },
        {
            "label": "order_details_119998164",
            "operation_name": "getOrderDetails",
            "query": ORDER_DETAILS_QUERY,
            "variables": {"input": build_order_search_input("119998164")},
        },
        {
            "label": "subscription_details_205093077",
            "operation_name": "getSubscriptionDetails",
            "query": SUBSCRIPTION_DETAILS_QUERY,
            "variables": {"input": build_subscription_detail_input("205093077")},
        },
        {
            "label": "subscription_details_205342378",
            "operation_name": "getSubscriptionDetails",
            "query": SUBSCRIPTION_DETAILS_QUERY,
            "variables": {"input": build_subscription_detail_input("205342378")},
        },
        {
            "label": "subscription_details_207008120",
            "operation_name": "getSubscriptionDetails",
            "query": SUBSCRIPTION_DETAILS_QUERY,
            "variables": {"input": build_subscription_detail_input("207008120")},
        },
        {
            "label": "subscription_search_end_customer_ahepa_general_hospital",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {
                "input": build_subscription_party_input(
                    party_type="END_CUSTOMER",
                    party_name="AHEPA GENERAL HOSPITAL",
                )
            },
        },
        {
            "label": "subscription_search_end_customer_general_hospital_ahepa_th_essaloniki",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {
                "input": build_subscription_party_input(
                    party_type="END_CUSTOMER",
                    party_name="GENERAL HOSPITAL AHEPA TH ESSALONIKI",
                )
            },
        },
        {
            "label": "subscription_search_install_site_1084635571",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {"input": build_subscription_party_input(party_type="INSTALL_SITE", party_id="1084635571")},
        },
        {
            "label": "subscription_search_install_site_1038716884",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {"input": build_subscription_party_input(party_type="INSTALL_SITE", party_id="1038716884")},
        },
        {
            "label": "subscription_search_bill_to_30402848",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {"input": build_subscription_party_input(party_type="BILL_TO", party_id="30402848")},
        },
        {
            "label": "subscription_search_bill_to_1005803060",
            "operation_name": "searchSubscription",
            "query": SUBSCRIPTION_SEARCH_QUERY,
            "variables": {"input": build_subscription_party_input(party_type="BILL_TO", party_id="1005803060")},
        },
    ]


def render_markdown(environment: str, context: CiscoContext, token: str, cases: list[dict[str, Any]]) -> str:
    """Render a copy-paste-ready markdown report."""
    lines = []
    lines.append(f"# Cisco Modern Commerce API Repro ({environment.upper()})")
    lines.append("")
    lines.append("This report was generated by a standalone Python script using OAuth client-credentials and direct GraphQL calls.")
    lines.append("")
    lines.append("## Runtime")
    lines.append("")
    lines.append(f"- Token URL: `{context.token_url}`")
    lines.append(f"- GraphQL Endpoint: `{context.graphql_endpoint}`")
    lines.append(f"- Client ID: `{mask(context.client_id)}`")
    lines.append(f"- OAuth token acquired successfully: `yes`")
    lines.append("- Access token value: withheld")
    lines.append("")

    for case in cases:
        lines.append(f"## {case['label']}")
        lines.append("")
        lines.append(f"- Operation: `{case['result']['operation_name']}`")
        lines.append(f"- HTTP status: `{case['result']['http_status']}`")
        lines.append("- Variables:")
        lines.append("```json")
        lines.append(json.dumps(case["result"]["variables"], indent=2))
        lines.append("```")
        lines.append("- Response:")
        lines.append("```json")
        lines.append(json.dumps(case["result"]["body"], indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Run the repro matrix and print JSON or markdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=sorted(ENVIRONMENT_ENDPOINTS), default="prod")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    context = load_context(args.environment)
    if not context.client_id or not context.client_secret:
        print("Missing Cisco credentials in environment.", file=sys.stderr)
        return 2

    with requests.Session() as session:
        token = get_access_token(session, context)
        cases = default_cases()
        for case in cases:
            case["result"] = execute_graphql(
                session=session,
                context=context,
                token=token,
                operation_name=case["operation_name"],
                query=case["query"],
                variables=case["variables"],
            )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "environment": args.environment,
                    "token_url": context.token_url,
                    "graphql_endpoint": context.graphql_endpoint,
                    "client_id_masked": mask(context.client_id),
                    "token_masked": mask(token),
                    "cases": [case["result"] | {"label": case["label"]} for case in cases],
                },
                indent=2,
            )
        )
        return 0

    print(render_markdown(args.environment, context, token, cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

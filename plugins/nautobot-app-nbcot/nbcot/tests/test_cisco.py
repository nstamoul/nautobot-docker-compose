"""Tests for Cisco client, normalization, and sync logic."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from nbcot.cisco.client import CiscoGraphQLClient, CiscoSettings
from nbcot.cisco.exceptions import CiscoGraphQLError, NBCOTConfigurationError
from nbcot.cisco.line_items import build_line_tree, group_order_lines, line_number_sort_key
from nbcot.cisco.normalizers import CiscoPayloadNormalizer
from nbcot.cisco.sync import CiscoOrderSynchronizer
from nbcot.models import CiscoOrderLine, CiscoOrderUpdate
from nbcot.tests import fixtures


class FakeResponse:
    """Minimal fake requests.Response for client tests."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        """Return the configured payload."""
        return self._payload


class CiscoSettingsTest(TestCase):
    """Test settings validation."""

    @override_settings(PLUGINS_CONFIG={"nbcot": {"client_id": "", "client_secret": "", "graphql_endpoint": ""}})
    def test_validate_requires_credentials_and_endpoint(self):
        """Client settings should reject incomplete plugin configuration."""
        settings_obj = CiscoSettings.load()
        with self.assertRaises(NBCOTConfigurationError):
            settings_obj.validate()

    @override_settings(PLUGINS_CONFIG={"nbcot": {"graphql_endpoint": "https://example.invalid/graphql"}})
    def test_load_uses_cisco_env_vars_when_plugin_config_missing_credentials(self):
        """Client settings should fall back to the Cisco env var names used in deployment."""
        self.addCleanup(os.environ.pop, "CISCO_MODERN_API_CLIENT_ID", None)
        self.addCleanup(os.environ.pop, "CISCO_MODERN_API_SECRET", None)
        os.environ["CISCO_MODERN_API_CLIENT_ID"] = "env-client-id"
        os.environ["CISCO_MODERN_API_SECRET"] = "env-client-secret"

        settings_obj = CiscoSettings.load()

        self.assertEqual(settings_obj.client_id, "env-client-id")
        self.assertEqual(settings_obj.client_secret, "env-client-secret")

    @override_settings(PLUGINS_CONFIG={"nbcot": {"graphql_endpoint": "https://example.invalid/graphql"}})
    def test_load_uses_legacy_api_token_env_vars_when_plugin_config_missing_credentials(self):
        """Client settings should support the legacy Cisco OAuth env var names used by jobs."""
        for key in (
            "CISCO_MODERN_API_CLIENT_ID",
            "CISCO_MODERN_API_SECRET",
            "NBCOT_CLIENT_ID",
            "NBCOT_CLIENT_SECRET",
            "API_TOKEN_CLIENT_ID",
            "API_TOKEN_CLIENT_PASS",
        ):
            self.addCleanup(os.environ.pop, key, None)
            os.environ.pop(key, None)
        os.environ["API_TOKEN_CLIENT_ID"] = "legacy-client-id"
        os.environ["API_TOKEN_CLIENT_PASS"] = "legacy-client-secret"

        settings_obj = CiscoSettings.load()

        self.assertEqual(settings_obj.client_id, "legacy-client-id")
        self.assertEqual(settings_obj.client_secret, "legacy-client-secret")

    @override_settings(PLUGINS_CONFIG={"nbcot": {"graphql_endpoint": "https://example.invalid/graphql"}})
    def test_load_uses_vault_credentials_when_env_credentials_missing(self):
        """Client settings should resolve Cisco OAuth credentials from the configured Vault path."""
        for key in (
            "CISCO_MODERN_API_CLIENT_ID",
            "CISCO_MODERN_API_SECRET",
            "NBCOT_CLIENT_ID",
            "NBCOT_CLIENT_SECRET",
            "API_TOKEN_CLIENT_ID",
            "API_TOKEN_CLIENT_PASS",
        ):
            self.addCleanup(os.environ.pop, key, None)
            os.environ.pop(key, None)
        resolver = MagicMock()
        resolver.resolve_mapping.return_value = {
            "client_id": "vault-client-id",
            "client_secret": "vault-client-secret",
        }
        with patch("nbcot.cisco.client.SecretResolver.from_env", return_value=resolver):
            settings_obj = CiscoSettings.load()

        self.assertEqual(settings_obj.client_id, "vault-client-id")
        self.assertEqual(settings_obj.client_secret, "vault-client-secret")

    @override_settings(
        PLUGINS_CONFIG={
            "nbcot": {
                "environment": "poe",
                "graphql_endpoint": "https://capitest.cisco.com/commerce/POE/apis",
            }
        }
    )
    def test_environment_override_uses_known_endpoint(self):
        """Explicit environment overrides should select that endpoint."""
        settings_obj = CiscoSettings.load(environment_override="prod")

        self.assertEqual(settings_obj.environment, "prod")
        self.assertEqual(settings_obj.graphql_endpoint, "https://capi.cisco.com/commerce/apis")


class CiscoGraphQLClientTest(SimpleTestCase):
    """Test OAuth token and GraphQL request construction."""

    @override_settings(
        PLUGINS_CONFIG={
            "nbcot": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "graphql_endpoint": "https://example.invalid/graphql",
            }
        }
    )
    def test_execute_uses_cached_token(self):
        """GraphQL client should cache access tokens between calls."""
        session = MagicMock()
        session.post.side_effect = [
            FakeResponse({"access_token": "abc", "expires_in": 3600}),
            FakeResponse({"data": {"searchOrder": []}}),
            FakeResponse({"data": {"searchOrder": []}}),
        ]
        client = CiscoGraphQLClient(http_session=session)
        client.search_orders({"orderNumber": "SO-1"})
        client.search_orders({"orderNumber": "SO-2"})
        self.assertEqual(session.post.call_count, 3)

    @override_settings(
        PLUGINS_CONFIG={
            "nbcot": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "graphql_endpoint": "https://example.invalid/graphql",
            }
        }
    )
    def test_execute_flattens_graphql_extension_messages(self):
        """GraphQL client should surface the vendor message instead of a raw error blob."""
        session = MagicMock()
        session.post.side_effect = [
            FakeResponse({"access_token": "abc", "expires_in": 3600}),
            FakeResponse(
                {
                    "errors": [
                        {
                            "message": "TechnicalException",
                            "extensions": {
                                "messages": [
                                    {
                                        "code": "SERVICE_ERROR",
                                        "description": "Unable to fetch data from Core SearchOrder API",
                                    }
                                ]
                            },
                        }
                    ]
                }
            ),
        ]
        client = CiscoGraphQLClient(http_session=session)

        with self.assertRaises(CiscoGraphQLError) as exc:
            client.execute("query { __typename }")

        self.assertEqual(str(exc.exception), "Unable to fetch data from Core SearchOrder API")

    def test_build_order_search_input_supports_portal_search_fields(self):
        """Order search input should support the same key fields exposed by Cisco's portal."""
        search_input = CiscoGraphQLClient._build_order_search_input(
            {
                "sales_order_number": "119998164",
                "order_name": "AHEPA Infra Refresh",
                "web_order_id": "11001048032",
                "subscription_id": "SUB-123",
                "purchase_order": "1573/26B",
                "deal_id": "73455770",
                "end_customer_name": "AHEPA",
                "end_customer_number": "EC-1",
                "end_customer_po_number": "ECPO-1",
                "bill_to_address_id": "BILL-1",
                "order_status": "CLOSED",
            }
        )

        self.assertEqual(
            search_input["orderSearchCriteria"],
            [
                {"orderSearchKey": "SALES_ORDER_ID", "orderSearchValue": "119998164"},
                {"orderSearchKey": "ORDER_NAME", "orderSearchValue": "AHEPA Infra Refresh"},
                {"orderSearchKey": "WEB_ORDER_ID", "orderSearchValue": "11001048032"},
                {"orderSearchKey": "SUBSCRIPTION_ID", "orderSearchValue": "SUB-123"},
                {"orderSearchKey": "PURCHASE_ORDER_ID", "orderSearchValue": "1573/26B"},
                {"orderSearchKey": "DEAL_ID", "orderSearchValue": "73455770"},
                {"orderSearchKey": "END_CUSTOMER_NAME", "orderSearchValue": "AHEPA"},
                {"orderSearchKey": "END_CUSTOMER_NUMBER", "orderSearchValue": "EC-1"},
                {"orderSearchKey": "END_CUSTOMER_PURCHASE_ORDER_NUMBER", "orderSearchValue": "ECPO-1"},
                {"orderSearchKey": "BILL_TO_ID", "orderSearchValue": "BILL-1"},
                {"orderSearchKey": "ORDER_STATUS", "orderSearchValue": "CLOSED"},
            ],
        )


class CiscoLineItemHelperTest(SimpleTestCase):
    """Test line item sorting and hierarchy helpers."""

    def test_line_number_sort_key_orders_dotted_numeric_paths_naturally(self):
        """Dotted line numbers should sort by numeric hierarchy instead of text."""
        line_numbers = ["11.0", "1.0.10", "1.0.2", "1.0", "10.0", "1.0.1", "2.0", "1.0.11.2"]

        self.assertEqual(
            sorted(line_numbers, key=line_number_sort_key),
            ["1.0", "1.0.1", "1.0.2", "1.0.10", "1.0.11.2", "2.0", "10.0", "11.0"],
        )

    def test_group_order_lines_places_minor_lines_under_major_lines(self):
        """Lines ending .0 should be group headers with nested minor lines below them."""
        lines = [
            SimpleNamespace(line_number="1.0.10", line_key="1.0.10"),
            SimpleNamespace(line_number="2.0", line_key="2.0"),
            SimpleNamespace(line_number="1.0", line_key="1.0"),
            SimpleNamespace(line_number="1.0.2", line_key="1.0.2"),
            SimpleNamespace(line_number="1.0.1", line_key="1.0.1"),
        ]

        groups = group_order_lines(lines)

        self.assertEqual([group.major.line_number for group in groups], ["1.0", "2.0"])
        self.assertEqual([line.line_number for line in groups[0].minor_lines], ["1.0.1", "1.0.2", "1.0.10"])
        self.assertEqual(groups[1].minor_lines, [])

    def test_build_line_tree_adds_submajor_level_below_root_line(self):
        """X.Y lines should be expandable parents under X.0 roots."""
        lines = [
            SimpleNamespace(line_number="45.1.1", line_key="45.1.1"),
            SimpleNamespace(line_number="45.1.0.1", line_key="45.1.0.1"),
            SimpleNamespace(line_number="45.1", line_key="45.1"),
            SimpleNamespace(line_number="45.0", line_key="45.0"),
            SimpleNamespace(line_number="1.0.1", line_key="1.0.1"),
            SimpleNamespace(line_number="1.0", line_key="1.0"),
            SimpleNamespace(line_number="1.0.0.1", line_key="1.0.0.1"),
        ]

        rows = build_line_tree(lines)
        rows_by_number = {row.line.line_number: row for row in rows}

        self.assertEqual(
            [row.line.line_number for row in rows],
            ["1.0", "1.0.0.1", "1.0.1", "45.0", "45.1", "45.1.0.1", "45.1.1"],
        )
        self.assertEqual(rows_by_number["45.0"].depth, 0)
        self.assertEqual(rows_by_number["45.1"].parent_id, rows_by_number["45.0"].row_id)
        self.assertEqual(rows_by_number["45.1"].depth, 1)
        self.assertTrue(rows_by_number["45.1"].has_children)
        self.assertEqual(rows_by_number["45.1.0.1"].parent_id, rows_by_number["45.1"].row_id)
        self.assertEqual(rows_by_number["45.1.1"].parent_id, rows_by_number["45.1"].row_id)


class CiscoPayloadNormalizerTest(TestCase):
    """Test payload normalization."""

    def setUp(self):
        """Instantiate the normalizer."""
        self.normalizer = CiscoPayloadNormalizer()

    def test_normalize_search_result(self):
        """Search results should map into the normalized dataclass."""
        result = self.normalizer.normalize_search_result(
            {
                "ciscoSalesOrderReference": {"ciscoSalesOrderId": "8001"},
                "buyerPurchaseOrderReference": {"purchaseOrderId": "PO-8001"},
                "parties": [{"id": "ACME-1", "name": "Acme", "type": "END_CUSTOMER"}],
                "orderStatus": "SUBMITTED",
                "messages": [
                    {"code": "WARN-1", "description": "Missing confirmation", "severity": "WARNING"},
                    {"code": "WARN-2", "description": "Pending review", "severity": "WARNING"},
                ],
            }
        )
        self.assertEqual(result.order_number, "8001")
        self.assertEqual(result.customer_po_number, "PO-8001")
        self.assertEqual(result.account_number, "ACME-1")
        self.assertEqual(result.open_exception_count, 2)

    def test_normalize_order_details(self):
        """Detail payload should capture lines and dates."""
        snapshot = self.normalizer.normalize_order_details(
            {
                "ciscoSalesOrderReference": {"ciscoSalesOrderId": "8002"},
                "buyerPurchaseOrderReference": {"purchaseOrderId": "PO-8002"},
                "parties": [{"id": "ACME-1", "name": "Acme", "type": "END_CUSTOMER"}],
                "orderStatus": "BOOKED",
                "businessStatus": "SUCCESS",
                "metaData": {"createdOn": "2026-04-16T08:30:00", "lastUpdatedAt": "2026-04-17T09:45:00"},
                "messages": [{"code": "WARN-1", "description": "Review required", "severity": "WARNING"}],
                "lines": [
                    {
                        "orderLineReference": {"lineId": "10", "userInterfaceLineId": "10"},
                        "item": {"sku": "SKU-10", "description": "Test SKU"},
                        "orderLineStatus": "AWAITING_FULFILLMENT",
                        "quantity": {"measurement": 2, "unitOfMeasure": "EA"},
                        "holdInformation": [
                            {
                                "name": "Credit Hold",
                                "description": "Finance review",
                                "reason": "Credit review",
                                "appliedDate": "2026-04-16T08:35:00",
                                "isPartnerActionRequired": True,
                            }
                        ],
                        "shippingAttributes": {
                            "shippedQty": 0,
                            "estimatedDeliveryDate": "2026-05-03",
                            "requestedDeliveryDate": "2026-05-01",
                            "promisedDate": "2026-05-02",
                            "shipSetStatus": "BACKORDERED",
                        },
                    }
                ],
            }
        )
        self.assertEqual(snapshot.order_number, "8002")
        self.assertEqual(len(snapshot.lines), 1)
        self.assertEqual(snapshot.lines[0].line_number, "10")
        self.assertEqual(snapshot.lines[0].quantity_backordered, 2)
        self.assertEqual(snapshot.promised_delivery_date.isoformat(), "2026-05-02")
        self.assertEqual(snapshot.open_exception_count, 2)


class CiscoOrderSynchronizerTest(TestCase):
    """Test persistence and change detection."""

    def _build_synchronizer(self, payload):
        client = SimpleNamespace(
            get_order_details=lambda _order_number: payload,
            search_orders=lambda _filters: [],
        )
        return CiscoOrderSynchronizer(client=client)

    def test_sync_is_idempotent_for_lines(self):
        """Repeated syncs should not duplicate line rows or updates."""
        payload = {
            "orderNumber": "SO-9001",
            "status": "Submitted",
            "lines": [{"lineNumber": "1", "sku": "SKU-1", "quantityOrdered": 1}],
        }
        synchronizer = self._build_synchronizer(payload)
        order, changes = synchronizer.sync_order_by_number("SO-9001")
        self.assertEqual(len(changes), 1)
        order, changes = synchronizer.sync_order_by_number("SO-9001")
        self.assertEqual(len(changes), 0)
        self.assertEqual(CiscoOrderLine.objects.filter(order=order).count(), 1)
        self.assertEqual(CiscoOrderUpdate.objects.filter(order=order).count(), 1)

    def test_sync_creates_status_change_update(self):
        """Changing the status should create a status_changed update."""
        synchronizer = self._build_synchronizer({"orderNumber": "SO-9002", "status": "Submitted", "lines": []})
        order, _ = synchronizer.sync_order_by_number("SO-9002")
        changed_synchronizer = self._build_synchronizer({"orderNumber": "SO-9002", "status": "Shipped", "lines": []})
        _, changes = changed_synchronizer.sync_order_by_number("SO-9002")
        self.assertEqual(len(changes), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, "Shipped")
        self.assertTrue(CiscoOrderUpdate.objects.filter(order=order, update_type="status_changed").exists())

    def test_sync_marks_selected_lines_tracked(self):
        """Synchronizer should persist item-level tracking choices by line key."""
        payload = {
            "orderNumber": "SO-9003",
            "status": "Submitted",
            "lines": [
                {"lineKey": "major-1", "lineNumber": "1.0"},
                {"lineKey": "minor-1", "lineNumber": "1.0.1"},
            ],
        }
        synchronizer = self._build_synchronizer(payload)

        order, _changes = synchronizer.sync_order_by_number("SO-9003", tracked_line_keys=["minor-1"])

        self.assertEqual(list(order.lines.filter(is_tracked=True).values_list("line_key", flat=True)), ["minor-1"])

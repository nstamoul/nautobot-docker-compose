"""Default GraphQL query documents for Cisco Commerce Modern APIs."""

DEFAULT_SEARCH_QUERY = """
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

DEFAULT_ORDER_DETAILS_QUERY = """
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

DEFAULT_SUBSCRIPTION_SEARCH_QUERY = """
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
      activationDate
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
        hasAutoRenewal
        billingPreference
        mySubscriptionStatus
        activationDate
      }
    }
  }
}
""".strip()

DEFAULT_SUBSCRIPTION_DETAILS_QUERY = """
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
      activationDate
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
        hasAutoRenewal
        billingPreference
        mySubscriptionStatus
        activationDate
      }
      lines {
        mySubscriptionLineReference {
          lineId
          parentLineId
        }
        orderReference {
          webOrderId
          submissionDate
          buyerPurchaseOrderReference {
            purchaseOrderId
          }
          ciscoSalesOrderReference {
            ciscoSalesOrderId
          }
        }
        orderLineReference {
          webOrderId
          lineId
          userInterfaceLineId
          purchaseOrderLineReference
        }
        quantity {
          measurement
          unitOfMeasure
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

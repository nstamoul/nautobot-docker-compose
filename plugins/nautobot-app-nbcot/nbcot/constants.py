"""Constants used by NBCOT."""

UAT_GRAPHQL_ENDPOINT = "https://capitest.cisco.com/commerce/UAT/apis"
POE_GRAPHQL_ENDPOINT = "https://capitest.cisco.com/commerce/POE/apis"
PROD_GRAPHQL_ENDPOINT = "https://capi.cisco.com/commerce/apis"
DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"

ENVIRONMENT_ENDPOINTS = {
    "uat": UAT_GRAPHQL_ENDPOINT,
    "poe": POE_GRAPHQL_ENDPOINT,
    "prod": PROD_GRAPHQL_ENDPOINT,
}

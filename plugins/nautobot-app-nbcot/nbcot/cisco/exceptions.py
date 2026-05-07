"""Exceptions raised by the Cisco Commerce integration layer."""


class NBCOTConfigurationError(RuntimeError):
    """Raised when NBCOT plugin settings are incomplete."""


class CiscoAuthenticationError(RuntimeError):
    """Raised when OAuth token retrieval fails."""


class CiscoGraphQLError(RuntimeError):
    """Raised when Cisco GraphQL returns errors."""

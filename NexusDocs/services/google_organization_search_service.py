"""Google AI Mode organization-header search.

The parser implementation remains compatible with the response protocol used
by earlier NexusDocs releases, while the public API now names the active
provider explicitly.
"""

from services.alice_organization_search_service import (
    GoogleOrganizationSearchService,
    GoogleResponseError,
    GoogleSearchRequest,
)

__all__ = (
    "GoogleOrganizationSearchService",
    "GoogleResponseError",
    "GoogleSearchRequest",
)

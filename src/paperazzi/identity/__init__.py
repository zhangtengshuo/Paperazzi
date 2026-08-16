"""Phase 4 author identity and local semantic resolution."""

from .normalization import NameFeatures, normalize_name, normalize_search_text, name_features
from .service import (
    IdentityResolutionError,
    accept_membership,
    bootstrap_author_identities,
    merge_authors,
    split_mention,
)

__all__ = [
    "NameFeatures",
    "normalize_name",
    "normalize_search_text",
    "name_features",
    "IdentityResolutionError",
    "accept_membership",
    "bootstrap_author_identities",
    "merge_authors",
    "split_mention",
]

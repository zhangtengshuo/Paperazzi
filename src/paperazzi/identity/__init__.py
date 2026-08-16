"""Phase 4 author identity and local semantic resolution."""

from .authorship_evidence import accept_authorship_evidence, propose_authorship_evidence
from .normalization import NameFeatures, name_features, normalize_name, normalize_search_text
from .operations import (
    add_external_id,
    mark_not_same_person,
    set_identity_lock,
    unlink_mention,
)
from .reference_resolution import LocalReferenceResolver, normalize_doi, normalize_title
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
    "unlink_mention",
    "mark_not_same_person",
    "set_identity_lock",
    "add_external_id",
    "propose_authorship_evidence",
    "accept_authorship_evidence",
    "LocalReferenceResolver",
    "normalize_doi",
    "normalize_title",
]

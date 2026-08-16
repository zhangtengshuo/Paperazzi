"""Phase 4 author identity and local semantic resolution."""

# Import the stable bootstrap first.  It compatibility-patches the historical
# paperazzi.identity.service import path so existing callers get the source-stable
# resolver without breaking merge/split/manual-operation APIs.
from . import stable_bootstrap as _stable_bootstrap
from .source_seed import seed_required_name_multiplicity

_stable_bootstrap._seed_required_name_multiplicity = seed_required_name_multiplicity

bootstrap_author_identities = _stable_bootstrap.bootstrap_author_identities
score_mention_against_author = _stable_bootstrap.score_mention_against_author

from .authorship_evidence import accept_authorship_evidence, propose_authorship_evidence
from .normalization import NameFeatures, name_features, normalize_name, normalize_search_text
from .operations import (
    add_external_id,
    mark_not_same_person,
    set_identity_lock,
    unlink_mention,
)
from .reference_operations import (
    ReferenceResolutionError,
    accept_reviewed_reference_match,
    reject_reference_match,
    resolve_reference_review_queue_item,
)
from .reference_resolution import LocalReferenceResolver, normalize_doi, normalize_title
from .service import (
    IdentityResolutionError,
    accept_membership,
    merge_authors,
    split_mention,
)
from .source_collaboration import SourceCollaborationIndex

__all__ = [
    "NameFeatures",
    "normalize_name",
    "normalize_search_text",
    "name_features",
    "IdentityResolutionError",
    "accept_membership",
    "bootstrap_author_identities",
    "score_mention_against_author",
    "SourceCollaborationIndex",
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
    "ReferenceResolutionError",
    "accept_reviewed_reference_match",
    "reject_reference_match",
    "resolve_reference_review_queue_item",
]

"""Versioned Phase 4 resolution policy.

Thresholds are deliberately centralized so persisted resolver decisions can be
reproduced and later superseded by a new policy version without rewriting history.
"""

POLICY_VERSION = "phase4-resolution-policy-v1"

# Author identity: normalized-name evidence alone can never satisfy these guards.
IDENTITY_AUTO_ACCEPT_SCORE = 0.85
IDENTITY_AUTO_ACCEPT_MARGIN = 0.15
IDENTITY_MIN_COAUTHOR_OVERLAP = 2

# Reference matching.
REFERENCE_MIN_CANDIDATE_SCORE = 0.55
REFERENCE_TITLE_AUTO_ACCEPT_SCORE = 0.90
REFERENCE_TITLE_AUTO_ACCEPT_MARGIN = 0.12
REFERENCE_JVPY_AUTO_ACCEPT_SCORE = 0.90
REFERENCE_JVPY_AUTO_ACCEPT_MARGIN = 0.15
REFERENCE_MAX_STORED_CANDIDATES = 5

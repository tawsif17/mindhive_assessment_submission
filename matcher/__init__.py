"""Public interface for the tenant-scoped order-line matcher."""

from .core import Matcher
from .types import CandidateEvidence, MatchResult, OrderLine

__all__ = ["CandidateEvidence", "MatchResult", "Matcher", "OrderLine"]


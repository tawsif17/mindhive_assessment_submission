"""Plain data types used by the matcher and evaluation harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class OrderLine:
    """Fields that are visible when one order line is matched."""

    line_id: str
    tenant: str
    customer_id: str
    channel: str
    order_date: str
    raw_text: str
    qty: str = ""
    uom_text: str = ""
    unit_price: str = ""
    buyer_sku: str = ""
    raw_barcode: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "OrderLine":
        """Create an order line from a CSV row and ignore label-only columns."""
        return cls(**{name: row.get(name, "").strip() for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class CatalogueItem:
    """One catalogue row with the fields used during matching."""

    tenant: str
    item_code: str
    item_name: str
    description: str
    brand: str
    item_group: str
    stock_uom: str
    barcode: str
    manufacturer_part_no: str
    disabled: bool
    list_price: float | None
    is_misc: bool
    search_text: str
    name_text: str
    uom_conversions: dict[str, float]


@dataclass(frozen=True)
class AliasRecord:
    """One customer-specific alias mapping."""

    tenant: str
    customer_id: str
    customer_sku: str
    item_code: str
    customer_description: str
    valid_from: str
    valid_to: str
    source: str
    confidence: float


@dataclass
class CandidateEvidence:
    """Separate facts collected for one candidate item."""

    item_code: str
    item_name: str
    tenant: str
    rapidfuzz_score: float = 0.0
    word_tfidf_score: float = 0.0
    char_tfidf_score: float = 0.0
    item_code_exact: bool = False
    barcode_exact: bool = False
    part_number_exact: bool = False
    alias_exact: bool = False
    alias_source: str = ""
    alias_confidence: float = 0.0
    brand_match: bool = False
    family_overlap: float = 0.0
    size_overlap: float = 0.0
    size_completeness: float = 0.0
    uom_match: bool = False
    price_similarity: float = 0.0
    active_twin: bool = False
    identifier_conflict: bool = False
    attribute_conflict: bool = False
    disabled_alias_target: bool = False
    score: float = 0.0
    confidence: float = 0.0
    margin: float = 0.0
    safety_blocks: list[str] = field(default_factory=list)

    def has_strong_identifier(self) -> bool:
        """Return whether a unique, active identifier proves this candidate."""
        trusted_alias = (
            self.alias_exact
            and self.alias_confidence >= 0.99
            and self.alias_source in {"confirmed_order", "manual_import"}
        )
        return bool(
            self.item_code_exact
            or self.barcode_exact
            or self.part_number_exact
            or trusted_alias
        )

    def feature_values(self) -> list[float]:
        """Return features in the stable order used by the ranker."""
        return [
            self.rapidfuzz_score,
            self.word_tfidf_score,
            self.char_tfidf_score,
            float(self.item_code_exact),
            float(self.barcode_exact),
            float(self.part_number_exact),
            float(self.alias_exact),
            self.alias_confidence,
            float(self.brand_match),
            self.family_overlap,
            self.size_overlap,
            self.size_completeness,
            float(self.uom_match),
            self.price_similarity,
            float(self.active_twin),
            float(self.identifier_conflict),
            float(self.attribute_conflict),
            float(self.disabled_alias_target),
        ]

    def to_dict(self) -> dict[str, Any]:
        """Return evidence in a serialisable form."""
        return asdict(self)


FEATURE_NAMES = [
    "rapidfuzz_score",
    "word_tfidf_score",
    "char_tfidf_score",
    "item_code_exact",
    "barcode_exact",
    "part_number_exact",
    "alias_exact",
    "alias_confidence",
    "brand_match",
    "family_overlap",
    "size_overlap",
    "size_completeness",
    "uom_match",
    "price_similarity",
    "active_twin",
    "identifier_conflict",
    "attribute_conflict",
    "disabled_alias_target",
]


@dataclass
class MatchResult:
    """One matcher response with prediction fields and detailed evidence."""

    line_id: str
    item_code: str
    confidence: float
    decision: str
    reason_code: str
    candidates: list[CandidateEvidence]
    latency_ms: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def candidate_string(self) -> str:
        """Format at most three candidates for predictions.csv."""
        return "|".join(
            f"{candidate.item_code}:{candidate.confidence:.6f}"
            for candidate in self.candidates[:3]
        )

    def to_prediction_row(self) -> dict[str, str]:
        """Return the exact fields required by the assessment."""
        return {
            "line_id": self.line_id,
            "item_code": self.item_code if self.decision == "auto" else "",
            "confidence": f"{max(0.0, min(1.0, self.confidence)):.6f}",
            "decision": self.decision,
            "reason_code": self.reason_code,
            "candidates": self.candidate_string(),
        }

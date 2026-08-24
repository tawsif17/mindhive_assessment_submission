"""Tenant-scoped matching, evidence collection, ranking, and safe decisions."""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz, process
from sklearn.feature_extraction.text import TfidfVectorizer

from .data import MatcherData, load_matcher_data
from .model import ProbabilityRanker
from .text import (
    is_non_item_text,
    normalise_identifier,
    normalise_order_text,
    normalise_text,
    normalise_uom,
    numeric_tokens,
    text_tokens,
)
from .types import AliasRecord, CandidateEvidence, CatalogueItem, MatchResult, OrderLine


DEFAULT_CONFIDENCE_THRESHOLD = 0.98
DEFAULT_MARGIN_THRESHOLD = 0.08
MIN_REVIEW_CONFIDENCE = 0.05


class TenantIndex:
    """Search indexes that contain active, sellable rows for one tenant only."""

    def __init__(self, tenant: str, items: list[CatalogueItem]) -> None:
        self.tenant = tenant
        self.items = sorted(
            [item for item in items if not item.disabled and not item.is_misc],
            key=lambda item: item.item_code,
        )
        self.by_code = {normalise_identifier(item.item_code): item for item in self.items}
        self.by_barcode = self._multi_index(self.items, "barcode")
        self.by_part_number = self._multi_index(self.items, "manufacturer_part_no")
        self.by_name: dict[str, list[CatalogueItem]] = defaultdict(list)
        for item in self.items:
            self.by_name[item.name_text].append(item)

        self.search_texts = [item.search_text for item in self.items]
        self.word_vectorizer = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True
        )
        self.char_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True
        )
        self.word_matrix = self.word_vectorizer.fit_transform(self.search_texts)
        self.char_matrix = self.char_vectorizer.fit_transform(self.search_texts)

    @staticmethod
    def _multi_index(
        items: Iterable[CatalogueItem], field_name: str
    ) -> dict[str, list[CatalogueItem]]:
        index: dict[str, list[CatalogueItem]] = defaultdict(list)
        for item in items:
            value = normalise_identifier(getattr(item, field_name))
            if value:
                index[value].append(item)
        return dict(index)

    def vector_scores(self, query: str, kind: str) -> list[float]:
        """Return cosine scores for every item in a stable catalogue order."""
        if not query:
            return [0.0] * len(self.items)
        if kind == "word":
            query_vector = self.word_vectorizer.transform([query])
            scores = self.word_matrix @ query_vector.T
        elif kind == "char":
            query_vector = self.char_vectorizer.transform([query])
            scores = self.char_matrix @ query_vector.T
        else:
            raise ValueError(f"Unknown vector score kind: {kind}")
        return [float(value) for value in scores.toarray().ravel()]


class Matcher:
    """Resolve one visible order line to an item or a safe abstention."""

    def __init__(
        self,
        data: MatcherData,
        ranker: ProbabilityRanker | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    ) -> None:
        self.data = data
        self.ranker = ranker
        self.confidence_threshold = confidence_threshold
        self.margin_threshold = margin_threshold
        self.indexes = {
            tenant: TenantIndex(tenant, items)
            for tenant, items in sorted(data.items_by_tenant.items())
        }
        self.alias_index: dict[tuple[str, str, str], list[AliasRecord]] = defaultdict(list)
        for alias in data.aliases:
            key = (
                alias.tenant,
                alias.customer_id,
                normalise_identifier(alias.customer_sku),
            )
            self.alias_index[key].append(alias)

    @classmethod
    def from_data_dir(
        cls,
        data_dir: str | Path,
        *,
        include_aliases: bool = True,
        ranker: ProbabilityRanker | None = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
    ) -> "Matcher":
        """Build a matcher from read-only CSV files."""
        data = load_matcher_data(data_dir, include_aliases=include_aliases)
        return cls(data, ranker, confidence_threshold, margin_threshold)

    def with_ranker(
        self,
        ranker: ProbabilityRanker,
        confidence_threshold: float | None = None,
        margin_threshold: float | None = None,
    ) -> "Matcher":
        """Return a matcher that shares data but uses a fitted ranker."""
        return Matcher(
            self.data,
            ranker=ranker,
            confidence_threshold=(
                self.confidence_threshold
                if confidence_threshold is None
                else confidence_threshold
            ),
            margin_threshold=(
                self.margin_threshold if margin_threshold is None else margin_threshold
            ),
        )

    def retrieve(
        self,
        line: OrderLine,
        strategy: str = "hybrid",
        candidate_limit: int = 20,
    ) -> tuple[list[CandidateEvidence], dict[str, object]]:
        """Generate and score candidates without making an AUTO decision."""
        tenant = line.tenant.lower()
        if tenant not in self.indexes:
            raise ValueError(f"Unknown tenant: {line.tenant}")
        index = self.indexes[tenant]
        query = normalise_order_text(" ".join([line.raw_text, line.notes]))
        item_by_code = {item.item_code: item for item in index.items}
        candidate_codes: set[str] = set()
        lane_codes: dict[str, set[str]] = defaultdict(set)

        identifier_values = {
            normalise_identifier(line.buyer_sku),
            normalise_identifier(line.raw_barcode),
            normalise_identifier(line.raw_text),
        }
        identifier_values.discard("")
        embedded_numbers = set(re.findall(r"\b\d{8,14}\b", line.raw_text))
        identifier_values.update(normalise_identifier(value) for value in embedded_numbers)

        # Item codes are checked before text retrieval and inside the tenant index.
        for item in index.items:
            code_value = normalise_identifier(item.item_code)
            if code_value in identifier_values or code_value in normalise_identifier(line.raw_text):
                lane_codes["item_code"].add(item.item_code)

        barcode_targets: set[str] = set()
        part_targets: set[str] = set()
        for value in identifier_values:
            barcode_targets.update(item.item_code for item in index.by_barcode.get(value, []))
            part_targets.update(item.item_code for item in index.by_part_number.get(value, []))
        lane_codes["barcode"].update(barcode_targets)
        lane_codes["part_number"].update(part_targets)

        alias_records = self._current_aliases(line)
        active_alias_targets: set[str] = set()
        disabled_alias_targets: set[str] = set()
        for alias in alias_records:
            target = self.data.all_items_by_code[alias.item_code]
            if target.disabled or target.is_misc:
                disabled_alias_targets.add(target.item_code)
            elif target.tenant == tenant:
                active_alias_targets.add(target.item_code)
        lane_codes["alias"].update(active_alias_targets)

        rapid_scores: dict[str, float] = {}
        word_scores: dict[str, float] = {}
        char_scores: dict[str, float] = {}
        if query and strategy in {"rapidfuzz", "hybrid"}:
            matches = process.extract(
                query,
                index.search_texts,
                scorer=fuzz.WRatio,
                limit=min(candidate_limit, len(index.items)),
            )
            for _text, score, item_index in matches:
                item_code = index.items[item_index].item_code
                rapid_scores[item_code] = score / 100.0
                lane_codes["rapidfuzz"].add(item_code)

        if strategy in {"word_tfidf", "hybrid"}:
            scores = index.vector_scores(query, "word")
            for item_index in self._top_indexes(scores, candidate_limit):
                item_code = index.items[item_index].item_code
                word_scores[item_code] = scores[item_index]
                lane_codes["word_tfidf"].add(item_code)

        if strategy in {"char_tfidf", "hybrid"}:
            scores = index.vector_scores(query, "char")
            for item_index in self._top_indexes(scores, candidate_limit):
                item_code = index.items[item_index].item_code
                char_scores[item_code] = scores[item_index]
                lane_codes["char_tfidf"].add(item_code)

        if strategy == "exact":
            used_lanes = {"item_code", "barcode", "part_number", "alias"}
        else:
            used_lanes = {"item_code", "barcode", "part_number", "alias", strategy}
            if strategy == "hybrid":
                used_lanes = set(lane_codes)
        for lane in used_lanes:
            candidate_codes.update(lane_codes.get(lane, set()))

        identifier_target_sets = [
            values
            for values in (
                lane_codes["item_code"], barcode_targets, part_targets, active_alias_targets
            )
            if values
        ]
        combined_identifier_targets = set().union(*identifier_target_sets) if identifier_target_sets else set()
        identifier_conflict = len(combined_identifier_targets) > 1

        evidence_rows: list[CandidateEvidence] = []
        for item_code in sorted(candidate_codes):
            item = item_by_code[item_code]
            alias_for_item = [record for record in alias_records if record.item_code == item_code]
            evidence = self._build_evidence(
                line=line,
                item=item,
                rapid_score=rapid_scores.get(item_code, self._rapid_score(query, item.search_text)),
                word_score=word_scores.get(item_code, 0.0),
                char_score=char_scores.get(item_code, 0.0),
                item_code_exact=item_code in lane_codes["item_code"],
                barcode_exact=item_code in barcode_targets,
                part_number_exact=item_code in part_targets,
                alias_records=alias_for_item,
                identifier_conflict=identifier_conflict,
                disabled_alias_target=bool(disabled_alias_targets),
                index=index,
            )
            evidence_rows.append(evidence)

        self._score_candidates(evidence_rows)
        for evidence in evidence_rows:
            if evidence.has_strong_identifier() and not evidence.safety_blocks:
                evidence.confidence = 1.0
        evidence_rows.sort(key=lambda row: (-row.confidence, -row.score, row.item_code))
        if evidence_rows:
            second = evidence_rows[1].confidence if len(evidence_rows) > 1 else 0.0
            margin = evidence_rows[0].confidence - second
            evidence_rows[0].margin = margin
        metadata: dict[str, object] = {
            "query": query,
            "lanes": {name: sorted(values) for name, values in sorted(lane_codes.items())},
            "disabled_alias_targets": sorted(disabled_alias_targets),
            "identifier_conflict": identifier_conflict,
        }
        return evidence_rows[:candidate_limit], metadata

    def match(self, line: OrderLine) -> MatchResult:
        """Return one deterministic match or a review/reject abstention."""
        started = time.perf_counter()
        try:
            if not line.line_id or not line.tenant or not line.raw_text:
                return self._result(line.line_id, "", 0.0, "reject", "invalid_input", [], started)
            if line.tenant.lower() not in self.indexes:
                return self._result(line.line_id, "", 0.0, "reject", "invalid_input", [], started)
            if is_non_item_text(line.raw_text):
                return self._result(line.line_id, "", 0.0, "reject", "not_an_item", [], started)
            candidates, metadata = self.retrieve(line)
        except (TypeError, ValueError):
            return self._result(line.line_id, "", 0.0, "reject", "invalid_input", [], started)

        if not candidates:
            return self._result(line.line_id, "", 0.0, "reject", "no_candidate", [], started)

        top = candidates[0]
        reason = self._reason_for(top)
        if not top.safety_blocks:
            threshold_passed = (
                top.confidence >= self.confidence_threshold
                and top.margin >= self.margin_threshold
            )
            if top.has_strong_identifier() or threshold_passed:
                return self._result(
                    line.line_id, top.item_code, top.confidence, "auto", reason,
                    candidates[:3], started, metadata,
                )
        if top.confidence >= MIN_REVIEW_CONFIDENCE:
            review_reason = top.safety_blocks[0] if top.safety_blocks else (
                "low_margin" if top.margin < self.margin_threshold else "low_confidence"
            )
            return self._result(
                line.line_id, "", top.confidence, "review", review_reason,
                candidates[:3], started, metadata,
            )
        return self._result(
            line.line_id, "", top.confidence, "reject", "no_candidate",
            candidates[:3], started, metadata,
        )

    def _current_aliases(self, line: OrderLine) -> list[AliasRecord]:
        sku = normalise_identifier(line.buyer_sku)
        if not sku:
            return []
        records = self.alias_index.get((line.tenant.lower(), line.customer_id, sku), [])
        try:
            order_day = date.fromisoformat(line.order_date)
        except ValueError:
            return []
        current: list[AliasRecord] = []
        for record in records:
            valid_from = date.fromisoformat(record.valid_from)
            valid_to = date.fromisoformat(record.valid_to) if record.valid_to else None
            if valid_from <= order_day and (valid_to is None or order_day <= valid_to):
                current.append(record)
        return current

    @staticmethod
    def _top_indexes(scores: list[float], limit: int) -> list[int]:
        return [
            index
            for index, score in sorted(
                enumerate(scores), key=lambda pair: (-pair[1], pair[0])
            )[:limit]
            if score > 0.0
        ]

    @staticmethod
    def _rapid_score(query: str, target: str) -> float:
        return fuzz.WRatio(query, target) / 100.0 if query else 0.0

    def _build_evidence(
        self,
        *,
        line: OrderLine,
        item: CatalogueItem,
        rapid_score: float,
        word_score: float,
        char_score: float,
        item_code_exact: bool,
        barcode_exact: bool,
        part_number_exact: bool,
        alias_records: list[AliasRecord],
        identifier_conflict: bool,
        disabled_alias_target: bool,
        index: TenantIndex,
    ) -> CandidateEvidence:
        line_tokens = text_tokens(line.raw_text)
        item_tokens = text_tokens(item.item_name)
        item_family = text_tokens(item.item_group.split(">")[-1])
        line_numbers = numeric_tokens(line.raw_text)
        item_numbers = numeric_tokens(item.item_name + " " + item.description)
        size_overlap = self._overlap(line_numbers, item_numbers)
        size_completeness = self._overlap(item_numbers, line_numbers)
        family_overlap = self._overlap(line_tokens, item_family)
        brand_match = normalise_text(item.brand) in normalise_text(line.raw_text)
        line_uom = normalise_uom(line.uom_text)
        valid_uoms = set(item.uom_conversions) | {normalise_uom(item.stock_uom)}
        uom_match = bool(line_uom and line_uom in valid_uoms)
        size_conflict = bool(line_numbers and item_numbers and size_overlap < 1.0)
        uom_conflict = bool(line_uom and line_uom not in valid_uoms)
        attribute_conflict = size_conflict or uom_conflict
        alias_confidence = max((record.confidence for record in alias_records), default=0.0)
        alias_source = max(
            alias_records,
            key=lambda record: (record.confidence, record.source),
            default=None,
        )
        active_twin = len(index.by_name.get(item.name_text, [])) > 1
        price_similarity = self._price_similarity(line.unit_price, item.list_price)
        evidence = CandidateEvidence(
            item_code=item.item_code,
            item_name=item.item_name,
            tenant=item.tenant,
            rapidfuzz_score=rapid_score,
            word_tfidf_score=word_score,
            char_tfidf_score=char_score,
            item_code_exact=item_code_exact,
            barcode_exact=barcode_exact,
            part_number_exact=part_number_exact,
            alias_exact=bool(alias_records),
            alias_source=alias_source.source if alias_source else "",
            alias_confidence=alias_confidence,
            brand_match=brand_match,
            family_overlap=family_overlap,
            size_overlap=size_overlap,
            size_completeness=size_completeness,
            uom_match=uom_match,
            price_similarity=price_similarity,
            active_twin=active_twin,
            identifier_conflict=identifier_conflict,
            attribute_conflict=attribute_conflict,
            disabled_alias_target=disabled_alias_target,
        )
        if identifier_conflict:
            evidence.safety_blocks.append("identifier_ambiguous")
        if active_twin:
            evidence.safety_blocks.append("active_twin")
        if attribute_conflict:
            evidence.safety_blocks.append("attribute_conflict")
        if (
            evidence.alias_exact
            and not self._is_trusted_alias(alias_records)
            and not self._has_independent_catalogue_support(evidence)
        ):
            evidence.safety_blocks.append("alias_not_trusted")
        if disabled_alias_target:
            evidence.safety_blocks.append("alias_disabled_target")
        return evidence

    def _score_candidates(self, candidates: list[CandidateEvidence]) -> None:
        if not candidates:
            return
        if self.ranker is not None:
            probabilities = self.ranker.predict(
                [candidate.feature_values() for candidate in candidates]
            )
            for candidate, probability in zip(candidates, probabilities):
                candidate.score = probability
                candidate.confidence = probability
            return
        for candidate in candidates:
            identifier_score = max(
                float(candidate.item_code_exact),
                float(candidate.barcode_exact),
                float(candidate.part_number_exact),
                candidate.alias_confidence if candidate.alias_exact else 0.0,
            )
            text_score = (
                0.35 * candidate.rapidfuzz_score
                + 0.25 * candidate.word_tfidf_score
                + 0.25 * candidate.char_tfidf_score
                + 0.08 * float(candidate.brand_match)
                + 0.07 * candidate.family_overlap
            )
            structured = 0.08 * candidate.size_overlap + 0.03 * float(candidate.uom_match)
            conflict_penalty = 0.25 * float(candidate.attribute_conflict)
            candidate.score = max(identifier_score, min(1.0, text_score + structured))
            candidate.confidence = max(0.0, min(0.995, candidate.score - conflict_penalty))

    @staticmethod
    def _overlap(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left.intersection(right)) / len(left)

    @staticmethod
    def _price_similarity(value: str, catalogue_price: float | None) -> float:
        if not value.strip() or catalogue_price is None or catalogue_price <= 0:
            return 0.0
        try:
            order_price = float(value)
        except ValueError:
            return 0.0
        ratio = abs(order_price - catalogue_price) / catalogue_price
        return math.exp(-4.0 * ratio)

    @staticmethod
    def _is_trusted_alias(records: list[AliasRecord]) -> bool:
        targets = {record.item_code for record in records}
        return (
            len(targets) == 1
            and any(
                record.confidence >= 0.99
                and record.source in {"confirmed_order", "manual_import"}
                for record in records
            )
        )

    @staticmethod
    def _has_independent_catalogue_support(candidate: CandidateEvidence) -> bool:
        """Return True when catalogue evidence proves a weak alias independently.

        A weak or inferred alias is never enough by itself. It stops being a hard
        block only when brand, all visible numbers, and both lexical methods agree.
        """
        return (
            candidate.brand_match
            and candidate.size_overlap >= 1.0
            and candidate.size_completeness >= 1.0
            and candidate.word_tfidf_score >= 0.65
            and candidate.char_tfidf_score >= 0.85
            and not candidate.attribute_conflict
            and not candidate.active_twin
            and not candidate.identifier_conflict
        )

    @staticmethod
    def _has_safe_unique_identifier(candidate: CandidateEvidence) -> bool:
        trusted_alias = (
            candidate.alias_exact
            and candidate.alias_confidence >= 0.99
            and candidate.alias_source in {"confirmed_order", "manual_import"}
        )
        return any(
            [candidate.item_code_exact, candidate.barcode_exact, candidate.part_number_exact, trusted_alias]
        )

    @staticmethod
    def _reason_for(candidate: CandidateEvidence) -> str:
        if candidate.barcode_exact:
            return "barcode_unique"
        if candidate.alias_exact:
            return "alias_current_unique"
        if candidate.item_code_exact:
            return "item_code_exact"
        if candidate.part_number_exact:
            return "part_number_unique"
        return "text_high_margin"

    @staticmethod
    def _result(
        line_id: str,
        item_code: str,
        confidence: float,
        decision: str,
        reason_code: str,
        candidates: list[CandidateEvidence],
        started: float,
        evidence: dict[str, object] | None = None,
    ) -> MatchResult:
        return MatchResult(
            line_id=line_id,
            item_code=item_code,
            confidence=confidence,
            decision=decision,
            reason_code=reason_code,
            candidates=candidates,
            latency_ms=(time.perf_counter() - started) * 1_000,
            evidence=evidence or {},
        )

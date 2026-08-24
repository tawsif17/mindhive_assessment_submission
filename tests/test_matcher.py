from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from matcher import Matcher, OrderLine
from matcher.data import MatcherData, read_csv
from matcher.text import contains_spreadsheet_error, normalise_text, normalise_uom
from matcher.types import AliasRecord, CatalogueItem


def make_item(
    tenant: str,
    item_code: str,
    name: str,
    *,
    barcode: str = "",
    part_number: str = "",
    disabled: bool = False,
    misc: bool = False,
) -> CatalogueItem:
    search_text = normalise_text(f"{name} {name} TestBrand All Items Hardware")
    return CatalogueItem(
        tenant=tenant,
        item_code=item_code,
        item_name=name,
        description=name,
        brand="" if misc else "TestBrand",
        item_group="All Items > Misc" if misc else "All Items > Hardware > Bolt",
        stock_uom="Pcs",
        barcode=barcode,
        manufacturer_part_no=part_number,
        disabled=disabled,
        list_price=10.0,
        is_misc=misc,
        search_text=search_text,
        name_text=normalise_text(name.replace(" (Bulk)", "")),
        uom_conversions={"piece": 1.0, "box": 10.0},
    )


def make_line(**changes: str) -> OrderLine:
    values = {
        "line_id": "LINE-1",
        "tenant": "acme",
        "customer_id": "CUST-1",
        "channel": "portal_csv",
        "order_date": "2026-06-01",
        "raw_text": "TestBrand hex bolt M8",
        "qty": "1",
        "uom_text": "pcs",
        "unit_price": "10",
        "buyer_sku": "",
        "raw_barcode": "",
        "notes": "",
    }
    values.update(changes)
    return OrderLine(**values)


class MatcherSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.acme_main = make_item("acme", "ACM-BOLT1", "TestBrand Hex Bolt M8", barcode="11111111")
        self.acme_duplicate_barcode = make_item(
            "acme", "ACM-BOLT2", "TestBrand Hex Bolt M10", barcode="22222222"
        )
        self.acme_duplicate_barcode_2 = make_item(
            "acme", "ACM-BOLT3", "TestBrand Hex Bolt M12", barcode="22222222"
        )
        self.disabled = make_item(
            "acme", "ACM-OLD", "TestBrand Old Bolt", disabled=True
        )
        self.misc = make_item("acme", "ACM-MISC", "Delivery Fee", misc=True)
        self.nordic = make_item("nordic", "NRD-FISH1", "TestBrand Frozen Fish")
        aliases = [
            AliasRecord("acme", "CUST-1", "SAFE", "ACM-BOLT1", "bolt", "2026-01-01", "", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-1", "EXPIRED", "ACM-BOLT1", "bolt", "2025-01-01", "2025-12-31", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-2", "OTHER", "ACM-BOLT1", "bolt", "2026-01-01", "", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-1", "DISABLED", "ACM-OLD", "old", "2026-01-01", "", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-1", "COLLIDE", "ACM-BOLT1", "bolt", "2026-01-01", "", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-1", "COLLIDE", "ACM-BOLT2", "bolt", "2026-01-01", "", "confirmed_order", 1.0),
            AliasRecord("acme", "CUST-1", "WEAK", "ACM-BOLT1", "bolt", "2026-01-01", "", "confirmed_order", 0.55),
            AliasRecord("acme", "CUST-1", "INFERRED", "ACM-BOLT1", "bolt", "2026-01-01", "", "inferred_match", 1.0),
        ]
        data = MatcherData(
            items_by_tenant={
                "acme": [
                    self.acme_main, self.acme_duplicate_barcode,
                    self.acme_duplicate_barcode_2, self.disabled, self.misc,
                ],
                "nordic": [self.nordic],
            },
            all_items_by_code={
                item.item_code: item
                for item in [
                    self.acme_main, self.acme_duplicate_barcode,
                    self.acme_duplicate_barcode_2, self.disabled, self.misc, self.nordic,
                ]
            },
            aliases=aliases,
        )
        self.matcher = Matcher(data)

    def test_tenant_filter_is_applied_before_retrieval(self) -> None:
        candidates, _ = self.matcher.retrieve(make_line(raw_text="Frozen Fish"))
        self.assertTrue(candidates)
        self.assertTrue(all(candidate.tenant == "acme" for candidate in candidates))
        self.assertNotIn("NRD-FISH1", [candidate.item_code for candidate in candidates])

    def test_disabled_and_misc_items_are_not_searchable(self) -> None:
        candidates, _ = self.matcher.retrieve(make_line(raw_text="Delivery Fee Old Bolt"))
        codes = [candidate.item_code for candidate in candidates]
        self.assertNotIn("ACM-OLD", codes)
        self.assertNotIn("ACM-MISC", codes)

    def test_unique_barcode_is_preserved_as_exact_evidence(self) -> None:
        candidates, _ = self.matcher.retrieve(
            make_line(raw_text="bolt", raw_barcode="11111111")
        )
        main = next(candidate for candidate in candidates if candidate.item_code == "ACM-BOLT1")
        self.assertTrue(main.barcode_exact)
        self.assertNotIn("identifier_ambiguous", main.safety_blocks)

    def test_duplicate_barcode_is_blocked(self) -> None:
        candidates, metadata = self.matcher.retrieve(
            make_line(raw_text="bolt", raw_barcode="22222222")
        )
        barcode_rows = [candidate for candidate in candidates if candidate.barcode_exact]
        self.assertEqual(2, len(barcode_rows))
        self.assertTrue(metadata["identifier_conflict"])
        self.assertTrue(all("identifier_ambiguous" in row.safety_blocks for row in barcode_rows))

    def test_alias_must_be_current_and_customer_specific(self) -> None:
        safe, _ = self.matcher.retrieve(make_line(buyer_sku="SAFE"))
        expired, _ = self.matcher.retrieve(make_line(buyer_sku="EXPIRED"))
        wrong_customer, _ = self.matcher.retrieve(make_line(buyer_sku="OTHER"))
        self.assertTrue(any(candidate.alias_exact for candidate in safe))
        self.assertFalse(any(candidate.alias_exact for candidate in expired))
        self.assertFalse(any(candidate.alias_exact for candidate in wrong_customer))

    def test_colliding_alias_is_blocked(self) -> None:
        candidates, _ = self.matcher.retrieve(make_line(buyer_sku="COLLIDE"))
        alias_rows = [candidate for candidate in candidates if candidate.alias_exact]
        self.assertEqual(2, len(alias_rows))
        self.assertTrue(all("identifier_ambiguous" in row.safety_blocks for row in alias_rows))

    def test_disabled_alias_target_is_negative_evidence(self) -> None:
        candidates, metadata = self.matcher.retrieve(make_line(buyer_sku="DISABLED"))
        self.assertEqual(["ACM-OLD"], metadata["disabled_alias_targets"])
        self.assertTrue(all("alias_disabled_target" in row.safety_blocks for row in candidates))

    def test_weak_alias_can_be_confirmed_by_complete_catalogue_evidence(self) -> None:
        candidates, _ = self.matcher.retrieve(
            make_line(raw_text="TestBrand Hex Bolt M8", buyer_sku="WEAK")
        )
        main = next(candidate for candidate in candidates if candidate.item_code == "ACM-BOLT1")
        self.assertNotIn("alias_not_trusted", main.safety_blocks)

    def test_inferred_alias_stays_blocked_when_size_is_missing(self) -> None:
        candidates, _ = self.matcher.retrieve(
            make_line(raw_text="TestBrand Hex Bolt", buyer_sku="INFERRED")
        )
        main = next(candidate for candidate in candidates if candidate.item_code == "ACM-BOLT1")
        self.assertIn("alias_not_trusted", main.safety_blocks)

    def test_cold_start_still_retrieves_catalogue_text(self) -> None:
        cold_data = MatcherData(
            self.matcher.data.items_by_tenant,
            self.matcher.data.all_items_by_code,
            [],
        )
        cold_matcher = Matcher(cold_data)
        candidates, _ = cold_matcher.retrieve(make_line(raw_text="TestBrand Hex Bolt M8"))
        self.assertEqual("ACM-BOLT1", candidates[0].item_code)

    def test_active_twin_is_blocked_with_and_without_pack_text(self) -> None:
        normal = make_item("acme", "ACM-TWIN1", "TestBrand Bolt")
        bulk = make_item("acme", "ACM-TWIN2", "TestBrand Bolt (Bulk)")
        data = MatcherData(
            {"acme": [normal, bulk]},
            {normal.item_code: normal, bulk.item_code: bulk},
            [],
        )
        matcher = Matcher(data)
        without_pack, _ = matcher.retrieve(make_line(raw_text="TestBrand Bolt"))
        with_pack, _ = matcher.retrieve(make_line(raw_text="TestBrand Bolt bulk box"))
        self.assertTrue(all("active_twin" in row.safety_blocks for row in without_pack))
        self.assertTrue(all("active_twin" in row.safety_blocks for row in with_pack))

    def test_same_input_returns_same_prediction_fields(self) -> None:
        first = self.matcher.match(make_line())
        second = self.matcher.match(make_line())
        self.assertEqual(first.to_prediction_row(), second.to_prediction_row())
        self.assertEqual(
            [candidate.to_dict() for candidate in first.candidates],
            [candidate.to_dict() for candidate in second.candidates],
        )

    def test_non_item_text_is_rejected(self) -> None:
        result = self.matcher.match(make_line(raw_text="same as last month order"))
        self.assertEqual("reject", result.decision)
        self.assertEqual("not_an_item", result.reason_code)
        self.assertEqual("", result.item_code)

    def test_output_schema_and_confidence_range(self) -> None:
        row = self.matcher.match(make_line()).to_prediction_row()
        self.assertEqual(
            ["line_id", "item_code", "confidence", "decision", "reason_code", "candidates"],
            list(row),
        )
        self.assertGreaterEqual(float(row["confidence"]), 0.0)
        self.assertLessEqual(float(row["confidence"]), 1.0)
        self.assertLessEqual(len([part for part in row["candidates"].split("|") if part]), 3)


class DataPreflightTests(unittest.TestCase):
    def test_common_piece_units_are_normalised(self) -> None:
        for value in ("ea", "each", "unit", "units", "pcs"):
            self.assertEqual("piece", normalise_uom(value))

    def test_spreadsheet_tokens_are_detected(self) -> None:
        for token in ("#NAME?", "#REF!", "#VALUE!"):
            self.assertTrue(contains_spreadsheet_error(f"bad {token} value"))

    def test_csv_reader_reports_spreadsheet_error_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sample.csv"
            path.write_text("id,name\n1,#NAME?\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row 2, column name"):
                read_csv(path, {"id", "name"})

    def test_csv_reader_reports_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sample.csv"
            path.write_text("id\n1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns: name"):
                read_csv(path, {"id", "name"})


class FullDataIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.matcher = Matcher.from_data_dir(cls.root / "data")
        with (cls.root / "data" / "order_lines_train.csv").open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_all_training_rows_run_and_stay_tenant_scoped(self) -> None:
        for row in self.rows:
            result = self.matcher.match(OrderLine.from_dict(row))
            if result.decision == "auto":
                expected_prefix = "ACM-" if row["tenant"] == "acme" else "NRD-"
                self.assertTrue(result.item_code.startswith(expected_prefix))
                item = self.matcher.data.all_items_by_code[result.item_code]
                self.assertFalse(item.disabled)
                self.assertFalse(item.is_misc)

    def test_measured_p95_is_within_budget(self) -> None:
        results = [self.matcher.match(OrderLine.from_dict(row)) for row in self.rows]
        latencies = sorted(result.latency_ms for result in results)
        p95_index = max(0, (95 * len(latencies) + 99) // 100 - 1)
        self.assertLessEqual(latencies[p95_index], 250.0)


if __name__ == "__main__":
    unittest.main()

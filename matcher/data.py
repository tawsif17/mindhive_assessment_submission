"""Read and validate the matching data without changing source files."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .text import contains_spreadsheet_error, normalise_text, normalise_uom
from .types import AliasRecord, CatalogueItem


CATALOGUE_COLUMNS = {
    "item_code", "item_name", "description", "brand", "item_group", "stock_uom",
    "uom_conversions", "barcode", "manufacturer_part_no", "disabled", "list_price",
}
ALIAS_COLUMNS = {
    "tenant", "customer_id", "customer_sku", "item_code", "customer_description",
    "valid_from", "valid_to", "source", "confidence",
}
ORDER_COLUMNS = {
    "line_id", "tenant", "customer_id", "channel", "order_date", "raw_text", "qty",
    "uom_text", "unit_price", "buyer_sku", "raw_barcode", "notes",
}
UOM_COLUMNS = {"tenant", "item_code", "uom", "conversion_factor", "is_stock_uom"}
EXPECTED_CODE_PREFIX = {"acme": "ACM-", "nordic": "NRD-"}
MISC_NAMES = {"DELIVERY FEE", "MISC CHARGE", "OPENING BALANCE", "SAMPLE - DO NOT SELL"}


def is_misc_row(row: dict[str, str]) -> bool:
    """Return True for catalogue rows that are not sellable products."""
    name = row.get("item_name", "").strip().upper()
    group = row.get("item_group", "").strip().lower()
    brand = row.get("brand", "").strip()
    return name in MISC_NAMES or not brand or group.endswith("> misc")


def read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    """Read one CSV after checking its columns and cell values."""
    if not path.is_file():
        raise FileNotFoundError(f"Required data file was not found: {path}")
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(required_columns - columns)
            if missing:
                raise ValueError(f"{path.name} is missing columns: {', '.join(missing)}")
            rows = list(reader)
    except UnicodeDecodeError as error:
        raise ValueError(f"{path.name} could not be read as UTF-8 CSV") from error

    for row_number, row in enumerate(rows, start=2):
        for column, value in row.items():
            if contains_spreadsheet_error(value or ""):
                raise ValueError(
                    f"Spreadsheet error token was found in {path.name}, "
                    f"row {row_number}, column {column}"
                )
    return rows


@dataclass
class MatcherData:
    """Validated catalogue, alias, and UOM data used by the matcher."""

    items_by_tenant: dict[str, list[CatalogueItem]]
    all_items_by_code: dict[str, CatalogueItem]
    aliases: list[AliasRecord]

    @property
    def tenants(self) -> set[str]:
        return set(self.items_by_tenant)


def load_matcher_data(data_dir: str | Path, include_aliases: bool = True) -> MatcherData:
    """Load catalogues and aliases, with tenant ownership checked."""
    root = Path(data_dir)
    catalogue_paths = sorted(root.glob("catalogue_*.csv"))
    if not catalogue_paths:
        raise FileNotFoundError(f"No catalogue CSV was found in {root}")

    items_by_tenant: dict[str, list[CatalogueItem]] = defaultdict(list)
    all_items_by_code: dict[str, CatalogueItem] = {}
    for path in catalogue_paths:
        tenant = path.stem.removeprefix("catalogue_").lower()
        expected_prefix = EXPECTED_CODE_PREFIX.get(tenant)
        if expected_prefix is None:
            raise ValueError(f"No item-code ownership rule exists for tenant: {tenant}")
        for row in read_csv(path, CATALOGUE_COLUMNS):
            item_code = row["item_code"].strip()
            if not item_code.startswith(expected_prefix):
                raise ValueError(
                    f"Catalogue item {item_code} does not belong to tenant {tenant}"
                )
            if item_code in all_items_by_code:
                raise ValueError(f"Duplicate catalogue item code was found: {item_code}")
            conversions: dict[str, float] = {}
            try:
                for conversion in json.loads(row.get("uom_conversions", "[]") or "[]"):
                    conversions[normalise_uom(str(conversion["uom"]))] = float(
                        conversion["conversion_factor"]
                    )
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid UOM data was found for {item_code}") from error
            price_text = row.get("list_price", "").strip()
            item = CatalogueItem(
                tenant=tenant,
                item_code=item_code,
                item_name=row["item_name"].strip(),
                description=row["description"].strip(),
                brand=row["brand"].strip(),
                item_group=row["item_group"].strip(),
                stock_uom=row["stock_uom"].strip(),
                barcode=row["barcode"].strip(),
                manufacturer_part_no=row["manufacturer_part_no"].strip(),
                disabled=row["disabled"].strip() == "1",
                list_price=float(price_text) if price_text else None,
                is_misc=is_misc_row(row),
                search_text=normalise_text(
                    " ".join(
                        [row["item_name"], row["description"], row["brand"], row["item_group"]]
                    )
                ),
                name_text=normalise_text(row["item_name"].replace(" (Bulk)", "")),
                uom_conversions=conversions,
            )
            items_by_tenant[tenant].append(item)
            all_items_by_code[item_code] = item

    # The separate UOM file is treated as a required reference. A mismatch is
    # stopped at load time instead of becoming uncertain matching evidence.
    uom_rows = read_csv(root / "uom_reference.csv", UOM_COLUMNS)
    uom_by_item: dict[str, dict[str, float]] = defaultdict(dict)
    stock_uom_counts: dict[str, int] = defaultdict(int)
    for row in uom_rows:
        item_code = row["item_code"].strip()
        item = all_items_by_code.get(item_code)
        tenant = row["tenant"].strip().lower()
        if item is None:
            raise ValueError(f"UOM target was not found: {item_code}")
        if item.tenant != tenant:
            raise ValueError(
                f"UOM target {item_code} belongs to {item.tenant}, not {tenant}"
            )
        try:
            factor = float(row["conversion_factor"])
        except ValueError as error:
            raise ValueError(f"Invalid UOM conversion was found for {item_code}") from error
        if factor <= 0:
            raise ValueError(f"UOM conversion must be positive for {item_code}")
        uom_by_item[item_code][normalise_uom(row["uom"])] = factor
        if row["is_stock_uom"].strip() == "1":
            stock_uom_counts[item_code] += 1
    for item_code, item in all_items_by_code.items():
        if item_code not in uom_by_item:
            raise ValueError(f"No UOM reference row was found for {item_code}")
        if stock_uom_counts[item_code] != 1:
            raise ValueError(f"Exactly one stock UOM row is required for {item_code}")
        if uom_by_item[item_code] != item.uom_conversions:
            raise ValueError(f"Catalogue and UOM reference values differ for {item_code}")

    aliases: list[AliasRecord] = []
    alias_path = root / "customer_sku_map.csv"
    if include_aliases:
        for row in read_csv(alias_path, ALIAS_COLUMNS):
            tenant = row["tenant"].strip().lower()
            target = all_items_by_code.get(row["item_code"].strip())
            if tenant not in items_by_tenant:
                raise ValueError(f"Unknown alias tenant was found: {tenant}")
            if target is None:
                raise ValueError(f"Alias target was not found: {row['item_code']}")
            if target.tenant != tenant:
                raise ValueError(
                    f"Alias target {target.item_code} belongs to {target.tenant}, not {tenant}"
                )
            aliases.append(
                AliasRecord(
                    tenant=tenant,
                    customer_id=row["customer_id"].strip(),
                    customer_sku=row["customer_sku"].strip(),
                    item_code=target.item_code,
                    customer_description=row["customer_description"].strip(),
                    valid_from=row["valid_from"].strip(),
                    valid_to=row["valid_to"].strip(),
                    source=row["source"].strip(),
                    confidence=float(row["confidence"]),
                )
            )

    return MatcherData(dict(items_by_tenant), all_items_by_code, aliases)


def load_order_rows(path: str | Path, require_label: bool = False) -> list[dict[str, str]]:
    """Load order rows for evaluation or prediction generation."""
    required = set(ORDER_COLUMNS)
    if require_label:
        required.add("gt_item_code")
    rows = read_csv(Path(path), required)
    line_ids: set[str] = set()
    for row in rows:
        tenant = row["tenant"].strip().lower()
        if not tenant:
            raise ValueError(f"Line {row['line_id']} has no tenant")
        line_id = row["line_id"].strip()
        if line_id in line_ids:
            raise ValueError(f"Duplicate line_id was found: {line_id}")
        line_ids.add(line_id)
    return rows

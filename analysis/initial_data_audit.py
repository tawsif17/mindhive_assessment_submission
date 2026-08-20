#!/usr/bin/env python3
"""Print a read-only audit of the supplied matching data.

Only Python standard-library modules are used. The source files are opened for
reading.

Run from the repository root:

    python analysis/initial_data_audit.py
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPOSITORY_ROOT / "data"

CATALOGUE_FILES = {
    "acme": "catalogue_acme.csv",
    "nordic": "catalogue_nordic.csv",
}

EXPECTED_COLUMNS = {
    "catalogue_acme.csv": [
        "item_code",
        "item_name",
        "description",
        "brand",
        "item_group",
        "stock_uom",
        "uom_conversions",
        "barcode",
        "manufacturer_part_no",
        "disabled",
        "available_qty",
        "list_price",
    ],
    "catalogue_nordic.csv": [
        "item_code",
        "item_name",
        "description",
        "brand",
        "item_group",
        "stock_uom",
        "uom_conversions",
        "barcode",
        "manufacturer_part_no",
        "disabled",
        "available_qty",
        "list_price",
    ],
    "customer_sku_map.csv": [
        "tenant",
        "customer_id",
        "customer_sku",
        "item_code",
        "customer_description",
        "valid_from",
        "valid_to",
        "source",
        "confidence",
    ],
    "order_lines_train.csv": [
        "line_id",
        "tenant",
        "customer_id",
        "channel",
        "order_date",
        "raw_text",
        "qty",
        "uom_text",
        "unit_price",
        "buyer_sku",
        "raw_barcode",
        "notes",
        "gt_item_code",
    ],
    "order_lines_holdout.csv": [
        "line_id",
        "tenant",
        "customer_id",
        "channel",
        "order_date",
        "raw_text",
        "qty",
        "uom_text",
        "unit_price",
        "buyer_sku",
        "raw_barcode",
        "notes",
    ],
    "uom_reference.csv": [
        "tenant",
        "item_code",
        "uom",
        "conversion_factor",
        "is_stock_uom",
    ],
}

EXPECTED_CODE_PREFIX = {
    "acme": "ACM-",
    "nordic": "NRD-",
}

MISC_NAMES = {
    "DELIVERY FEE",
    "MISC CHARGE",
    "OPENING BALANCE",
    "SAMPLE - DO NOT SELL",
}

LEADING_ORDER_WORDS = [
    "please send ",
    "pls send ",
    "urgent ",
    "need ",
    "item ",
    "1 ",
]

EXAMPLE_LIMIT = 5


def read_csv_file(file_name: str) -> tuple[list[dict[str, str]], list[str]]:
    """Read one CSV file and return its rows and column names."""
    path = DATA_DIR / file_name
    with path.open("r", newline="", encoding="utf-8-sig") as file_handle:
        reader = csv.DictReader(file_handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    return rows, columns


def print_section(title: str) -> None:
    """Print a clear section heading."""
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def format_rate(count: int, total: int) -> str:
    """Return a count and its share as a short string."""
    if total == 0:
        return f"{count} (0.0%)"
    rate = count / total * 100
    return f"{count} ({rate:.1f}%)"


def normalise_text(value: str) -> str:
    """Make text easier to compare without changing the source value."""
    ascii_text = unicodedata.normalize("NFKD", value)
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    return " ".join(words)


def normalise_order_text(value: str) -> str:
    """Normalise an order line and remove one simple order prefix."""
    text = normalise_text(value)
    for prefix in LEADING_ORDER_WORDS:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def is_misc_catalogue_row(row: dict[str, str]) -> bool:
    """Return True when a catalogue row does not look like a sellable item."""
    item_name = row.get("item_name", "").strip().upper()
    item_group = row.get("item_group", "").strip().lower()
    brand = row.get("brand", "").strip()

    if item_name in MISC_NAMES:
        return True
    if not brand:
        return True
    if item_group.endswith("> misc"):
        return True
    return False


def is_disabled(row: dict[str, str]) -> bool:
    """Return True when the disabled flag is set."""
    return row.get("disabled", "").strip() == "1"


def group_values(
    rows: list[dict[str, str]], field_name: str
) -> dict[str, list[dict[str, str]]]:
    """Group non-blank rows by one field."""
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        value = row.get(field_name, "").strip()
        if value:
            groups[value].append(row)
    return groups


def duplicate_groups(
    rows: list[dict[str, str]], field_name: str
) -> dict[str, list[dict[str, str]]]:
    """Return field values that are used by more than one row."""
    groups = group_values(rows, field_name)
    duplicates: dict[str, list[dict[str, str]]] = {}
    for value, grouped_rows in groups.items():
        if len(grouped_rows) > 1:
            duplicates[value] = grouped_rows
    return duplicates


def count_active_duplicate_groups(
    groups: dict[str, list[dict[str, str]]]
) -> int:
    """Count duplicate groups that contain two or more active rows."""
    count = 0
    for grouped_rows in groups.values():
        active_count = 0
        for row in grouped_rows:
            if not is_disabled(row):
                active_count += 1
        if active_count > 1:
            count += 1
    return count


def print_group_examples(
    groups: dict[object, object], label: str, limit: int = EXAMPLE_LIMIT
) -> None:
    """Print a small and stable list of grouped examples."""
    if not groups:
        return
    print(f"  Examples of {label} were:")
    keys = sorted(groups, key=lambda value: str(value))
    for key in keys[:limit]:
        value = groups[key]
        print(f"    - {key}: {value}")


def load_all_data() -> dict[str, object]:
    """Load each public data file once."""
    loaded: dict[str, object] = {}
    for file_name in EXPECTED_COLUMNS:
        rows, columns = read_csv_file(file_name)
        loaded[file_name] = rows
        loaded[f"{file_name}:columns"] = columns

    report_path = DATA_DIR / "report_reference.json.gz"
    with gzip.open(report_path, "rt", encoding="utf-8") as file_handle:
        loaded["report_reference.json.gz"] = json.load(file_handle)
    return loaded


def audit_files(data: dict[str, object]) -> None:
    """Print row counts and schema checks."""
    print_section("1. DATA FILES")
    for file_name, expected_columns in EXPECTED_COLUMNS.items():
        rows = data[file_name]
        columns = data[f"{file_name}:columns"]
        assert isinstance(rows, list)
        assert isinstance(columns, list)

        missing_columns = []
        for column in expected_columns:
            if column not in columns:
                missing_columns.append(column)

        print(f"{file_name}")
        print(f"  Rows found: {len(rows)}")
        print(f"  Columns found: {', '.join(columns)}")
        if missing_columns:
            print(f"  Missing columns were found: {', '.join(missing_columns)}")
        else:
            print("  All required columns were found.")


def build_catalogue_indexes(
    catalogues: dict[str, list[dict[str, str]]]
) -> tuple[dict[str, str], dict[tuple[str, str], dict[str, str]]]:
    """Build simple lookups for catalogue ownership and row details."""
    owner_by_code: dict[str, str] = {}
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]] = {}

    for tenant, rows in catalogues.items():
        for row in rows:
            item_code = row["item_code"].strip()
            if item_code not in owner_by_code:
                owner_by_code[item_code] = tenant
            row_by_tenant_and_code[(tenant, item_code)] = row

    return owner_by_code, row_by_tenant_and_code


def find_active_twins(
    rows: list[dict[str, str]],
) -> dict[str, list[str]]:
    """Find active items that share a visible base name."""
    grouped_codes: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if is_disabled(row) or is_misc_catalogue_row(row):
            continue
        base_name = row["item_name"].replace(" (Bulk)", "")
        base_name = normalise_text(base_name)
        grouped_codes[base_name].append(row["item_code"])

    twins: dict[str, list[str]] = {}
    for base_name, item_codes in grouped_codes.items():
        if len(item_codes) > 1:
            twins[base_name] = sorted(item_codes)
    return twins


def find_duplicate_normalised_names(
    rows: list[dict[str, str]],
) -> dict[str, list[str]]:
    """Find exact visible names that are used by more than one row."""
    grouped_codes: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        name = normalise_text(row["item_name"])
        grouped_codes[name].append(row["item_code"])

    duplicates: dict[str, list[str]] = {}
    for name, item_codes in grouped_codes.items():
        if len(item_codes) > 1:
            duplicates[name] = sorted(item_codes)
    return duplicates


def audit_catalogues(
    catalogues: dict[str, list[dict[str, str]]]
) -> dict[str, dict[str, object]]:
    """Print catalogue counts and identifier risks."""
    print_section("2. CATALOGUES")
    results: dict[str, dict[str, object]] = {}

    for tenant, rows in catalogues.items():
        active_rows = []
        disabled_rows = []
        misc_rows = []
        wrong_prefix_rows = []

        for row in rows:
            if is_disabled(row):
                disabled_rows.append(row)
            else:
                active_rows.append(row)
            if is_misc_catalogue_row(row):
                misc_rows.append(row)
            if not row["item_code"].startswith(EXPECTED_CODE_PREFIX[tenant]):
                wrong_prefix_rows.append(row)

        twins = find_active_twins(rows)
        duplicate_codes = duplicate_groups(rows, "item_code")
        duplicate_barcodes = duplicate_groups(rows, "barcode")
        duplicate_part_numbers = duplicate_groups(rows, "manufacturer_part_no")
        duplicate_names = find_duplicate_normalised_names(rows)
        active_duplicate_barcodes = count_active_duplicate_groups(duplicate_barcodes)
        active_duplicate_part_numbers = count_active_duplicate_groups(
            duplicate_part_numbers
        )

        print(f"Tenant: {tenant}")
        print(f"  Catalogue rows found: {len(rows)}")
        print(f"  Active rows found: {format_rate(len(active_rows), len(rows))}")
        print(f"  Disabled rows found: {format_rate(len(disabled_rows), len(rows))}")
        print(f"  Misc rows found: {format_rate(len(misc_rows), len(rows))}")
        print(f"  Active twin groups found: {len(twins)}")
        print(f"  Duplicate item-code groups found: {len(duplicate_codes)}")
        print(f"  Duplicate barcode groups found: {len(duplicate_barcodes)}")
        print(
            "  Duplicate barcode groups with two active rows: "
            f"{active_duplicate_barcodes}"
        )
        print(
            "  Duplicate manufacturer-part-number groups found: "
            f"{len(duplicate_part_numbers)}"
        )
        print(
            "  Duplicate part-number groups with two active rows: "
            f"{active_duplicate_part_numbers}"
        )
        print(f"  Duplicate normalized-name groups found: {len(duplicate_names)}")
        print(f"  Wrong item-code prefixes found: {len(wrong_prefix_rows)}")

        misc_examples: dict[str, str] = {}
        for row in misc_rows[:EXAMPLE_LIMIT]:
            misc_examples[row["item_code"]] = row["item_name"]
        print_group_examples(misc_examples, "misc rows")
        print_group_examples(twins, "active twin groups")

        barcode_examples: dict[str, list[str]] = {}
        for value, grouped_rows in duplicate_barcodes.items():
            barcode_examples[value] = sorted(row["item_code"] for row in grouped_rows)
        print_group_examples(barcode_examples, "duplicate barcodes")

        part_number_examples: dict[str, list[str]] = {}
        for value, grouped_rows in duplicate_part_numbers.items():
            part_number_examples[value] = sorted(
                row["item_code"] for row in grouped_rows
            )
        print_group_examples(part_number_examples, "duplicate manufacturer part numbers")

        results[tenant] = {
            "total": len(rows),
            "active": len(active_rows),
            "disabled": len(disabled_rows),
            "misc": len(misc_rows),
            "twins": twins,
            "duplicate_codes": duplicate_codes,
            "duplicate_barcodes": duplicate_barcodes,
            "active_duplicate_barcodes": active_duplicate_barcodes,
            "duplicate_part_numbers": duplicate_part_numbers,
            "active_duplicate_part_numbers": active_duplicate_part_numbers,
            "duplicate_names": duplicate_names,
            "wrong_prefix": wrong_prefix_rows,
        }

    return results


def find_dataset_end_date(
    training_rows: list[dict[str, str]], holdout_rows: list[dict[str, str]]
) -> str:
    """Return the latest order date found in the supplied order lines."""
    dates = []
    for row in training_rows + holdout_rows:
        order_date = row.get("order_date", "").strip()
        if order_date:
            dates.append(order_date)
    return max(dates) if dates else ""


def alias_is_valid_on_date(alias: dict[str, str], order_date: str) -> bool:
    """Check the date range on one alias row."""
    valid_from = alias.get("valid_from", "").strip()
    valid_to = alias.get("valid_to", "").strip()

    if valid_from and order_date < valid_from:
        return False
    if valid_to and order_date > valid_to:
        return False
    return True


def audit_aliases(
    aliases: list[dict[str, str]],
    audit_date: str,
    owner_by_code: dict[str, str],
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    """Print alias counts and unsafe target checks."""
    print_section("3. CUSTOMER ALIASES")

    tenant_counts = Counter()
    source_counts = Counter()
    confidence_counts = Counter()
    expired_rows = []
    missing_targets = []
    cross_tenant_targets = []
    disabled_targets = []
    current_disabled_targets = []
    misc_targets = []
    collision_codes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    current_collision_codes: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for alias in aliases:
        tenant = alias["tenant"].strip()
        item_code = alias["item_code"].strip()
        tenant_counts[tenant] += 1
        source_counts[alias["source"].strip()] += 1
        confidence_counts[alias["confidence"].strip()] += 1

        valid_to = alias["valid_to"].strip()
        if valid_to and valid_to < audit_date:
            expired_rows.append(alias)

        collision_key = (
            tenant,
            alias["customer_id"].strip(),
            alias["customer_sku"].strip(),
        )
        collision_codes[collision_key].add(item_code)
        if alias_is_valid_on_date(alias, audit_date):
            current_collision_codes[collision_key].add(item_code)

        owner = owner_by_code.get(item_code)
        if owner is None:
            missing_targets.append(alias)
            continue
        if owner != tenant:
            cross_tenant_targets.append(alias)
            continue

        target_row = row_by_tenant_and_code.get((tenant, item_code))
        if target_row is None:
            missing_targets.append(alias)
            continue
        if is_disabled(target_row):
            disabled_targets.append(alias)
            if alias_is_valid_on_date(alias, audit_date):
                current_disabled_targets.append(alias)
        if is_misc_catalogue_row(target_row):
            misc_targets.append(alias)

    collisions: dict[tuple[str, str, str], list[str]] = {}
    for key, item_codes in collision_codes.items():
        if len(item_codes) > 1:
            collisions[key] = sorted(item_codes)

    current_collisions: dict[tuple[str, str, str], list[str]] = {}
    for key, item_codes in current_collision_codes.items():
        if len(item_codes) > 1:
            current_collisions[key] = sorted(item_codes)

    print(f"Alias rows found: {len(aliases)}")
    print(f"The audit date was set to: {audit_date}")
    print(f"Expired aliases found: {format_rate(len(expired_rows), len(aliases))}")
    print(f"Stored alias collision groups found: {len(collisions)}")
    print(f"Current alias collision groups found: {len(current_collisions)}")
    print(f"Aliases linked to missing items: {len(missing_targets)}")
    print(f"Aliases linked to another tenant: {len(cross_tenant_targets)}")
    print(f"Aliases linked to disabled items: {len(disabled_targets)}")
    print(
        "Current aliases linked to disabled items: "
        f"{len(current_disabled_targets)}"
    )
    print(f"Aliases linked to misc rows: {len(misc_targets)}")
    print(f"Aliases by tenant: {dict(sorted(tenant_counts.items()))}")
    print(f"Aliases by source: {dict(sorted(source_counts.items()))}")
    print(f"Aliases by confidence: {dict(sorted(confidence_counts.items()))}")
    print_group_examples(collisions, "alias collisions")

    disabled_examples: dict[str, str] = {}
    for alias in disabled_targets[:EXAMPLE_LIMIT]:
        key = f"{alias['tenant']}/{alias['customer_id']}/{alias['customer_sku']}"
        disabled_examples[key] = alias["item_code"]
    print_group_examples(disabled_examples, "aliases linked to disabled items")

    return {
        "tenant_counts": tenant_counts,
        "source_counts": source_counts,
        "confidence_counts": confidence_counts,
        "expired": expired_rows,
        "collisions": collisions,
        "current_collisions": current_collisions,
        "missing_targets": missing_targets,
        "cross_tenant_targets": cross_tenant_targets,
        "disabled_targets": disabled_targets,
        "current_disabled_targets": current_disabled_targets,
        "misc_targets": misc_targets,
    }


def parse_float(value: str) -> float | None:
    """Parse one number. None is returned when the value is not valid."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def embedded_uom_values(row: dict[str, str]) -> set[tuple[str, float]] | None:
    """Read the UOM JSON stored in one catalogue row."""
    try:
        values = json.loads(row["uom_conversions"])
    except (json.JSONDecodeError, TypeError):
        return None

    result: set[tuple[str, float]] = set()
    for value in values:
        factor = parse_float(str(value.get("conversion_factor", "")))
        uom = str(value.get("uom", "")).strip()
        if factor is None or not uom:
            return None
        result.add((uom, factor))
    return result


def audit_uom(
    uom_rows: list[dict[str, str]],
    catalogues: dict[str, list[dict[str, str]]],
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    """Print UOM coverage and consistency checks."""
    print_section("4. UOM DATA")

    grouped_uom_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    invalid_factors = []
    unknown_targets = []
    stock_uom_counts = Counter()
    conversion_count_distribution = Counter()

    for uom_row in uom_rows:
        key = (uom_row["tenant"].strip(), uom_row["item_code"].strip())
        grouped_uom_rows[key].append(uom_row)

        factor = parse_float(uom_row["conversion_factor"])
        if factor is None or factor <= 0:
            invalid_factors.append(uom_row)
        if key not in row_by_tenant_and_code:
            unknown_targets.append(uom_row)
        if uom_row["is_stock_uom"].strip() == "1":
            stock_uom_counts[uom_row["uom"].strip()] += 1

    for matching_rows in grouped_uom_rows.values():
        conversion_count_distribution[len(matching_rows)] += 1

    missing_stock_rows = []
    multiple_stock_rows = []
    catalogue_uom_mismatches = []
    embedded_uom_mismatches = []
    invalid_embedded_uom = []
    coverage_results: dict[str, dict[str, int]] = {}

    for tenant, catalogue_rows in catalogues.items():
        covered = 0
        active_total = 0
        active_covered = 0
        disabled_total = 0
        disabled_covered = 0

        for catalogue_row in catalogue_rows:
            item_code = catalogue_row["item_code"].strip()
            key = (tenant, item_code)
            matching_uom_rows = grouped_uom_rows.get(key, [])

            if matching_uom_rows:
                covered += 1

            if is_disabled(catalogue_row):
                disabled_total += 1
                if matching_uom_rows:
                    disabled_covered += 1
            else:
                active_total += 1
                if matching_uom_rows:
                    active_covered += 1

            stock_rows = []
            for uom_row in matching_uom_rows:
                if uom_row["is_stock_uom"].strip() == "1":
                    stock_rows.append(uom_row)

            if len(stock_rows) == 0:
                missing_stock_rows.append(key)
            if len(stock_rows) > 1:
                multiple_stock_rows.append(key)
            if len(stock_rows) == 1:
                if stock_rows[0]["uom"].strip() != catalogue_row["stock_uom"].strip():
                    catalogue_uom_mismatches.append(key)

            embedded_values = embedded_uom_values(catalogue_row)
            if embedded_values is None:
                invalid_embedded_uom.append(key)
            else:
                reference_values: set[tuple[str, float]] = set()
                for uom_row in matching_uom_rows:
                    factor = parse_float(uom_row["conversion_factor"])
                    if factor is not None:
                        reference_values.add((uom_row["uom"].strip(), factor))
                if embedded_values != reference_values:
                    embedded_uom_mismatches.append(key)

        coverage_results[tenant] = {
            "total": len(catalogue_rows),
            "covered": covered,
            "active_total": active_total,
            "active_covered": active_covered,
            "disabled_total": disabled_total,
            "disabled_covered": disabled_covered,
        }

        print(f"Tenant: {tenant}")
        print(
            "  Catalogue rows with UOM data: "
            f"{format_rate(covered, len(catalogue_rows))}"
        )
        print(
            "  Active rows with UOM data: "
            f"{format_rate(active_covered, active_total)}"
        )
        print(
            "  Disabled rows with UOM data: "
            f"{format_rate(disabled_covered, disabled_total)}"
        )

    print(f"UOM rows found: {len(uom_rows)}")
    print(f"Items with no stock-UOM row: {len(missing_stock_rows)}")
    print(f"Items with more than one stock-UOM row: {len(multiple_stock_rows)}")
    print(f"Invalid conversion values found: {len(invalid_factors)}")
    print(f"UOM rows linked to missing items: {len(unknown_targets)}")
    print(f"Catalogue stock-UOM mismatches found: {len(catalogue_uom_mismatches)}")
    print(f"Invalid embedded UOM values found: {len(invalid_embedded_uom)}")
    print(f"Embedded and reference UOM mismatches found: {len(embedded_uom_mismatches)}")
    print(
        "Conversion-row counts per item: "
        f"{dict(sorted(conversion_count_distribution.items()))}"
    )
    print(f"Stock UOM counts: {dict(sorted(stock_uom_counts.items()))}")

    return {
        "coverage": coverage_results,
        "missing_stock": missing_stock_rows,
        "multiple_stock": multiple_stock_rows,
        "invalid_factors": invalid_factors,
        "unknown_targets": unknown_targets,
        "catalogue_mismatches": catalogue_uom_mismatches,
        "embedded_mismatches": embedded_uom_mismatches,
        "invalid_embedded": invalid_embedded_uom,
        "conversion_count_distribution": conversion_count_distribution,
    }


def signal_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    """Count the order lines that contain each useful signal."""
    fields = ["buyer_sku", "raw_barcode", "uom_text", "unit_price", "notes"]
    counts: dict[str, int] = {}
    for field_name in fields:
        count = 0
        for row in rows:
            if row.get(field_name, "").strip():
                count += 1
        counts[field_name] = count
    return counts


def audit_training_rows(
    training_rows: list[dict[str, str]],
    owner_by_code: dict[str, str],
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    """Print label rates, order-line counts, and label integrity checks."""
    print_section("5. TRAINING ORDER LINES")

    tenant_counts = Counter()
    channel_counts = Counter()
    blank_by_tenant = Counter()
    labelled_rows = []
    blank_rows = []
    missing_label_targets = []
    wrong_tenant_labels = []
    disabled_label_targets = []
    misc_label_targets = []

    for row in training_rows:
        tenant = row["tenant"].strip()
        item_code = row["gt_item_code"].strip()
        tenant_counts[tenant] += 1
        channel_counts[row["channel"].strip()] += 1

        if not item_code:
            blank_rows.append(row)
            blank_by_tenant[tenant] += 1
            continue

        labelled_rows.append(row)
        owner = owner_by_code.get(item_code)
        if owner is None:
            missing_label_targets.append(row)
            continue
        if owner != tenant:
            wrong_tenant_labels.append(row)
            continue

        target_row = row_by_tenant_and_code.get((tenant, item_code))
        if target_row is None:
            missing_label_targets.append(row)
            continue
        if is_disabled(target_row):
            disabled_label_targets.append(row)
        if is_misc_catalogue_row(target_row):
            misc_label_targets.append(row)

    print(f"Training rows found: {len(training_rows)}")
    print(f"Rows with a label: {format_rate(len(labelled_rows), len(training_rows))}")
    print(f"Rows with a blank label: {format_rate(len(blank_rows), len(training_rows))}")
    print(f"Rows by tenant: {dict(sorted(tenant_counts.items()))}")
    print(f"Rows by channel: {dict(sorted(channel_counts.items()))}")

    for tenant in sorted(tenant_counts):
        print(
            f"  Blank labels for {tenant}: "
            f"{format_rate(blank_by_tenant[tenant], tenant_counts[tenant])}"
        )

    signals = signal_counts(training_rows)
    for field_name, count in signals.items():
        print(f"Rows with {field_name}: {format_rate(count, len(training_rows))}")

    print(f"Labels linked to missing items: {len(missing_label_targets)}")
    print(f"Labels linked to another tenant: {len(wrong_tenant_labels)}")
    print(f"Labels linked to disabled items: {len(disabled_label_targets)}")
    print(f"Labels linked to misc rows: {len(misc_label_targets)}")

    return {
        "tenant_counts": tenant_counts,
        "channel_counts": channel_counts,
        "signals": signals,
        "labelled": labelled_rows,
        "blank": blank_rows,
        "blank_by_tenant": blank_by_tenant,
        "missing_targets": missing_label_targets,
        "wrong_tenant": wrong_tenant_labels,
        "disabled_targets": disabled_label_targets,
        "misc_targets": misc_label_targets,
    }


def median_number(values: list[int]) -> float:
    """Return a median. Zero is returned for an empty list."""
    if not values:
        return 0.0
    return float(statistics.median(values))


def observable_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    """Build a summary that can be compared without labels."""
    tenant_counts = Counter()
    channel_counts = Counter()
    text_lengths = []
    token_counts = []
    quantity_count = 0
    order_dates = []

    for row in rows:
        tenant_counts[row["tenant"].strip()] += 1
        channel_counts[row["channel"].strip()] += 1
        raw_text = row["raw_text"]
        text_lengths.append(len(raw_text))
        token_counts.append(len(normalise_text(raw_text).split()))
        if row["qty"].strip():
            quantity_count += 1
        if row["order_date"].strip():
            order_dates.append(row["order_date"].strip())

    return {
        "total": len(rows),
        "tenants": tenant_counts,
        "channels": channel_counts,
        "signals": signal_counts(rows),
        "mean_text_length": statistics.mean(text_lengths) if text_lengths else 0.0,
        "median_text_length": median_number(text_lengths),
        "mean_token_count": statistics.mean(token_counts) if token_counts else 0.0,
        "median_token_count": median_number(token_counts),
        "quantity_count": quantity_count,
        "first_date": min(order_dates) if order_dates else "",
        "last_date": max(order_dates) if order_dates else "",
    }


def category_shares(counts: Counter, total: int) -> dict[str, float]:
    """Convert category counts to percentage shares."""
    shares: dict[str, float] = {}
    for key, count in counts.items():
        share = count / total * 100 if total else 0.0
        shares[key] = round(share, 1)
    return shares


def print_distribution(name: str, summary: dict[str, object]) -> None:
    """Print one train or holdout summary."""
    total = int(summary["total"])
    print(name)
    print(f"  Rows found: {total}")
    print(
        "  Tenant shares: "
        f"{dict(sorted(category_shares(summary['tenants'], total).items()))}"
    )
    print(
        "  Channel shares: "
        f"{dict(sorted(category_shares(summary['channels'], total).items()))}"
    )

    signals = summary["signals"]
    for field_name, count in signals.items():
        print(f"  Rows with {field_name}: {format_rate(count, total)}")

    print(f"  Mean text length: {summary['mean_text_length']:.1f} characters")
    print(f"  Median text length: {summary['median_text_length']:.1f} characters")
    print(f"  Mean token count: {summary['mean_token_count']:.1f}")
    print(f"  Median token count: {summary['median_token_count']:.1f}")
    print(
        "  Rows with quantity: "
        f"{format_rate(int(summary['quantity_count']), total)}"
    )
    print(f"  Date range: {summary['first_date']} to {summary['last_date']}")


def percentage_point_changes(
    train_summary: dict[str, object], holdout_summary: dict[str, object]
) -> list[str]:
    """Return visible rate changes of at least five percentage points."""
    changes = []
    train_total = int(train_summary["total"])
    holdout_total = int(holdout_summary["total"])

    areas = [
        ("tenant", train_summary["tenants"], holdout_summary["tenants"]),
        ("channel", train_summary["channels"], holdout_summary["channels"]),
        ("signal", train_summary["signals"], holdout_summary["signals"]),
    ]

    for area_name, train_counts, holdout_counts in areas:
        all_keys = sorted(set(train_counts) | set(holdout_counts))
        for key in all_keys:
            train_rate = train_counts.get(key, 0) / train_total * 100
            holdout_rate = holdout_counts.get(key, 0) / holdout_total * 100
            change = holdout_rate - train_rate
            if abs(change) >= 5.0:
                changes.append(
                    f"{area_name} {key}: {train_rate:.1f}% to "
                    f"{holdout_rate:.1f}% ({change:+.1f} points)"
                )
    return changes


def audit_train_holdout_distribution(
    training_rows: list[dict[str, str]], holdout_rows: list[dict[str, str]]
) -> tuple[dict[str, object], dict[str, object]]:
    """Print a label-free comparison of training and holdout data."""
    print_section("6. TRAINING AND HOLDOUT COMPARISON")
    train_summary = observable_summary(training_rows)
    holdout_summary = observable_summary(holdout_rows)

    print_distribution("Training data", train_summary)
    print_distribution("Holdout data", holdout_summary)

    changes = percentage_point_changes(train_summary, holdout_summary)
    if changes:
        print("Visible changes of at least five percentage points were found:")
        for change in changes:
            print(f"  - {change}")
    else:
        print("No visible rate change of at least five percentage points was found.")

    print("No holdout label was read or inferred.")
    return train_summary, holdout_summary


def build_match_indexes(
    catalogues: dict[str, list[dict[str, str]]]
) -> dict[str, dict[tuple[str, str], set[str]]]:
    """Build active, non-misc indexes for simple matching checks."""
    barcode_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    name_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    base_name_index: dict[tuple[str, str], set[str]] = defaultdict(set)

    for tenant, rows in catalogues.items():
        for row in rows:
            if is_disabled(row) or is_misc_catalogue_row(row):
                continue

            item_code = row["item_code"].strip()
            barcode = row["barcode"].strip()
            if barcode:
                barcode_index[(tenant, barcode)].add(item_code)

            item_name = normalise_text(row["item_name"])
            name_index[(tenant, item_name)].add(item_code)

            base_name = row["item_name"].replace(" (Bulk)", "")
            base_name = normalise_text(base_name)
            base_name_index[(tenant, base_name)].add(item_code)

    return {
        "barcode": barcode_index,
        "name": name_index,
        "base_name": base_name_index,
    }


def one_item_code(item_codes: set[str]) -> str | None:
    """Return one item code only when the set contains one value."""
    if len(item_codes) != 1:
        return None
    return next(iter(item_codes))


def measure_predictions(
    lane_name: str,
    predictions: dict[str, str],
    training_by_id: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Measure one simple matching lane against training labels."""
    correct = 0
    false_matches = []

    for line_id, predicted_code in predictions.items():
        row = training_by_id[line_id]
        if row["gt_item_code"].strip() == predicted_code:
            correct += 1
        else:
            false_matches.append((line_id, predicted_code, row["gt_item_code"].strip()))

    match_count = len(predictions)
    total = len(training_by_id)
    precision = correct / match_count if match_count else 0.0
    coverage = match_count / total if total else 0.0

    print(lane_name)
    print(f"  Matches made: {match_count}")
    print(f"  Correct matches: {correct}")
    print(f"  False matches: {len(false_matches)}")
    print(f"  Precision: {precision * 100:.1f}%")
    print(f"  Coverage: {coverage * 100:.1f}%")
    if false_matches:
        print("  Sample false matches were:")
        for line_id, predicted_code, true_code in false_matches[:EXAMPLE_LIMIT]:
            shown_true_code = true_code or "blank label"
            print(f"    - {line_id}: {predicted_code} was used; {shown_true_code} was given")

    return {
        "name": lane_name,
        "matches": match_count,
        "correct": correct,
        "false": false_matches,
        "precision": precision,
        "coverage": coverage,
        "predictions": predictions,
    }


def audit_matcher_lanes(
    training_rows: list[dict[str, str]],
    aliases: list[dict[str, str]],
    catalogues: dict[str, list[dict[str, str]]],
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[tuple[str, str], set[str]]]]:
    """Measure simple identifier and name matching lanes."""
    print_section("7. BASIC MATCHER CHECKS ON TRAINING DATA")

    training_by_id = {}
    for row in training_rows:
        training_by_id[row["line_id"]] = row

    indexes = build_match_indexes(catalogues)

    barcode_predictions: dict[str, str] = {}
    for row in training_rows:
        barcode = row["raw_barcode"].strip()
        if not barcode:
            continue
        item_codes = indexes["barcode"].get((row["tenant"], barcode), set())
        item_code = one_item_code(item_codes)
        if item_code:
            barcode_predictions[row["line_id"]] = item_code

    alias_index: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for alias in aliases:
        key = (
            alias["tenant"].strip(),
            alias["customer_id"].strip(),
            alias["customer_sku"].strip(),
        )
        alias_index[key].append(alias)

    alias_predictions: dict[str, str] = {}
    for row in training_rows:
        buyer_sku = row["buyer_sku"].strip()
        if not buyer_sku:
            continue

        key = (row["tenant"], row["customer_id"], buyer_sku)
        valid_codes = set()
        for alias in alias_index.get(key, []):
            if not alias_is_valid_on_date(alias, row["order_date"]):
                continue
            item_code = alias["item_code"].strip()
            catalogue_row = row_by_tenant_and_code.get((row["tenant"], item_code))
            if catalogue_row is None:
                continue
            if is_disabled(catalogue_row) or is_misc_catalogue_row(catalogue_row):
                continue
            valid_codes.add(item_code)

        item_code = one_item_code(valid_codes)
        if item_code:
            alias_predictions[row["line_id"]] = item_code

    name_predictions: dict[str, str] = {}
    for row in training_rows:
        normalised_order = normalise_order_text(row["raw_text"])
        item_codes = indexes["name"].get((row["tenant"], normalised_order), set())
        item_code = one_item_code(item_codes)
        if item_code:
            name_predictions[row["line_id"]] = item_code

    results = {
        "barcode": measure_predictions(
            "Unique active barcode lane", barcode_predictions, training_by_id
        ),
        "alias": measure_predictions(
            "Valid customer alias lane", alias_predictions, training_by_id
        ),
        "name": measure_predictions(
            "Unique normalized item-name lane", name_predictions, training_by_id
        ),
    }
    print("These checks were measured on training data only.")
    print("They were not treated as a final matcher.")
    return results, indexes


def audit_label_review_candidates(
    training_rows: list[dict[str, str]],
    indexes: dict[str, dict[tuple[str, str], set[str]]],
    row_by_tenant_and_code: dict[tuple[str, str], dict[str, str]],
) -> dict[str, list[tuple[str, str, str]]]:
    """Find blank labels that have strong or unclear catalogue evidence."""
    print_section("8. LABELS THAT MAY NEED REVIEW")

    unique_barcode_candidates = []
    unique_name_candidates = []
    twin_or_pack_candidates = []

    for row in training_rows:
        if row["gt_item_code"].strip():
            continue

        tenant = row["tenant"].strip()
        line_id = row["line_id"].strip()

        barcode = row["raw_barcode"].strip()
        if barcode:
            barcode_codes = indexes["barcode"].get((tenant, barcode), set())
            barcode_code = one_item_code(barcode_codes)
            if barcode_code:
                unique_barcode_candidates.append(
                    (line_id, barcode_code, "one active barcode match was found")
                )

        normalised_order = normalise_order_text(row["raw_text"])
        name_codes = indexes["name"].get((tenant, normalised_order), set())
        name_code = one_item_code(name_codes)
        if not name_code:
            continue

        catalogue_row = row_by_tenant_and_code[(tenant, name_code)]
        base_name = catalogue_row["item_name"].replace(" (Bulk)", "")
        base_name = normalise_text(base_name)
        base_codes = indexes["base_name"].get((tenant, base_name), set())

        if len(base_codes) > 1:
            twin_or_pack_candidates.append(
                (line_id, name_code, "an active twin or pack choice was found")
            )
        else:
            unique_name_candidates.append(
                (line_id, name_code, "one active exact-name match was found")
            )

    groups = [
        ("Blank labels with one active barcode match", unique_barcode_candidates),
        ("Blank labels with one active exact-name match", unique_name_candidates),
        ("Blank labels with a twin or pack risk", twin_or_pack_candidates),
    ]

    for title, candidates in groups:
        print(f"{title}: {len(candidates)}")
        for line_id, item_code, reason in candidates[:EXAMPLE_LIMIT]:
            print(f"  - {line_id}: {item_code}; {reason}")

    print("These rows were marked for review only.")
    print("A label error was not assumed.")
    return {
        "barcode": unique_barcode_candidates,
        "name": unique_name_candidates,
        "twin_or_pack": twin_or_pack_candidates,
    }


def audit_report_reference(report: dict[str, object]) -> dict[str, object]:
    """Print the main facts stored in the report reference."""
    print_section("9. REPORT REFERENCE")
    rows = report.get("rows", [])
    columns = report.get("columns", [])
    assert isinstance(rows, list)
    assert isinstance(columns, list)

    tenants = set()
    channels = set()
    days = set()
    null_counts = Counter()

    for row in rows:
        tenants.add(row.get("tenant_id"))
        channels.add(row.get("channel"))
        days.add(row.get("day"))
        for column in columns:
            if row.get(column) is None:
                null_counts[column] += 1

    print(f"Reference rows found: {len(rows)}")
    print(f"Reference columns found: {', '.join(columns)}")
    print(f"Baseline run time: {report.get('elapsed_s')} seconds")
    print(f"Tenants found: {len(tenants)}")
    print(f"Channels found: {len(channels)}")
    print(f"Days found: {len(days)}")
    print(f"Missing values by column: {dict(sorted(null_counts.items()))}")
    if "p95_latency_ms" in columns:
        print("The p95_latency_ms column was found.")
    else:
        print("The p95_latency_ms column was not found.")

    return {
        "rows": len(rows),
        "columns": columns,
        "elapsed_s": report.get("elapsed_s"),
        "tenants": len(tenants),
        "channels": len(channels),
        "days": len(days),
        "null_counts": null_counts,
        "has_p95": "p95_latency_ms" in columns,
    }


def print_next_steps(matcher_results: dict[str, dict[str, object]]) -> None:
    """Print short actions that follow from the measured data."""
    print_section("10. NEXT ENGINEERING STEPS")

    barcode_precision = float(matcher_results["barcode"]["precision"]) * 100
    alias_precision = float(matcher_results["alias"]["precision"]) * 100
    name_precision = float(matcher_results["name"]["precision"]) * 100

    print(
        "1. Tenant filters should be applied before any candidate is returned."
    )
    print("2. Disabled and misc rows should be removed before matching.")
    print(
        f"3. The barcode lane was measured at {barcode_precision:.1f}% precision."
    )
    print(
        f"4. The valid alias lane was measured at {alias_precision:.1f}% precision."
    )
    print(
        f"5. The exact-name lane was measured at {name_precision:.1f}% precision."
    )
    print("6. Name-only matches should be reviewed until safer rules are proved.")
    print("7. Review should be used when two active item choices remain.")
    print("8. Rejection should be used for clear non-item lines.")
    print("9. Precision and coverage should be tested at several score limits.")
    print("10. False automatic matches should be tracked by tenant and input type.")
    print("11. The report query should be changed to use grouped data once.")
    print("12. Tenant indexes should be kept separate as the catalogue grows.")
    print("13. Alias updates should be checked before they are trusted.")


def main() -> None:
    """Run every read-only audit section."""
    data = load_all_data()

    catalogue_acme = data["catalogue_acme.csv"]
    catalogue_nordic = data["catalogue_nordic.csv"]
    aliases = data["customer_sku_map.csv"]
    training_rows = data["order_lines_train.csv"]
    holdout_rows = data["order_lines_holdout.csv"]
    uom_rows = data["uom_reference.csv"]
    report = data["report_reference.json.gz"]

    assert isinstance(catalogue_acme, list)
    assert isinstance(catalogue_nordic, list)
    assert isinstance(aliases, list)
    assert isinstance(training_rows, list)
    assert isinstance(holdout_rows, list)
    assert isinstance(uom_rows, list)
    assert isinstance(report, dict)

    catalogues = {
        "acme": catalogue_acme,
        "nordic": catalogue_nordic,
    }

    owner_by_code, row_by_tenant_and_code = build_catalogue_indexes(catalogues)
    audit_date = find_dataset_end_date(training_rows, holdout_rows)

    audit_files(data)
    audit_catalogues(catalogues)
    audit_aliases(
        aliases,
        audit_date,
        owner_by_code,
        row_by_tenant_and_code,
    )
    audit_uom(uom_rows, catalogues, row_by_tenant_and_code)
    audit_training_rows(training_rows, owner_by_code, row_by_tenant_and_code)
    audit_train_holdout_distribution(training_rows, holdout_rows)
    matcher_results, match_indexes = audit_matcher_lanes(
        training_rows,
        aliases,
        catalogues,
        row_by_tenant_and_code,
    )
    audit_label_review_candidates(
        training_rows,
        match_indexes,
        row_by_tenant_and_code,
    )
    audit_report_reference(report)
    print_next_steps(matcher_results)


if __name__ == "__main__":
    main()

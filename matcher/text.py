"""Deterministic text and field normalisation helpers.

The functions in this module do not learn from labels. They turn common writing
variants into stable values while keeping the original values on the input objects.
"""

from __future__ import annotations

import re
import unicodedata


SPREADSHEET_ERROR_TOKENS = ("#NAME?", "#REF!", "#VALUE!", "#DIV/0!", "#N/A")

TOKEN_REPLACEMENTS = {
    "s s": "stainless steel",
    "ss": "stainless steel",
    "ss304": "stainless steel 304",
    "ss316": "stainless steel 316",
    "zp": "zinc plated",
    "galv": "galvanised",
    "pcs": "piece",
    "pc": "piece",
    "nos": "piece",
    "pkt": "packet",
    "ctn": "carton",
    "kg": "kilogram",
}

ORDER_WORDS = {
    "please",
    "pls",
    "send",
    "need",
    "urgent",
    "item",
    "order",
    "kindly",
}

NON_ITEM_PHRASES = (
    "same as last month",
    "subtotal",
    "total only",
    "thanks bro",
    "deliver by",
    "po attached",
    "quote best price",
    "confirm stock",
    "opening balance",
    "delivery fee",
    "misc charge",
)

UOM_ALIASES = {
    "ea": "piece",
    "each": "piece",
    "pc": "piece",
    "pcs": "piece",
    "piece": "piece",
    "pieces": "piece",
    "unit": "piece",
    "units": "piece",
    "nos": "piece",
    "no": "piece",
    "pkt": "packet",
    "packet": "packet",
    "pack": "packet",
    "box": "box",
    "ctn": "carton",
    "carton": "carton",
    "kg": "kilogram",
    "kgs": "kilogram",
    "kilogram": "kilogram",
    "roll": "roll",
    "length": "length",
}


def normalise_text(value: str) -> str:
    """Return a stable lower-case representation of free text."""
    ascii_text = unicodedata.normalize("NFKD", value or "")
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    # Keep dimensions useful: M8x50 becomes "m8 x 50" and 1-1/2 remains visible.
    ascii_text = re.sub(r"(?<=[a-z0-9])x(?=[0-9])", " x ", ascii_text.lower())
    raw_tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", ascii_text)
    joined = " ".join(raw_tokens)
    for old, new in sorted(TOKEN_REPLACEMENTS.items(), key=lambda pair: -len(pair[0])):
        joined = re.sub(rf"\b{re.escape(old)}\b", new, joined)
    return " ".join(joined.split())


def normalise_order_text(value: str) -> str:
    """Normalise an order description and remove low-value order words."""
    tokens = normalise_text(value).split()
    useful_tokens = [token for token in tokens if token not in ORDER_WORDS]
    return " ".join(useful_tokens)


def normalise_identifier(value: str) -> str:
    """Return an identifier without case, spaces, or punctuation differences."""
    return "".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def normalise_uom(value: str) -> str:
    """Map common unit spellings to one value."""
    normalised = normalise_text(value)
    return UOM_ALIASES.get(normalised, normalised)


def text_tokens(value: str) -> set[str]:
    """Return the unique normalised words in a value."""
    return set(normalise_text(value).split())


def numeric_tokens(value: str) -> set[str]:
    """Return tokens that carry a number and often describe size or pack."""
    normalised = normalise_text(value)
    tokens = normalised.split()
    result: set[str] = set()
    for index, token in enumerate(tokens):
        if any(character.isdigit() for character in token):
            result.add(token)
            if index + 1 < len(tokens) and tokens[index + 1] in {
                "mm", "cm", "m", "kilogram", "g", "ml", "l"
            }:
                result.add(f"{token}{tokens[index + 1]}")
    return result


def contains_spreadsheet_error(value: str) -> bool:
    """Return True when a cell contains a known spreadsheet error token."""
    upper_value = (value or "").upper()
    return any(token in upper_value for token in SPREADSHEET_ERROR_TOKENS)


def is_non_item_text(value: str) -> bool:
    """Identify clear request, summary, and courtesy lines with no product."""
    normalised = normalise_text(value)
    if not normalised:
        return True
    if any(phrase in normalised for phrase in NON_ITEM_PHRASES):
        return True
    return len(normalised.split()) <= 2 and normalised in {"subtotal", "total", "thanks"}

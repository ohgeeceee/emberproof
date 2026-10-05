"""Replacement-value estimation.

These are deliberately conservative, clearly-labelled defaults — a starting
number the owner edits. A wrong estimate the owner corrects is far better than
an empty field they never fill in. Every value carries a `value_source` so a
report never presents a guess as a fact.
"""

from __future__ import annotations

CATEGORIES = [
    ("electronics", "Electronics"),
    ("appliance", "Appliances"),
    ("furniture", "Furniture"),
    ("kitchen", "Kitchen"),
    ("bedding", "Bedding & linens"),
    ("clothing", "Clothing"),
    ("tools", "Tools"),
    ("jewelry", "Jewelry & watches"),
    ("musical", "Musical instruments"),
    ("sports", "Sports & fitness"),
    ("outdoor", "Outdoor & lawn"),
    ("documents", "Documents & media"),
    ("other", "Other"),
]

# Median-ish replacement cost per unit, in whole dollars. Deliberately rounded
# down; the point is a floor, not a valuation.
DEFAULT_REPLACEMENT_USD = {
    "electronics": 300,
    "appliance": 600,
    "furniture": 400,
    "kitchen": 60,
    "bedding": 80,
    "clothing": 40,
    "tools": 120,
    "jewelry": 500,
    "musical": 700,
    "sports": 150,
    "outdoor": 250,
    "documents": 20,
    "other": 75,
}

CATEGORY_LABELS = dict(CATEGORIES)


def estimate_cents(category: str, quantity: int = 1) -> int:
    unit = DEFAULT_REPLACEMENT_USD.get(category, DEFAULT_REPLACEMENT_USD["other"])
    return unit * 100 * max(1, int(quantity or 1))


def label(category: str) -> str:
    return CATEGORY_LABELS.get(category, "Other")


def dollars(cents) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:,.0f}"


def dollars_exact(cents) -> str:
    if cents is None:
        return "—"
    return f"${cents / 100:,.2f}"
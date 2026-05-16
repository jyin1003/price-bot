from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal

# Vendor Data Classes
class SourceType(str, Enum):
    SEARCH = "search"
    SPECIFIC = "specific"

@dataclass
class PriceRecord:
    date: str
    product_id: str
    vendor: str
    product_name: str
    category: str
    price: float
    source: SourceType
    
    def __post_init__(self):
        self.product_id = str(self.product_id).strip()
        
        # 1. Handle if date is already a datetime object
        if isinstance(self.date, datetime):
            self.date = self.date.strftime("%Y-%m-%d")
        else:
            try:
                # 2. Attempt to parse common formats
                # This handles '2024-05-20 14:30:00', '2024-05-20T14:30:00', etc.
                dt = datetime.fromisoformat(str(self.date).replace("Z", "+00:00"))
                self.date = dt.strftime("%Y-%m-%d")
            except ValueError:
                # 3. Fallback for custom formats if fromisoformat fails
                # Add specific formats here if your vendors use weird ones
                print(f"Warning: Could not parse date format: {self.date}")

    def to_price_history_row(self) -> dict:
        return {
            "date": self.date,
            "product_id": self.product_id,
            "vendor": self.vendor,
            "category": self.category,
            "price": self.price,
        }

    def to_product_row(self) -> dict:
        return {
            "product_id": self.product_id,
            "vendor": self.vendor,
            "product_name": self.product_name,
            "category": self.category,
            "source": self.source,
            "last_seen": self.date,
        }

PriceStatus = Literal["cheapest", "full price", "discounted"]


@dataclass
class ProductPriceAnalysis:
    """Per-product price analysis (used internally; kept for compatibility)."""
    product_name: str
    current_price: float
    vendor: str
    category: str
    discount: float
    status: PriceStatus


@dataclass
class GroupPriceAnalysis:
    """
    Group-level price analysis — one row per product match group.

    current_price / best_vendor reflect the cheapest member of the group
    based on each member's most recent price in price_history.csv.
    discount and status are computed against the group's all-time max_price
    from grouped_product_metrics.csv.
    """
    group_id: int
    group_name: str
    current_price: float
    best_vendor: str
    category: str
    discount: float
    status: PriceStatus


@dataclass
class CategoryPriceAnalysis:
    category: str
    cheapest_products: list[GroupPriceAnalysis]
    top_five_cheapest: list[GroupPriceAnalysis]
    top_five_most_discounted: list[GroupPriceAnalysis]


@dataclass
class ProductMatchCandidate:
    category: str

    left_product_id: str
    left_vendor: str
    left_product_name: str
    left_max_price: float | None

    right_product_id: str
    right_vendor: str
    right_product_name: str
    right_max_price: float | None

    name_score: float
    price_score: float | None
    final_score: float
    match_reason: str


# ---------------------------------------------------------------------------
# CSV column definitions
# ---------------------------------------------------------------------------

PRICE_HISTORY_COLUMNS = [
    "date",
    "product_id",
    "vendor",
    "category",
    "price",
]

PRODUCTS_COLUMNS = [
    "product_id",
    "vendor",
    "product_name",
    "category",
    "source",
    "last_seen",
]

METRIC_COLUMNS = [
    "product_id",
    "vendor",
    "max_price",
    "min_price",
    "last_updated",
]

# product_match.csv — one row per (group_id, product_id, vendor)
PRODUCT_MATCH_COLUMNS = [
    "group_id",       # monotonically increasing int, e.g. 1, 2, 3
    "group_name",     # token-intersection of all product names in the group
    "category",
    "product_id",
    "vendor",
    "product_name",
]

# grouped_product_metrics.csv — one row per group_id, aggregated across all members
GROUPED_PRODUCT_METRICS_COLUMNS = [
    "group_id",
    "group_name",
    "category",
    "max_price",      # max of max_price across all members
    "min_price",      # min of min_price across all members
    "last_updated",   # most recent last_updated across all members
]

PRODUCT_MATCH_COLUMNS_LEGACY = [
    "match_group_id",
    "category",
    "product_id",
    "vendor",
    "product_name",
    "normalised_name",
    "match_confidence",
    "match_method",
    "review_status",
    "last_updated",
]
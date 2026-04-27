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
    product_name: str
    current_price: float
    vendor: str
    category: str
    discount: float
    status: PriceStatus


@dataclass
class CategoryPriceAnalysis:
    category: str
    cheapest_products: list[ProductPriceAnalysis]
    top_five_cheapest: list[ProductPriceAnalysis]
    top_five_most_discounted: list[ProductPriceAnalysis]

# CSV Constants
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
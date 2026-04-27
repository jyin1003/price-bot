from dataclasses import dataclass
from enum import Enum

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

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import date

from data.model import PriceRecord

class BaseVendor(ABC):
    vendor_name: str

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

    @abstractmethod
    def search_products(self, search_term: str) -> list[dict]:
        """Vendor-specific API search."""
        pass

    @abstractmethod
    def fetch_specific_product(self, product_id: str) -> dict:
        """Vendor-specific API lookup for one product."""
        pass

    @abstractmethod
    def normalise_raw_product(
        self,
        raw_product: dict,
        category: str,
        source: str,
    ) -> PriceRecord:
        """Convert vendor API response into PriceRecord."""
        pass

    def normalise_price(self, raw_product: dict, category: str) -> dict:
        return {
            "date": date.today().isoformat(),
            "product_id": raw_product["product_id"],
            "vendor": self.vendor_name,
            "category": category,
            "price": raw_product["price"],
        }
    
    def fetch_category_prices(
        self,
        category: str,
        search_terms: list[str],
        specific_products: list[str],
    ) -> list[PriceRecord]:

        records_map: dict[str, PriceRecord] = {}

        for product_id in specific_products:
            raw_product = self.fetch_specific_product(product_id)

            record = self.normalise_raw_product(
                raw_product=raw_product,
                category=category,
                source="specific",
            )

            records_map[record.product_id] = record

        for search_term in search_terms:
            raw_products = self.search_products(search_term)

            for raw_product in raw_products:
                record = self.normalise_raw_product(
                    raw_product=raw_product,
                    category=category,
                    source="search",
                )

                # only add if not already seen
                if record.product_id not in records_map:
                    records_map[record.product_id] = record

        return list(records_map.values())
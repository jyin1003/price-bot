import logging
import re
from datetime import date
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from data.model import PriceRecord
from vendors.base import BaseVendor

logger = logging.getLogger(__name__)


class ChemistWarehouseVendor(BaseVendor):
    vendor_name = "chemist_warehouse"

    def __init__(self, data_dir: str = "data") -> None:
        super().__init__(data_dir=data_dir)

        self.base_url = "https://www.chemistwarehouse.com.au"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Chrome/120.0.0.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-AU,en;q=0.9",
            }
        )

    def search_products(self, search_term: str) -> list[dict]:
        """
        Chemist Warehouse search is not implemented yet.

        BaseVendor expects this to return list[dict], so return an empty list.
        Use specific_products with full product URLs for now.
        """
        logger.warning(
            "Chemist Warehouse search is not implemented. "
            "Use specific_products instead. search_term=%s",
            search_term,
        )
        return []

    def fetch_specific_product(self, product_id: str) -> dict | None:
        try:
            url = self._build_product_url(product_id)
        except ValueError:
            logger.exception("Invalid Chemist Warehouse product identifier: %s", product_id)
            return None

        logger.debug("Chemist Warehouse GET request: %s", url)

        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException:
            logger.exception("Chemist Warehouse request failed: %s", url)
            return None

        logger.debug(
            "Chemist Warehouse response: status=%s reason=%s url=%s final_url=%s",
            response.status_code,
            response.reason,
            url,
            response.url,
        )

        if response.status_code < 200 or response.status_code >= 300:
            logger.warning(
                "Chemist Warehouse product fetch failed: status=%s reason=%s url=%s",
                response.status_code,
                response.reason,
                url,
            )
            return None

        return {
            "request_url": url,
            "final_url": response.url,
            "status_code": response.status_code,
            "reason": response.reason,
            "requested_product_id": self._extract_buy_id(product_id),
            "html": response.text,
        }

    def normalise_raw_product(
        self,
        raw_product: dict,
        category: str,
        source: str,
    ) -> PriceRecord:
        soup = BeautifulSoup(raw_product["html"], "html.parser")

        product_name = self._extract_product_name(soup)
        price = self._extract_price(soup)

        buy_id = self._extract_buy_id(raw_product["final_url"])
        page_product_id = self._extract_page_product_id(soup)

        product_id = buy_id or page_product_id or raw_product["requested_product_id"]

        if not product_name:
            raise ValueError("Could not extract Chemist Warehouse product name.")

        if price is None:
            raise ValueError(f"Could not extract Chemist Warehouse price for {product_name}.")

        if not product_id:
            raise ValueError(f"Could not extract Chemist Warehouse product ID for {product_name}.")

        logger.debug(
            "Chemist Warehouse normalised product: product_id=%s product_name=%r price=%s source=%s",
            product_id,
            product_name,
            price,
            source,
        )
        return PriceRecord(
            date=date.today().isoformat(),
            product_id=str(product_id),
            vendor=self.vendor_name,
            product_name=product_name,
            category=category,
            price=price,
            source=source,
        )

    def _build_product_url(self, product_url: str) -> str:
        value = str(product_url).strip()

        if value.startswith("http://") or value.startswith("https://"):
            return value

        if value.startswith("/buy/"):
            return f"{self.base_url}{value}"

        raise ValueError(
            "Chemist Warehouse specific product must be a full product URL "
            "or a full /buy/<id>/<slug> path. Numeric-only IDs do not work "
            "because Chemist Warehouse requires the product slug."
        )

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(" ", strip=True)
            if name:
                return name

        title = soup.find("title")
        if title:
            return (
                title.get_text(" ", strip=True)
                .replace(" | Chemist Warehouse", "")
                .strip()
            )

        return ""

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        text = soup.get_text("\n", strip=True)

        price_matches = re.findall(r"\$(\d+(?:\.\d{1,2})?)", text)

        if not price_matches:
            return None

        prices = [float(price) for price in price_matches]
        logger.debug("Chemist Warehouse extracted prices: %s", prices)

        # Avoid accidentally taking cart totals or unrelated zero values.
        non_zero_prices = [price for price in prices if price > 0]

        if not non_zero_prices:
            return None

        return non_zero_prices[1] # prices are [30, 0, discounted_price, full_price]

    def _extract_page_product_id(self, soup: BeautifulSoup) -> str | None:
        text = soup.get_text("\n", strip=True)

        match = re.search(r"Product ID:\s*(\d+)", text, flags=re.IGNORECASE)

        if match:
            return match.group(1)

        return None

    def _extract_buy_id(self, value: str | None) -> str | None:
        if not value:
            return None

        parsed = urlparse(str(value))
        path = parsed.path if parsed.path else str(value)

        match = re.search(r"/buy/(\d+)", path)

        if match:
            return match.group(1)

        return None
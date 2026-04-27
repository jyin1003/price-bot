import logging
import re
from datetime import date
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from data.model import PriceRecord
from vendors.base import BaseVendor

logger = logging.getLogger(__name__)


class SkinSeoulVendor(BaseVendor):
    vendor_name = "skin_seoul"

    def __init__(self, data_dir: str = "data") -> None:
        super().__init__(data_dir=data_dir)

        self.base_url = "https://skin-seoul.com"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-AU,en;q=0.9",
            }
        )

    def search_products(self, search_term: str) -> list[dict]:
        """
        Skin Seoul search is not implemented yet.

        BaseVendor expects this to return list[dict], so return an empty list.
        Use specific_products with full product URLs for now.
        """
        logger.warning(
            "Skin Seoul search is not implemented. "
            "Use specific_products instead. search_term=%s",
            search_term,
        )
        return []

    def fetch_specific_product(self, product_id: str) -> dict | None:
        try:
            url = self._build_product_url(product_id)
        except ValueError:
            logger.exception("Invalid Skin Seoul product identifier: %s", product_id)
            return None

        logger.debug("Skin Seoul GET request: %s", url)

        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException:
            logger.exception("Skin Seoul request failed: %s", url)
            return None

        logger.debug(
            "Skin Seoul response: status=%s reason=%s url=%s final_url=%s",
            response.status_code,
            response.reason,
            url,
            response.url,
        )

        if response.status_code < 200 or response.status_code >= 300:
            logger.warning(
                "Skin Seoul product fetch failed: status=%s reason=%s url=%s",
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
            "requested_product_id": self._extract_slug(product_id),
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
        sku = self._extract_sku(soup)

        product_id = sku or raw_product["requested_product_id"]

        if not product_name:
            raise ValueError("Could not extract Skin Seoul product name.")

        if price is None:
            raise ValueError(f"Could not extract Skin Seoul price for {product_name}.")

        if not product_id:
            raise ValueError(f"Could not extract Skin Seoul SKU/product ID for {product_name}.")

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

        if value.startswith("/product/"):
            return f"{self.base_url}{value}"

        if value:
            return f"{self.base_url}/product/{value.strip('/')}/"

        raise ValueError(
            "Skin Seoul specific product must be a full product URL, "
            "a /product/<slug>/ path, or a product slug."
        )

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1:
            name = h1.get_text(" ", strip=True)
            if name:
                return name

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        title = soup.find("title")
        if title:
            return (
                title.get_text(" ", strip=True)
                .replace(" | Skin Seoul", "")
                .replace(" - Skin Seoul", "")
                .strip()
            )

        return ""

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        visible_text = self._get_visible_text(soup)
        prices = self._extract_money_values(visible_text)

        logger.debug("Skin Seoul extracted prices: %s", prices)

        if not prices:
            return None

        prices = self._dedupe_repeated_price_sequence(prices)

        has_per_item = re.search(r"per\s+item", visible_text, flags=re.IGNORECASE) is not None

        if has_per_item:
            pack_prices = prices[1:]

            if len(pack_prices) >= 2:
                full_pack_prices = pack_prices[0::2]

                if full_pack_prices:
                    return full_pack_prices[-1]

            return prices[0]

        return prices[0]

    def _dedupe_repeated_price_sequence(self, prices: list[float]) -> list[float]:
        """
        Skin Seoul often renders the same price block twice.

        Example:
            [17.66, 17.66, 8.83, 30.98, 7.75, 17.66, 17.66, 8.83, 30.98, 7.75]

        becomes:
            [17.66, 17.66, 8.83, 30.98, 7.75]
            
        If the page has "per item":
            - treat the prices after the first value (default selected price) as pack pairs:
                full_price, per_item_price
            - return the last full_price
        Otherwise:
            - return the first price
        """
        if len(prices) % 2 != 0:
            return prices

        midpoint = len(prices) // 2

        first_half = prices[:midpoint]
        second_half = prices[midpoint:]

        if first_half == second_half:
            return first_half

        return prices

    def _extract_sku(self, soup: BeautifulSoup) -> str | None:
        """
        Screenshot shows the SKU block as visible text like:

        SKU
        100054443

        The regex handles newlines/comments between the label and number.
        """
        text = self._get_visible_text(soup)

        match = re.search(r"\bSKU\b\s*([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

    def _extract_money_values(self, text: str) -> list[float]:
        matches = re.findall(r"A?\$\s*(\d+(?:\.\d{1,2})?)", text)

        values: list[float] = []

        for match in matches:
            try:
                values.append(float(match))
            except ValueError:
                continue

        return values

    def _get_visible_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        return soup.get_text("\n", strip=True)

    def _extract_slug(self, value: str | None) -> str | None:
        if not value:
            return None

        parsed = urlparse(str(value))
        path = parsed.path if parsed.path else str(value)

        match = re.search(r"/product/([^/]+)/?", path)

        if match:
            return match.group(1)

        return str(value).strip().strip("/") or None
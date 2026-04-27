from __future__ import annotations

import json, os, re
from datetime import date
from urllib.parse import urlencode

import http.client

from vendors.base import BaseVendor
from data.model import PriceRecord, SourceType
from config import COLES_MAX_PAGES, COLES_LIMIT

class ColesVendor(BaseVendor):
    vendor_name = "coles"

    def __init__(self, data_dir: str = "data"):
        super().__init__(data_dir=data_dir)

        self.api_host = os.getenv("COLES_API_HOST")
        self.api_key = os.getenv("COLES_API_KEY")

        if not self.api_host:
            raise ValueError("Missing COLES_API_HOST in environment variables")

        if not self.api_key:
            raise ValueError("Missing COLES_API_KEY in environment variables")

        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.api_host,
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict:
        conn = http.client.HTTPSConnection(self.api_host)

        try:
            conn.request("GET", path, headers=self.headers)
            response = conn.getresponse()
            raw_data = response.read().decode("utf-8")

            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Coles API request failed: {response.status} {response.reason} - {raw_data}"
                )

            return json.loads(raw_data)

        finally:
            conn.close()
            
    def _extract_coles_item_id(self, product_identifier: str) -> str:
        """
        Accepts either:
        - Coles item ID: '2372797'
        - Coles slug: 'kleenex-3-ply-large-n-thick-aloe-vera-facial-tissues-70-pack-2372797'

        Returns:
        - '2372797'
        """

        product_identifier = str(product_identifier).strip()

        if product_identifier.isdigit():
            return product_identifier

        match = re.search(r"-(\d+)$", product_identifier)

        if match:
            return match.group(1)

        raise ValueError(
            f"Could not extract Coles item_id from product identifier: {product_identifier}"
        )


    def search_products(
        self,
        search_term: str,
        max_pages: int = COLES_MAX_PAGES,
        limit: int = COLES_LIMIT,
    ) -> list[dict]:
        all_results: list[dict] = []

        for page in range(1, max_pages + 1):
            query_params = urlencode(
                {
                    "query": search_term,
                    "context_mode": "delivery",
                    "page": page,
                    "limit": limit,
                }
            )

            data = self._get(f"/coles/search?{query_params}")

            results = data.get("results", [])
            total = data.get("total", 0)

            all_results.extend(results)

            if len(all_results) >= total:
                break

            if not results:
                break

        return all_results

    def fetch_specific_product(self, product_id: str) -> dict:
        """
        Fetch one Coles product directly by item ID or slug.
        """

        item_id = self._extract_coles_item_id(product_id)

        query_params = urlencode(
            {
                "item_id": item_id,
                "context_mode": "delivery",
            }
        )

        data = self._get(f"/coles/item?{query_params}")

        result = data.get("result")

        if not result:
            raise ValueError(f"Coles product not found: {product_id}")

        return result

    def normalise_raw_product(
        self,
        raw_product: dict,
        category: str,
        source: SourceType | str,
    ) -> PriceRecord:
        """
        Convert a Coles API product response into a standard PriceRecord.
        """

        product_id = str(raw_product.get("id") or raw_product.get("slug"))

        if not product_id:
            raise ValueError(f"Coles product missing id/slug: {raw_product}")

        brand = raw_product.get("brand")
        name = raw_product.get("name", "")

        if brand and brand.lower() not in name.lower():
            product_name = f"{brand} {name}".strip()
        else:
            product_name = name.strip()

        price = raw_product.get("discount_price", raw_product.get("price"))

        if price is None:
            raise ValueError(f"Coles product missing price: {product_id}")

        if isinstance(source, str):
            source = SourceType(source)

        return PriceRecord(
            date=date.today().isoformat(),
            product_id=product_id,
            vendor=self.vendor_name,
            product_name=product_name,
            category=category,
            price=float(price),
            source=source,
        )
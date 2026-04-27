from __future__ import annotations

import json
import os
from datetime import date
from urllib.parse import urlencode

import http.client

from vendors.base import BaseVendor
from data.model import PriceRecord, SourceType

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

    def search_products(self, search_term: str) -> list[dict]:
        """
        Search Coles products by keyword.
        """

        query_params = urlencode(
            {
                "query": search_term,
                "context_mode": "delivery",
                "page": 1,
                "limit": 30,
            }
        )

        data = self._get(f"/coles/search?{query_params}")

        return data.get("results", [])

    def fetch_specific_product(self, product_id: str) -> dict:
        """
        Fetch one Coles product.

        The API example only gives a search endpoint, so this method supports
        exact lookup by searching the product ID or slug and returning the exact match.
        """

        raw_products = self.search_products(product_id)

        for product in raw_products:
            product_id_match = str(product.get("id")) == str(product_id)
            slug_match = product.get("slug") == product_id

            if product_id_match or slug_match:
                return product

        raise ValueError(f"Coles product not found: {product_id}")

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
from __future__ import annotations

import json, os, re, logging
from datetime import date
from urllib.parse import urlencode

import http.client

from vendors.base import BaseVendor
from data.model import PriceRecord, SourceType
from price_bot.config import COLES_MAX_PAGES, COLES_LIMIT


logger = logging.getLogger(__name__)


class ColesVendor(BaseVendor):
    vendor_name = "coles"

    def __init__(self, data_dir: str = "data"):
        super().__init__(data_dir=data_dir)

        self.api_host = os.getenv("COLES_API_HOST")
        self.api_key = os.getenv("COLES_API_KEY")

        if not self.api_host:
            logger.error("Missing COLES_API_HOST in environment variables")
            raise ValueError("Missing COLES_API_HOST in environment variables")

        if not self.api_key:
            logger.error("Missing COLES_API_KEY in environment variables")
            raise ValueError("Missing COLES_API_KEY in environment variables")

        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.api_host,
            "Content-Type": "application/json",
        }

        logger.info("Initialised ColesVendor with host=%s", self.api_host)

    def _get(self, path: str) -> dict | None:
        logger.debug("Coles API GET request: %s", path)

        conn = http.client.HTTPSConnection(self.api_host)

        try:
            conn.request("GET", path, headers=self.headers)
            response = conn.getresponse()
            raw_data = response.read().decode("utf-8")

            logger.debug(
                "Coles API response: status=%s reason=%s path=%s",
                response.status,
                response.reason,
                path,
            )

            if response.status == 404:
                logger.warning(
                    "Coles API resource not found. Skipping: path=%s response=%s",
                    path,
                    raw_data,
                )
                return None

            if response.status < 200 or response.status >= 300:
                logger.error(
                    "Coles API request failed: status=%s reason=%s path=%s response=%s",
                    response.status,
                    response.reason,
                    path,
                    raw_data,
                )
                raise RuntimeError(
                    f"Coles API request failed: {response.status} {response.reason} - {raw_data}"
                )

            try:
                return json.loads(raw_data)
            except json.JSONDecodeError:
                logger.exception("Failed to decode Coles API JSON response for path=%s", path)
                raise

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
            logger.debug("Using Coles item_id directly: %s", product_identifier)
            return product_identifier

        match = re.search(r"-(\d+)$", product_identifier)

        if match:
            item_id = match.group(1)
            logger.debug(
                "Extracted Coles item_id=%s from product_identifier=%s",
                item_id,
                product_identifier,
            )
            return item_id

        logger.error(
            "Could not extract Coles item_id from product_identifier=%s",
            product_identifier,
        )
        raise ValueError(
            f"Could not extract Coles item_id from product identifier: {product_identifier}"
        )

    def search_products(
        self,
        search_term: str,
        max_pages: int = COLES_MAX_PAGES,
        limit: int = COLES_LIMIT,
    ) -> list[dict]:
        """
        Example Response:
        {
            status:"success"
            store_context:
                context_mode:"delivery"
            result:
                id:"2372797"
            slug:"kleenex-3-ply-large-n-thick-aloe-vera-facial-tissues-70-pack-2372797"
            name:"3 Ply Large N Thick Aloe Vera Facial Tissues"
            brand:"Kleenex"
            gtin:"9310088009712"
            barcode:"9310088009712"
            source_url:"https://www.coles.com.au/product/kleenex-3-ply-large-n-thick-aloe-vera-facial-tissues-70-pack-2372797"
            category:"Cleaning & Laundry"
            breadcrumbs:
                0:"Cleaning & Laundry"
                1:"Toilet Paper, Tissues & Paper Towels"
                2:"Facial Tissues"
            price:2.6
            currency:"AUD"
            size:"70 pack"
            unit:"each"
            unit_quantity:100
            unit_price:3.71
            price_per_unit_unit:"each"
            price_per_unit_quantity:100
            price_per_unit_price:3.71
            is_available:true
            in_stock:true
            images:
                image:"https://productimages.coles.com.au/productimages/2/2372797.jpg"
            price_info:
                0:
                    price:2.6
                    price_per_unit_unit:"each"
                    price_per_unit_quantity:100
                    price_per_unit_price:3.71
            description:"Kleenex Aloe Vera & Vitamin E Large & Thick tissues are nearly 40% larger for when you want even more Kleenex softness. Kleenex Aloe Vera & Vitamin E Large & Thick tissues feature Softcoat Lotion Technology, carefully coated with natural Aloe Vera and Vitamin E to help soothe your skin Perfect for times when sniffles and sneezes make your nose feel extra sensitive 3-ply thickness, 70 sheets per box, 28.5cm x 19.5cm Our Kleenex Facial Tissues are Aussie made and we're proud of it; they've been made at our Millicent mill in South Australia since 1966. This means support for local communities, including hundreds of local employees and their families, each year. FSC Certified, ensuring responsible forest management, meeting the most rigorous environmental and social standard for responsible forest management. Nearly 40% larger Nearly 40% larger for when you want even more Kleenex softness Softcoat Lotion Technology Softcoat Lotion Technology to help soothe your skin Aloe Vera and Vitamin E Carefully coated with natural Aloe Vera and Vitamin E 0 Perfect for times when sniffles and sneezes make your nose feel extra sensitive Made in Australia Kleenex Facial Tissues have been made at our Millicent Mill in South Australia since 1966. FSC Certified Made from ethically sourced fibre that promotes the sustainable management of forests, Kleenex Facial Tissue has earned Forest Stewardship Council (FSC) certification - the highest possible independent standard for responsible forest management.. 3-Ply Thickness 3-Ply Thickness. 70 tissues per box, 28.5cm x 19.5cm."
            dimensions:"115.00 x 210.00 x 75.00 mm"
            location_description:"Aisle information is not available for this product. Please ask a Team Member at $STORE to help you find this product."
            facing:0
            location_order:9999
            country_of_origin:"Australia"
            country_of_origin_percentage:0
        }
        """
        logger.info(
            "Searching Coles products: search_term=%r max_pages=%s limit=%s",
            search_term,
            max_pages,
            limit,
        )

        all_results: list[dict] = []
        expected_total: int | None = None

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
            page_total = data.get("total")

            if expected_total is None and isinstance(page_total, int):
                expected_total = page_total

            logger.info(
                "Coles search page fetched: search_term=%r page=%s results=%s page_total=%s expected_total=%s accumulated=%s",
                search_term,
                page,
                len(results),
                page_total,
                expected_total,
                len(all_results) + len(results),
            )

            if not results:
                logger.warning(
                    "Stopping Coles search because page returned no results: search_term=%r page=%s expected_total=%s accumulated=%s",
                    search_term,
                    page,
                    expected_total,
                    len(all_results),
                )
                break

            all_results.extend(results)

            if expected_total is not None and len(all_results) >= expected_total:
                logger.info(
                    "Finished Coles search because accumulated results reached expected total: search_term=%r expected_total=%s",
                    search_term,
                    expected_total,
                )
                break

        logger.info(
            "Completed Coles product search: search_term=%r returned=%s expected_total=%s",
            search_term,
            len(all_results),
            expected_total,
        )

        return all_results

    def fetch_specific_product(self, product_id: str) -> dict | None:
        """
        Fetch one Coles product directly by item ID or slug.
        """

        logger.debug("Fetching specific Coles product: product_id=%s", product_id)

        item_id = self._extract_coles_item_id(product_id)

        query_params = urlencode(
            {
                "item_id": item_id,
                "context_mode": "delivery",
            }
        )

        data = self._get(f"/coles/item?{query_params}")
        if not data:
            logger.warning(
                "Coles product not found: product_id=%s item_id=%s",
                product_id,
                item_id,
            )
            return None

        result = data.get("result")

        if not result:
            logger.warning(
                "Coles product not found: product_id=%s item_id=%s",
                product_id,
                item_id,
            )
            raise ValueError(f"Coles product not found: {product_id}")

        logger.info(
            "Fetched specific Coles product: product_id=%s item_id=%s name=%r",
            product_id,
            item_id,
            result.get("name"),
        )

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

        product_id = str(raw_product.get("id") or raw_product.get("slug") or "").strip()

        if not product_id:
            logger.error("Coles product missing id/slug: raw_product=%s", raw_product)
            raise ValueError(f"Coles product missing id/slug: {raw_product}")

        brand = raw_product.get("brand")
        name = raw_product.get("name", "")

        if brand and brand.lower() not in name.lower():
            product_name = f"{brand} {name}".strip()
        else:
            product_name = name.strip()

        price = raw_product.get("discount_price", raw_product.get("price"))

        if price is None:
            logger.error(
                "Coles product missing price: product_id=%s product_name=%r raw_product=%s",
                product_id,
                product_name,
                raw_product,
            )
            raise ValueError(f"Coles product missing price: {product_id}")

        if isinstance(source, str):
            source = SourceType(source)

        record = PriceRecord(
            date=date.today().isoformat(),
            product_id=product_id,
            vendor=self.vendor_name,
            product_name=product_name,
            category=category,
            price=float(price),
            source=source,
        )

        logger.debug(
            "Normalised Coles product: product_id=%s name=%r category=%s price=%s source=%s",
            record.product_id,
            record.product_name,
            record.category,
            record.price,
            record.source,
        )

        return record
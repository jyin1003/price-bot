from __future__ import annotations

import json, os, re,logging
from datetime import date
from urllib.parse import urlencode

import http.client

from vendors.base import BaseVendor
from data.model import PriceRecord, SourceType
from price_bot.config import WOOLWORTHS_MAX_PAGES, WOOLWORTHS_PAGE_SIZE


logger = logging.getLogger(__name__)

class WoolworthsVendor(BaseVendor):
    vendor_name = "woolworths"

    def __init__(self, data_dir: str = "data"):
        super().__init__(data_dir=data_dir)

        self.api_key = os.getenv("WOOLWORTHS_API_KEY")
        self.product_search_host = os.getenv("WOOLWORTHS_API_PRODUCT_SEARCH_HOST")
        self.product_detail_search_host = os.getenv("WOOLWORTHS_API_PRODUCT_DETAIL_SEARCH_HOST")

        if not self.api_key:
            logger.error("Missing WOOLWORTHS_API_KEY in environment variables")
            raise ValueError("Missing WOOLWORTHS_API_KEY in environment variables")

        if not self.product_search_host:
            logger.error("Missing WOOLWORTHS_API_PRODUCT_SEARCH_HOST in environment variables")
            raise ValueError("Missing WOOLWORTHS_API_PRODUCT_SEARCH_HOST in environment variables")

        if not self.product_detail_search_host:
            logger.error("Missing WOOLWORTHS_API_PRODUCT_DETAIL_SEARCH_HOST in environment variables")
            raise ValueError("Missing WOOLWORTHS_API_PRODUCT_DETAIL_SEARCH_HOST in environment variables")

        logger.info(
            "Initialised WoolworthsVendor with search_host=%s detail_host=%s",
            self.product_search_host,
            self.product_detail_search_host,
        )

    def _headers_for_host(self, host: str) -> dict[str, str]:
        return {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": host,
            "Content-Type": "application/json",
        }

    def _get(self, host: str, path: str) -> dict | None:
        logger.debug("Woolworths API GET request: host=%s path=%s", host, path)

        conn = http.client.HTTPSConnection(host)

        try:
            conn.request("GET", path, headers=self._headers_for_host(host))
            response = conn.getresponse()
            raw_data = response.read().decode("utf-8")

            logger.debug(
                "Woolworths API response: status=%s reason=%s host=%s path=%s",
                response.status,
                response.reason,
                host,
                path,
            )

            if response.status == 404:
                logger.warning(
                    "Woolworths API resource not found. Skipping: host=%s path=%s response=%s",
                    host,
                    path,
                    raw_data,
                )
                return None

            if response.status < 200 or response.status >= 300:
                logger.error(
                    "Woolworths API request failed: status=%s reason=%s host=%s path=%s response=%s",
                    response.status,
                    response.reason,
                    host,
                    path,
                    raw_data,
                )
                raise RuntimeError(
                    f"Woolworths API request failed: {response.status} {response.reason} - {raw_data}"
                )

            try:
                return json.loads(raw_data)
            except json.JSONDecodeError:
                logger.exception(
                    "Failed to decode Woolworths API JSON response for host=%s path=%s",
                    host,
                    path,
                )
                raise

        finally:
            conn.close()

    def _extract_woolworths_product_id(self, product_identifier: str | int) -> str:
        """
        Accepts:
        - Woolworths product ID: '759496'
        - Woolworths product URL: 'https://www.woolworths.com.au/shop/productdetails/759496'

        Returns:
        - '759496'
        """

        product_identifier = str(product_identifier).strip()

        if product_identifier.isdigit():
            logger.debug("Using Woolworths product_id directly: %s", product_identifier)
            return product_identifier

        match = re.search(r"/productdetails/(\d+)", product_identifier)

        if match:
            product_id = match.group(1)
            logger.debug(
                "Extracted Woolworths product_id=%s from product_identifier=%s",
                product_id,
                product_identifier,
            )
            return product_id

        match = re.search(r"(\d+)$", product_identifier)

        if match:
            product_id = match.group(1)
            logger.debug(
                "Extracted trailing Woolworths product_id=%s from product_identifier=%s",
                product_id,
                product_identifier,
            )
            return product_id

        logger.error(
            "Could not extract Woolworths product_id from product_identifier=%s",
            product_identifier,
        )
        raise ValueError(
            f"Could not extract Woolworths product_id from product identifier: {product_identifier}"
        )

    def _extract_product_id_from_search_result(self, raw_product: dict) -> str:
        """
        They return a product URL, where the final number is the product_id.

        Example:
        url='https://www.woolworths.com.au/shop/productdetails/759496'
        product_id='759496'
        """

        direct_id = raw_product.get("id") or raw_product.get("product_id") or raw_product.get("sku")

        if direct_id:
            return self._extract_woolworths_product_id(direct_id)

        url = raw_product.get("url") or raw_product.get("source_url")

        if url:
            return self._extract_woolworths_product_id(url)

        logger.error("Woolworths search result missing product id/url: raw_product=%s", raw_product)
        raise ValueError(f"Woolworths search result missing product id/url: {raw_product}")

    def search_products(
        self,
        search_term: str,
        max_pages: int = WOOLWORTHS_MAX_PAGES,
        size: int = WOOLWORTHS_PAGE_SIZE,
    ) -> list[dict]:
        """
        Example Response
        {
            query:"tissue"
            results:
                0:
                    barcode:9300633499815
                    product_name:"Essentials Facial Tissues"
                    product_brand:"Essentials"
                    current_price:1.9
                    product_size:"224 pack"
                    url:"https://www.woolworths.com.au/shop/productdetails/759496"
                1:
                    barcode:9310088018462
                    product_name:"Kleenex Ultimate 6ply Tissues"
                    product_brand:"Kleenex"
                    current_price:2
                    product_size:"20 pack"
                    url:"https://www.woolworths.com.au/shop/productdetails/6006077"
                ...
                9:
                    barcode:9339687212583
                    product_name:"Vevelle Aloe Vera Tissues 3Ply"
                    product_brand:"Vevelle"
                    current_price:1.7
                    product_size:"95 pack"
                    url:"https://www.woolworths.com.au/shop/productdetails/121154"
            total_results:59
            total_pages:6
            current_page:1
        }
        """

        logger.info(
            "Searching Woolworths products: search_term=%r max_pages=%s size=%s",
            search_term,
            max_pages,
            size,
        )

        all_results: list[dict] = []
        seen_product_ids: set[str] = set()
        expected_total: int | None = None
        total_pages: int | None = None

        for page_index in range(1, max_pages):
            query_params = urlencode(
                {
                    "query": search_term,
                    "page": page_index,
                    "size": size,
                }
            )

            data = self._get(
                self.product_search_host,
                f"/woolworths/product-search/?{query_params}",
            )

            results = data.get("results", [])

            if expected_total is None and isinstance(data.get("total_results"), int):
                expected_total = data.get("total_results")

            if total_pages is None and isinstance(data.get("total_pages"), int):
                total_pages = data.get("total_pages")

            logger.info(
                "Woolworths search page fetched: search_term=%r page_index=%s current_page=%s results=%s total_results=%s total_pages=%s accumulated=%s",
                search_term,
                page_index,
                data.get("current_page"),
                len(results),
                expected_total,
                total_pages,
                len(all_results) + len(results),
            )

            if not results:
                logger.warning(
                    "Stopping Woolworths search because page returned no results: search_term=%r page_index=%s total_results=%s accumulated=%s",
                    search_term,
                    page_index,
                    expected_total,
                    len(all_results),
                )
                break

            for raw_product in results:
                try:
                    product_id = self._extract_product_id_from_search_result(raw_product)
                except ValueError:
                    logger.exception(
                        "Skipping Woolworths search result because product_id could not be extracted: search_term=%r raw_product=%s",
                        search_term,
                        raw_product,
                    )
                    continue

                if product_id in seen_product_ids:
                    logger.debug(
                        "Skipping duplicate Woolworths product from search: search_term=%r product_id=%s",
                        search_term,
                        product_id,
                    )
                    continue

                raw_product["product_id"] = product_id
                seen_product_ids.add(product_id)
                all_results.append(raw_product)

            if expected_total is not None and len(all_results) >= expected_total:
                logger.info(
                    "Finished Woolworths search because accumulated results reached expected total: search_term=%r expected_total=%s",
                    search_term,
                    expected_total,
                )
                break

            if total_pages is not None and page_index + 1 >= total_pages:
                logger.info(
                    "Finished Woolworths search because page_index reached total_pages: search_term=%r total_pages=%s",
                    search_term,
                    total_pages,
                )
                break

        logger.info(
            "Completed Woolworths product search: search_term=%r returned=%s expected_total=%s total_pages=%s",
            search_term,
            len(all_results),
            expected_total,
            total_pages,
        )

        return all_results

    def fetch_specific_product(self, product_id: str) -> dict | None:
        """
        Example Response
        {
            status:"success"
            result:
                id:759496
                sku:"759496"
                barcode:"9300633499815"
                name:"Essentials Facial Tissues 224 pack"
                slug:"essentials-facial-tissues"
                brand:"Essentials"
                price:1.9
                discount_price:1.9
                unit_price:"$0.85 / 100SS"
                is_on_special:false
            price_info:
                0:
                    price:1.9
                    discount_price:1.9
                    unit_price:"$0.85 / 100SS"
                    unit:"Each"
                    size:"224 pack"
                    minimum_quantity:1
                    stock_status:"InStock"
                    is_available:true
                    is_purchasable:true
            image:"https://cdn0.woolworths.media/content/wowproductimages/large/759496.jpg"
            url:"https://www.woolworths.com.au/shop/productdetails/759496"
            source_url:"https://www.woolworths.com.au/shop/productdetails/759496"
            category_id:"1_2432B58"
            description:"Essentials Facial Tissues 224 pack"
            specifications:
            ingredients:null
            allergens:null
            storage:"Store in a cool, dry place."
            lifestyle:null
            ingredients:null
            allergens:null
            nutrition:null
        }
        """

        logger.debug("Fetching specific Woolworths product: product_id=%s", product_id)

        woolworths_product_id = self._extract_woolworths_product_id(product_id)

        query_params = urlencode(
            {
                "product_id": woolworths_product_id,
            }
        )

        data = self._get(
            self.product_detail_search_host,
            f"/woolworths/item?{query_params}",
        )
        if not data:
            logger.warning(
                "Woolworths product not found: product_id=%s woolworths_product_id=%s",
                product_id,
                woolworths_product_id,
            )
            return None

        result = data.get("result")

        if not result:
            logger.warning(
                "Woolworths product not found: product_id=%s woolworths_product_id=%s response_status=%s",
                product_id,
                woolworths_product_id,
                data.get("status"),
            )
            raise ValueError(f"Woolworths product not found: {product_id}")

        result["product_id"] = str(result.get("id") or result.get("sku") or woolworths_product_id)

        logger.info(
            "Fetched specific Woolworths product: product_id=%s woolworths_product_id=%s name=%r",
            product_id,
            woolworths_product_id,
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
        Convert a Woolworths API product response into a standard PriceRecord.

        Handles both:
        - product-search response shape
        - product-detail response shape
        """

        product_id = str(
            raw_product.get("product_id")
            or raw_product.get("id")
            or raw_product.get("sku")
            or ""
        ).strip()

        if not product_id:
            product_id = self._extract_product_id_from_search_result(raw_product)

        if not product_id:
            logger.error("Woolworths product missing product_id/id/sku/url: raw_product=%s", raw_product)
            raise ValueError(f"Woolworths product missing product_id/id/sku/url: {raw_product}")

        brand = raw_product.get("brand") or raw_product.get("product_brand")
        name = raw_product.get("name") or raw_product.get("product_name") or ""

        size = raw_product.get("size") or raw_product.get("product_size")

        if brand and brand.lower() not in name.lower():
            product_name = f"{brand} {name}".strip()
        else:
            product_name = name.strip()

        if size and size.lower() not in product_name.lower():
            product_name = f"{product_name} {size}".strip()

        price = (
            raw_product.get("discount_price")
            if raw_product.get("discount_price") is not None
            else raw_product.get("price")
        )

        if price is None:
            price = raw_product.get("current_price")

        if price is None:
            logger.error(
                "Woolworths product missing price: product_id=%s product_name=%r raw_product=%s",
                product_id,
                product_name,
                raw_product,
            )
            raise ValueError(f"Woolworths product missing price: {product_id}")

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
            "Normalised Woolworths product: product_id=%s name=%r category=%s price=%s source=%s",
            record.product_id,
            record.product_name,
            record.category,
            record.price,
            record.source,
        )

        return record
from pathlib import Path
import pandas as pd
import yaml

from vendors.coles import ColesVendor
from data.model import PriceRecord, PRICE_HISTORY_COLUMNS, PRODUCTS_COLUMNS
from config import DATA_DIR, PRODUCTS_YAML_PATH, PRICE_HISTORY_PATH, PRODUCTS_PATH

VENDOR_REGISTRY = {
    "coles": ColesVendor,
}

def load_products_config(path: Path = PRODUCTS_YAML_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    if not PRICE_HISTORY_PATH.exists():
        pd.DataFrame(columns=PRICE_HISTORY_COLUMNS).to_csv(
            PRICE_HISTORY_PATH,
            index=False,
        )

    if not PRODUCTS_PATH.exists():
        pd.DataFrame(columns=PRODUCTS_COLUMNS).to_csv(
            PRODUCTS_PATH,
            index=False,
        )


def fetch_all_prices(products_config: dict) -> list[PriceRecord]:
    records: list[PriceRecord] = []

    categories = products_config.get("categories", {})

    for category_name, category_config in categories.items():
        search_terms = category_config.get("search_terms", [])
        specific_products = category_config.get("specific_products", [])
        vendors = category_config.get("vendors", [])

        for vendor_name in vendors:
            if vendor_name not in VENDOR_REGISTRY:
                print(f"[fetch_prices] Skipping unsupported vendor: {vendor_name}")
                continue

            vendor_class = VENDOR_REGISTRY[vendor_name]
            vendor = vendor_class()

            vendor_records = vendor.fetch_category_prices(
                category=category_name,
                search_terms=search_terms,
                specific_products=specific_products,
            )

            records.extend(vendor_records)

    return records


def update_price_history(records: list[PriceRecord]) -> None:
    existing = pd.read_csv(PRICE_HISTORY_PATH)

    new_rows = pd.DataFrame(
        [record.to_price_history_row() for record in records],
        columns=PRICE_HISTORY_COLUMNS,
    )

    combined = pd.concat([existing, new_rows], ignore_index=True)

    # If the same product/vendor/category is collected again on the same date,
    # keep the latest collected row.
    combined = combined.drop_duplicates(
        subset=["date", "product_id", "vendor", "category"],
        keep="last",
    )

    combined = combined.sort_values(
        by=["date", "vendor", "category", "product_id"],
    )

    combined.to_csv(PRICE_HISTORY_PATH, index=False)


def update_products_registry(records: list[PriceRecord]) -> None:
    existing = pd.read_csv(PRODUCTS_PATH)

    new_rows = pd.DataFrame(
        [record.to_product_row() for record in records],
        columns=PRODUCTS_COLUMNS,
    )

    combined = pd.concat([existing, new_rows], ignore_index=True)

    # Product registry should only have one latest row per vendor product.
    combined = combined.drop_duplicates(
        subset=["product_id", "vendor"],
        keep="last",
    )

    combined = combined.sort_values(
        by=["vendor", "category", "product_name"],
    )

    combined.to_csv(PRODUCTS_PATH, index=False)


def run_fetch_prices() -> list[PriceRecord]:
    ensure_data_files()

    products_config = load_products_config()
    records = fetch_all_prices(products_config)

    if not records:
        print("[fetch_prices] No price records fetched.")
        return []

    update_price_history(records)
    update_products_registry(records)

    print(f"[fetch_prices] Fetched {len(records)} price records.")
    print(f"[fetch_prices] Updated {PRICE_HISTORY_PATH}")
    print(f"[fetch_prices] Updated {PRODUCTS_PATH}")

    return records


if __name__ == "__main__":
    run_fetch_prices()
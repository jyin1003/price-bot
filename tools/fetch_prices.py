import logging

import pandas as pd

from data.model import PriceRecord, PRICE_HISTORY_COLUMNS, PRODUCTS_COLUMNS
from price_bot.config import DATA_DIR, PRICE_HISTORY_PATH, PRODUCTS_PATH
from price_bot.setup import VENDOR_REGISTRY, load_products_config

logger = logging.getLogger(__name__)


def ensure_data_files() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    if not PRICE_HISTORY_PATH.exists():
        pd.DataFrame(columns=PRICE_HISTORY_COLUMNS).to_csv(
            PRICE_HISTORY_PATH,
            index=False,
        )
        logger.info("Created price history file: %s", PRICE_HISTORY_PATH)

    if not PRODUCTS_PATH.exists():
        pd.DataFrame(columns=PRODUCTS_COLUMNS).to_csv(
            PRODUCTS_PATH,
            index=False,
        )
        logger.info("Created products registry file: %s", PRODUCTS_PATH)


def get_specific_products_for_vendor(
    category_config: dict,
    vendor_name: str,
) -> list[str]:
    specific_products = category_config.get("specific_products", {})

    if isinstance(specific_products, list):
        return specific_products

    if isinstance(specific_products, dict):
        return specific_products.get(vendor_name, [])

    raise TypeError(
        f"specific_products must be a list or dict, got {type(specific_products)}"
    )


def _normalise_text(value: str) -> str:
    """
    Normalise text for case-insensitive matching.

    This means:
    - "Toilet Paper"
    - "toilet paper"
    - "TOILET PAPER"

    are all treated the same.
    """
    return value.casefold()


def _normalise_terms(terms: list[str] | None) -> list[str]:
    if not terms:
        return []

    return [_normalise_text(term.strip()) for term in terms if term and term.strip()]


def is_record_allowed_by_category_filters(
    record: PriceRecord,
    category_config: dict,
) -> bool:
    # 1. Normalise the product name once for efficiency
    product_name = _normalise_text(record.product_name)

    # 2. Extract and Normalise config terms
    must_include = _normalise_terms(category_config.get("must_include_terms"))
    or_include = _normalise_terms(category_config.get("or_include_terms"))
    must_exclude = _normalise_terms(category_config.get("must_exclude_terms"))

    # Hurdle 1: Must NOT contain any 'must_exclude_terms'
    if must_exclude:
        if any(term in product_name for term in must_exclude):
            logger.debug("Filtered (Excluded term found): %r", record.product_name)
            return False

    # Hurdle 2: Must contain ALL 'must_include_terms'
    if must_include:
        # Using all() ensures every term in the list is present in the name
        if not all(term in product_name for term in must_include):
            logger.debug("Filtered (Missing required terms): %r", record.product_name)
            return False

    # Hurdle 3: Must contain at least ONE 'or_include_terms' (if the list is provided)
    if or_include:
        # Using any() ensures at least one choice is present
        if not any(term in product_name for term in or_include):
            logger.debug("Filtered (Missing any OR terms): %r", record.product_name)
            return False

    # If it passed all hurdles above, it's a valid product
    return True


def filter_records_for_category(
    records: list[PriceRecord],
    category_config: dict,
) -> list[PriceRecord]:
    filtered_records = [
        record
        for record in records
        if is_record_allowed_by_category_filters(
            record=record,
            category_config=category_config,
        )
    ]

    removed_count = len(records) - len(filtered_records)

    if removed_count:
        logger.info(
            "Filtered category records: category=%s original=%s kept=%s removed=%s",
            records[0].category if records else None,
            len(records),
            len(filtered_records),
            removed_count,
        )

    return filtered_records


def fetch_all_prices(
    products_config: dict,
    only_vendors: set[str] | None = None,
    only_categories: set[str] | None = None,
    dry_run: bool = False,
) -> list[PriceRecord]:
    records: list[PriceRecord] = []

    categories = products_config.get("categories", {})

    if not categories:
        logger.warning("No categories found in products.yaml")
        return records

    for category_name, category_config in categories.items():
        if only_categories and category_name not in only_categories:
            logger.debug("Skipping category due to category filter: %s", category_name)
            continue

        search_terms = category_config.get("search_terms", [])
        vendors = category_config.get("vendors", [])

        for vendor_name in vendors:
            if only_vendors and vendor_name not in only_vendors:
                logger.debug(
                    "Skipping vendor due to vendor filter: category=%s vendor=%s",
                    category_name,
                    vendor_name,
                )
                continue

            if vendor_name not in VENDOR_REGISTRY:
                logger.warning("Skipping unsupported vendor: %s", vendor_name)
                continue

            specific_products = get_specific_products_for_vendor(
                category_config=category_config,
                vendor_name=vendor_name,
            )

            logger.info(
                "Selected fetch target: category=%s vendor=%s search_terms=%s specific_products=%s",
                category_name,
                vendor_name,
                len(search_terms),
                len(specific_products),
            )

            if dry_run:
                logger.info(
                    "Dry run enabled. Skipping API call: category=%s vendor=%s",
                    category_name,
                    vendor_name,
                )
                continue

            vendor_class = VENDOR_REGISTRY[vendor_name]
            vendor = vendor_class()

            vendor_records = vendor.fetch_category_prices(
                category=category_name,
                search_terms=search_terms,
                specific_products=specific_products,
            )

            logger.info(
                "Fetched vendor records: category=%s vendor=%s records=%s",
                category_name,
                vendor_name,
                len(vendor_records),
            )

            filtered_vendor_records = filter_records_for_category(
                records=vendor_records,
                category_config=category_config,
            )

            logger.info(
                "Kept vendor records after filtering: category=%s vendor=%s records=%s",
                category_name,
                vendor_name,
                len(filtered_vendor_records),
            )

            records.extend(filtered_vendor_records)

    return records


def update_price_history(records: list[PriceRecord]) -> None:
    existing = pd.read_csv(PRICE_HISTORY_PATH, dtype={"product_id": str})

    new_rows = pd.DataFrame(
        [record.to_price_history_row() for record in records],
        columns=PRICE_HISTORY_COLUMNS,
    )

    if new_rows.empty:
        logger.warning("No new rows supplied to update_price_history")
        return

    new_rows["product_id"] = new_rows["product_id"].astype(str)

    combined = pd.concat([existing, new_rows], ignore_index=True)

    before_dedup = len(combined)

    combined = combined.drop_duplicates(
        subset=["date", "product_id", "vendor", "category"],
        keep="last",
    )

    duplicates_removed = before_dedup - len(combined)

    combined = combined.sort_values(
        by=["date", "vendor", "category", "product_id"],
    )

    combined.to_csv(PRICE_HISTORY_PATH, index=False)

    logger.info(
        "Updated price history: new_rows=%s total_rows=%s duplicates_removed=%s output=%s",
        len(new_rows),
        len(combined),
        duplicates_removed,
        PRICE_HISTORY_PATH,
    )


def update_products_registry(records: list[PriceRecord]) -> None:
    existing = pd.read_csv(PRODUCTS_PATH, dtype={"product_id": str})

    new_rows = pd.DataFrame(
        [record.to_product_row() for record in records],
        columns=PRODUCTS_COLUMNS,
    )

    if new_rows.empty:
        logger.warning("No new rows supplied to update_products_registry")
        return

    new_rows["product_id"] = new_rows["product_id"].astype(str)

    combined = pd.concat([existing, new_rows], ignore_index=True)

    before_dedup = len(combined)

    combined = combined.drop_duplicates(
        subset=["product_id", "vendor"],
        keep="last",
    )

    duplicates_removed = before_dedup - len(combined)

    combined = combined.sort_values(
        by=["vendor", "category", "product_name"],
    )

    combined.to_csv(PRODUCTS_PATH, index=False)

    logger.info(
        "Updated products registry: new_rows=%s total_rows=%s duplicates_removed=%s output=%s",
        len(new_rows),
        len(combined),
        duplicates_removed,
        PRODUCTS_PATH,
    )


def run_fetch_prices(
    products_config: dict | None = None,
    only_vendors: set[str] | None = None,
    only_categories: set[str] | None = None,
    dry_run: bool = False,
) -> list[PriceRecord]:
    ensure_data_files()

    if products_config is None:
        products_config = load_products_config()

    logger.info(
        "Starting fetch prices: only_vendors=%s only_categories=%s dry_run=%s",
        sorted(only_vendors) if only_vendors else None,
        sorted(only_categories) if only_categories else None,
        dry_run,
    )

    records = fetch_all_prices(
        products_config=products_config,
        only_vendors=only_vendors,
        only_categories=only_categories,
        dry_run=dry_run,
    )

    if dry_run:
        logger.info("Dry run complete. No vendor API calls were made.")
        return []

    if not records:
        logger.warning("No price records fetched after filtering.")
        return []

    update_price_history(records)
    update_products_registry(records)

    logger.info("Fetch prices complete: records=%s", len(records))

    return records


if __name__ == "__main__":
    from price_bot.env import load_environment

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    load_environment()
    run_fetch_prices()
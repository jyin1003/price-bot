import argparse
import logging

from env import load_environment
from setup import VENDOR_REGISTRY, load_products_config
from tools.fetch_prices import run_fetch_prices
from tools.price_tracker import update_product_metrics, update_product_metrics_from_latest_history


def configure_logging(debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Price Bot - fetch and track product prices."
    )

    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Do not call vendor APIs. Useful for checking selected vendors/categories.",
    )

    parser.add_argument(
        "--vendors",
        nargs="+",
        choices=sorted(VENDOR_REGISTRY.keys()),
        help="Only fetch from specific vendors. Example: --vendors coles woolworths",
    )

    parser.add_argument(
        "--categories",
        nargs="+",
        help="Only fetch specific categories from products.yaml. Example: --categories tissue toilet_paper",
    )

    parser.add_argument(
        "--list-config",
        action="store_true",
        help="List available categories and vendors from products.yaml, then exit.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )

    return parser.parse_args()


def list_config(products_config: dict) -> None:
    categories = products_config.get("categories", {})

    print("\nAvailable categories:")
    for category_name, category_config in categories.items():
        vendors = category_config.get("vendors", [])
        search_terms = category_config.get("search_terms", [])

        print(
            f"  - {category_name} "
            f"(vendors={', '.join(vendors)}, search_terms={len(search_terms)})"
        )

    print("\nSupported vendors:")
    for vendor_name in sorted(VENDOR_REGISTRY.keys()):
        print(f"  - {vendor_name}")


def validate_category_filters(
    products_config: dict,
    requested_categories: set[str] | None,
) -> None:
    if not requested_categories:
        return

    available_categories = set(products_config.get("categories", {}).keys())
    unknown_categories = requested_categories - available_categories

    if unknown_categories:
        raise ValueError(
            "Unknown categories requested: "
            f"{sorted(unknown_categories)}. "
            f"Available categories: {sorted(available_categories)}"
        )


def main() -> None:
    args = parse_args()

    configure_logging(debug=args.debug)

    logger = logging.getLogger(__name__)

    load_environment()

    products_config = load_products_config()

    if args.list_config:
        list_config(products_config)
        return

    only_vendors = set(args.vendors) if args.vendors else None
    only_categories = set(args.categories) if args.categories else None

    validate_category_filters(
        products_config=products_config,
        requested_categories=only_categories,
    )

    logger.info("Starting Price Bot")

    logger.info("Fetching current prices")
    records = run_fetch_prices(
        products_config=products_config,
        only_vendors=only_vendors,
        only_categories=only_categories,
        dry_run=args.no_fetch,
    )
    
    if records:
        logger.info("Updating metrics from freshly fetched records")
        update_product_metrics(records)
    else:
        logger.info(
            "No fresh records available. Updating metrics from latest price history rows."
        )
        update_product_metrics_from_latest_history()

    logger.info("Price Bot complete")


if __name__ == "__main__":
    main()
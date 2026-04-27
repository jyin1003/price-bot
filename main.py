import logging

from env import load_environment
from tools.fetch_prices import run_fetch_prices
from tools.price_tracker import update_product_metrics

def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    configure_logging()
    load_environment()

    # Update current prices and metrics
    run_fetch_prices()
    update_product_metrics()


if __name__ == "__main__":
    main()
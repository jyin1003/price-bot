import logging

from env import load_environment
from tools.fetch_prices import run_fetch_prices

def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    configure_logging()
    load_environment()

    # Update current prices
    run_fetch_prices()


if __name__ == "__main__":
    main()
from pathlib import Path

# /price-bot/price_bot
PACKAGE_DIR = Path(__file__).resolve().parent

# /price-bot
BASE_DIR = PACKAGE_DIR.parent

# /price-bot/data
DATA_DIR = BASE_DIR / "data"

PRICE_HISTORY_PATH = DATA_DIR / "price_history.csv"
PRODUCTS_PATH = DATA_DIR / "products.csv"
PRODUCT_METRICS_PATH = DATA_DIR / "product_metrics.csv"
GROUPED_PRODUCT_METRICS_PATH = DATA_DIR / "grouped_product_metrics.csv"

PRODUCTS_YAML_PATH = PACKAGE_DIR / "products.yaml"

PRODUCT_MATCH_PATH = DATA_DIR / "product_match.csv"

# Query Constants
COLES_MAX_PAGES = 5
COLES_LIMIT = 100
WOOLWORTHS_MAX_PAGES = 50
WOOLWORTHS_PAGE_SIZE = 20

# Product matching
MATCH_MIN_SCORE = 70
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent

DATA_DIR = BASE_DIR / "data"
PROJECT_DIR = BASE_DIR / "price_bot"

PRICE_HISTORY_PATH = DATA_DIR / "price_history.csv"
PRODUCTS_PATH = DATA_DIR / "products.csv"
PRODUCT_METRICS_PATH = DATA_DIR / "product_metrics.csv"

PRODUCTS_YAML_PATH = PROJECT_DIR / "products.yaml"

# Query Constants
COLES_MAX_PAGES = 5
COLES_LIMIT = 100
WOOLWORTHS_MAX_PAGES = 50
WOOLWORTHS_PAGE_SIZE = 20
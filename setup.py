import yaml
from pathlib import Path

from vendors.coles import ColesVendor
from vendors.woolworths import WoolworthsVendor

from config import PRODUCTS_YAML_PATH

VENDOR_REGISTRY = {
    "coles": ColesVendor,
    "woolworths": WoolworthsVendor,
}

def load_products_config(path: Path = PRODUCTS_YAML_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
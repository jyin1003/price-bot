from vendors.coles import ColesVendor

VENDOR_REGISTRY = {
    "coles": ColesVendor,
}

# overwrite row if it has the same date (same day collection)

# example use of vendors
# records = vendor.fetch_category_prices(
#     category=category_name,
#     search_terms=category_config.get("search_terms", []),
#     specific_products=category_config.get("specific_products", []),
# )
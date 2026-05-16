# Price Bot

## Overview
Price Bot tracks price changes for specified products across multiple vendors. It retrieves current prices, compares them to historical highs, and outputs a summary of vendors, current prices, and price changes.

## Setup
```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Usage
Run the full workflow for all configured vendors and categories:

```powershell
python main.py
````

Run without making vendor API calls. Useful for checking config selection before spending API requests:

```powershell
python main.py --no-fetch
```

Fetch only from specific vendors:

```powershell
python main.py --vendors coles
```

Fetch only specific categories from `products.yaml`:

```powershell
python main.py --categories tissue toilet_paper
```

Fetch only specific vendors and categories:

```powershell
python main.py --vendors coles --categories tissue
```

List available categories and supported vendors, then exit:

```powershell
python main.py --list-config
```

Enable detailed debug logging:

```powershell
python main.py --debug
```

Run fuzzy cross-vendor product name matching that edits `product_match.csv`:

```powershell
python main.py --match-products
```

| Argument        | Purpose                                                                        |
| --------------- | ------------------------------------------------------------------------------ |
| `--no-fetch` | Skips vendor API calls but still refreshes metrics from existing `price_history.` |
| `--vendors`     | Limits the run to one or more vendors, e.g. `coles`, `woolworths`              |
| `--categories`  | Limits the run to one or more categories defined in `products.yaml`            |
| `--list-config` | Prints available categories and supported vendors, then exits                  |
| `--debug`       | Enables detailed debug-level logging                                           |
| `--match-products` | Runs fuzzy cross-vendor product name matching from `products.csv` without making vendor API calls |


## Data Sources & Update Frequency

| Vendor | Category | Update Frequency |
|--------|----------|------------------|
| Woolworths | Supermarket | Weekly (Thursday) |
| Coles | Supermarket | Weekly (Thursday) |
| Chemist Warehouse | Pharmacy / Health Retail | Fortnightly (Saturday) |
| Skin Seoul | Pharmacy / Health Retail | Fortnightly (Saturday) |

## Project Structure

```text
price-bot/
├── tools/
│   ├── fetch_prices.py
│   ├── price_tracker.py
│   ├── product_matcher.py
│   └── terminal_output.py
├── vendors/
│   ├── chemist_warehouse.py
│   ├── coles.py
│   └── woolworths.py
├── data/
│   ├── model.py
│   ├── price_history.csv
│   ├── products.csv
│   ├── product_match.csv
│   └── product_metrics.csv
├── price_bot/
│   ├── config.py
│   ├── env.py
│   └── products.yaml
├── .env
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

| Key Files           | Purpose                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `main.py`           | Runs the full price tracking workflow                               |
| `config.py`         | Stores non-secret settings such as file paths and supported vendors |
| `env.py`            | Loads API keys and environment variables from `.env`                |
| `products.yaml`     | Defines the products/categories to track                            |
| `price_history.csv` | Stores historical price records                                     |
| `requirements.txt`  | Python dependencies                                                 |
| `.env`              | Stores API keys and secrets                                         |
| `tools/fetch_prices.py`    | Coordinates API calls across vendors              |
| `tools/price_tracker.py`   | Compares current prices against historical prices |
| `tools/output.py` | Displays results in the terminal          |

## Data Architecture

The project uses a **three-layer data model**.

### `price_history.csv` (Source of Truth)
- Stores all observed prices over time.
- Append-only (never overwrite)
- Schema: `date,product_id,vendor,category,price`

Example
```
2026-04-27,5118857,woolworths,tissue,3.50
2026-04-27,893221,coles,tissue,3.20
```

### `products.csv` (Product Registry)

- Tracks all discovered products across vendors.
- Updated when new products are found via search or specified directly
- Schema: `product_id,vendor,product_name,category,source,last_seen`

Example:
```
5118857,woolworths,Kleenex 120 Pack,tissue,specific,2026-04-27
893221,coles,Coles Soft Tissue,tissue,search,2026-04-27
```

### `product_metrics.csv` (Derived Metrics)

- Stores computed statistics for each product.
- Updated after each run
- Used for fast lookups and output formatting
- Schema: `product_id,vendor,max_price,min_price,last_updated`

Example
```
5118857,woolworths,5.00,3.20,2026-04-27
893221,coles,4.50,3.00,2026-04-27
```

### `product_match.csv` (Cross-Vendor Product Matching)

- Stores product groupings across vendors.
- Used to compare equivalent or near-equivalent products sold by different vendors.
- Generated from fuzzy matching on `products.csv`.
- Should be manually reviewed before being treated as final.
- Schema: `group_id,group_name,category,product_id,vendor,product_name`

## Product Tracking Format

Products are defined in `products.yaml` using a **category-based structure**. This allows you to track both broad product groups and specific items within those groups.

```yaml
categories:
  <category_name>:
    search_terms: [list of keywords]
    vendors: [list of vendors]
    specific_products:
        [vendor]:
            [list of product IDs or slugs for that vendor]

```
| Field               | Description                                                    |
| ------------------- | -------------------------------------------------------------- |
| `categories`        | Top-level grouping of all tracked items                        |
| `<category_name>`   | A logical grouping (e.g. `tissue`, `milk`, `pain_relief`)      |
| `search_terms`      | Keywords used to query vendor APIs for broad matching products |
| `vendors`           | Vendors where this category should be tracked                  |
| `specific_products` | Exact product identifiers (IDs/slugs) per vendor for precise tracking     |


## Future Improvements
- Add scheduled weekly/fortnightly runs
- Add dashboard UI
- Add vendor-specific update frequencies
- Add product matching logic across different vendor naming conventions
- Add health metric to see if any product names for the same product id has changed or vice versa for a vendor
- Add unit pricing logic to compare
- Add favourites to categories
- Add cheapest for category seen across vendors (plumb fuzzy name matching)
- product metrics show full price if at max price and then cheapest if at min
- add cotton buds, saline
- w cosmetics
- paula's choice
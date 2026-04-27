# Price Bot

## Overview
Price Bot tracks price changes for specified products across multiple vendors. It retrieves current prices, compares them to historical highs, and outputs a summary of vendors, current prices, and price changes.

## Usage
```
pip install -r requirements.txt
python main.py
```

## Data Sources & Update Frequency

| Vendor | Category | Update Frequency |
|--------|----------|------------------|
| Woolworths | Supermarket | Weekly (Thursday) |
| Coles | Supermarket | Weekly (Thursday) |
| Chemist Warehouse | Pharmacy / Health Retail | Fortnightly (Saturday) |

## Project Structure

```text
price-bot/
├── tools/
│   ├── fetch_prices.py
│   ├── price_tracker.py
│   └── terminal_output.py
├── vendors/
│   ├── chemist_warehouse.py
│   ├── coles.py
│   └── woolworths.py
├── .env
├── .gitignore
├── config.py
├── env.py
├── main.py
├── price_history.csv
├── products.yaml
├── README.md
└── requirements.txt
```

| File                | Purpose                                                             |
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
| `tools/terminal_output.py` | Prints the final results in the terminal          |

## Product Tracking Format

Products are defined in `products.yaml` using a **category-based structure**. This allows you to track both broad product groups and specific items within those groups.

### General Structure

```yaml
categories:
  <category_name>:
    search_terms: [list of keywords]
    specific_products: [list of product IDs or slugs]
    vendors: [list of vendors]
```
| Field               | Description                                                    |
| ------------------- | -------------------------------------------------------------- |
| `categories`        | Top-level grouping of all tracked items                        |
| `<category_name>`   | A logical grouping (e.g. `tissue`, `milk`, `pain_relief`)      |
| `search_terms`      | Keywords used to query vendor APIs for broad matching products |
| `specific_products` | Exact product identifiers (IDs/slugs) for precise tracking     |
| `vendors`           | Vendors where this category should be tracked                  |


## Planned Flow
```
products.yaml
      ↓
main.py
      ↓
fetch current prices
      ↓
append to price_history.csv
      ↓
compare against historical highs/lows
      ↓
print terminal output
```

## Future Improvements
- Add scheduled weekly/fortnightly runs
- Add dashboard UI
- Add vendor-specific update frequencies
- Add product matching logic across different vendor naming conventions
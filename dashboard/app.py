from flask import Flask, render_template, jsonify, abort
import pandas as pd
from pathlib import Path

app = Flask(__name__)

# ── Path config ──────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

PRICE_HISTORY_PATH   = DATA_DIR / "price_history.csv"
PRODUCTS_PATH        = DATA_DIR / "products.csv"
PRODUCT_MATCH_PATH   = DATA_DIR / "product_match.csv"
PRODUCT_METRICS_PATH = DATA_DIR / "product_metrics.csv"
GROUPED_METRICS_PATH = DATA_DIR / "grouped_product_metrics.csv"


# ── Data loaders ───────────────────────────────────────────────────────────

def load_csv(path, dtype=None):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=dtype)
    except Exception:
        return pd.DataFrame()


def get_price_history():
    df = load_csv(PRICE_HISTORY_PATH, dtype={"product_id": str})
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df.dropna(subset=["date", "price"])


def get_latest_price_per_product(history_df):
    """Return the most recent price for each (product_id, vendor)."""
    if history_df.empty:
        return pd.DataFrame()
    return (
        history_df
        .sort_values("date")
        .groupby(["product_id", "vendor"], as_index=False)
        .last()
        .rename(columns={"price": "current_price", "date": "last_seen_date"})
    )


def get_history_for_product(history_df, product_id, vendor):
    """Return sorted history rows for one product."""
    mask = (history_df["product_id"].astype(str) == str(product_id)) & \
           (history_df["vendor"] == vendor)
    sub = history_df[mask].sort_values("date")
    return [
        {"date": row["date"].strftime("%Y-%m-%d"), "price": float(row["price"])}
        for _, row in sub.iterrows()
    ]


def build_dashboard_data():
    """Build all data needed for both pages."""
    history_df   = get_price_history()
    match_df     = load_csv(PRODUCT_MATCH_PATH, dtype={"product_id": str, "group_id": int})
    metrics_df   = load_csv(PRODUCT_METRICS_PATH, dtype={"product_id": str})
    grouped_df   = load_csv(GROUPED_METRICS_PATH)
    products_df  = load_csv(PRODUCTS_PATH, dtype={"product_id": str})

    if history_df.empty or match_df.empty or grouped_df.empty:
        return {}

    latest = get_latest_price_per_product(history_df)

    # Per-product metrics lookup
    metrics_lookup = {}
    if not metrics_df.empty:
        metrics_df["product_id"] = metrics_df["product_id"].astype(str)
        for _, row in metrics_df.iterrows():
            key = (str(row["product_id"]), str(row["vendor"]))
            metrics_lookup[key] = {
                "max_price": float(row["max_price"]) if pd.notna(row.get("max_price")) else None,
                "min_price": float(row["min_price"]) if pd.notna(row.get("min_price")) else None,
                "last_updated": str(row.get("last_updated", "")),
            }

    # Products name lookup
    products_lookup = {}
    if not products_df.empty:
        for _, row in products_df.iterrows():
            key = (str(row["product_id"]), str(row["vendor"]))
            products_lookup[key] = str(row.get("product_name", ""))

    # Latest price lookup
    latest_lookup = {}
    if not latest.empty:
        latest["product_id"] = latest["product_id"].astype(str)
        for _, row in latest.iterrows():
            key = (str(row["product_id"]), str(row["vendor"]))
            latest_lookup[key] = {
                "current_price": float(row["current_price"]),
                "last_seen_date": row["last_seen_date"].strftime("%Y-%m-%d") if pd.notna(row["last_seen_date"]) else "",
            }

    # Build group members
    match_df["product_id"] = match_df["product_id"].astype(str)
    group_members = {}
    for _, row in match_df.iterrows():
        gid = int(row["group_id"])
        key = (str(row["product_id"]), str(row["vendor"]))
        lp = latest_lookup.get(key, {})
        m  = metrics_lookup.get(key, {})
        member = {
            "product_id": str(row["product_id"]),
            "vendor": str(row["vendor"]),
            "product_name": str(row.get("product_name", products_lookup.get(key, ""))),
            "current_price": lp.get("current_price"),
            "last_seen_date": lp.get("last_seen_date", ""),
            "max_price": m.get("max_price"),
            "min_price": m.get("min_price"),
            "last_updated": m.get("last_updated", ""),
        }
        group_members.setdefault(gid, []).append(member)

    # Build groups keyed by category
    grouped_df["group_id"] = grouped_df["group_id"].astype(int)
    grouped_df["max_price"] = pd.to_numeric(grouped_df["max_price"], errors="coerce")
    grouped_df["min_price"] = pd.to_numeric(grouped_df["min_price"], errors="coerce")

    categories = {}
    for _, grow in grouped_df.iterrows():
        gid      = int(grow["group_id"])
        category = str(grow["category"])
        members  = group_members.get(gid, [])
        is_multi = len(members) > 1

        # best current price = cheapest member with a price
        priced = [m for m in members if m["current_price"] is not None]
        if not priced:
            continue
        best = min(priced, key=lambda m: m["current_price"])

        group_max = float(grow["max_price"]) if pd.notna(grow.get("max_price")) else None
        group_min = float(grow["min_price"]) if pd.notna(grow.get("min_price")) else None
        current   = float(best["current_price"])

        discount = 0.0
        if group_max and group_max > 0:
            discount = round(max(0, (group_max - current) / group_max * 100), 1)

        if group_max and current == group_max:
            status = "full price"
        elif group_min and current == group_min:
            status = "cheapest"
        else:
            status = "discounted"

        last_updated = str(grow.get("last_updated", ""))

        group_obj = {
            "group_id": gid,
            "group_name": str(grow["group_name"]),
            "category": category,
            "current_price": current,
            "best_vendor": best["vendor"],
            "discount": discount,
            "status": status,
            "group_max_price": group_max,
            "group_min_price": group_min,
            "last_updated": last_updated,
            "is_multi": is_multi,
            "members": sorted(members, key=lambda m: (m["current_price"] or 999, m["vendor"])),
        }

        categories.setdefault(category, []).append(group_obj)

    # Sort each category's groups and compute top lists
    result = {}
    for cat, groups in categories.items():
        sorted_cheapest    = sorted(groups, key=lambda g: (g["current_price"], g["group_name"]))
        sorted_discounted  = sorted(groups, key=lambda g: (-g["discount"], g["current_price"], g["group_name"]))
        sorted_alpha       = sorted(groups, key=lambda g: g["group_name"].lower())

        result[cat] = {
            "category": cat,
            "slug": cat,
            "all_groups": sorted_alpha,
            "top5_cheapest": sorted_cheapest[:5],
            "top5_discounted": sorted_discounted[:5],
        }

    return result


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    data = build_dashboard_data()
    return render_template("index.html", categories=data)


@app.route("/category/<slug>")
def category_page(slug):
    data = build_dashboard_data()
    if slug not in data:
        abort(404)
    return render_template("category.html", cat=data[slug], all_categories=list(data.keys()))


@app.route("/api/product_history/<vendor>/<product_id>")
def product_history(vendor, product_id):
    history_df = get_price_history()
    rows = get_history_for_product(history_df, product_id, vendor)
    return jsonify(rows)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
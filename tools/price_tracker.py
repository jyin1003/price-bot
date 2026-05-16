from pathlib import Path
import logging

import pandas as pd

from price_bot.config import (
    PRODUCT_METRICS_PATH,
    PRICE_HISTORY_PATH,
    PRODUCTS_PATH,
    GROUPED_PRODUCT_METRICS_PATH,
    PRODUCT_MATCH_PATH,
)
from data.model import (
    PRICE_HISTORY_COLUMNS,
    METRIC_COLUMNS,
    GROUPED_PRODUCT_METRICS_COLUMNS,
    GroupPriceAnalysis,
    CategoryPriceAnalysis,
    PriceStatus,
)

logger = logging.getLogger(__name__)


def _empty_metrics_df() -> pd.DataFrame:
    return pd.DataFrame(columns=METRIC_COLUMNS)


def _load_existing_metrics(product_metrics_path: Path) -> pd.DataFrame:
    """
    Load product_metrics.csv if it exists and has content.
    """

    if not product_metrics_path.exists():
        logger.info(
            "Product metrics file does not exist yet. A new one will be created: %s",
            product_metrics_path,
        )
        return _empty_metrics_df()

    try:
        metrics = pd.read_csv(product_metrics_path)
    except pd.errors.EmptyDataError:
        logger.warning(
            "Product metrics file exists but is completely empty. Rebuilding: %s",
            product_metrics_path,
        )
        return _empty_metrics_df()

    if metrics.empty:
        logger.info(
            "Product metrics file has headers but no rows: %s",
            product_metrics_path,
        )
        return _empty_metrics_df()

    missing_columns = set(METRIC_COLUMNS) - set(metrics.columns)
    if missing_columns:
        raise ValueError(
            f"product_metrics.csv is missing required columns: {sorted(missing_columns)}"
        )

    metrics = metrics[METRIC_COLUMNS].copy()
    metrics["product_id"] = metrics["product_id"].astype(str)
    metrics["vendor"] = metrics["vendor"].astype(str)
    metrics["max_price"] = pd.to_numeric(metrics["max_price"], errors="coerce")
    metrics["min_price"] = pd.to_numeric(metrics["min_price"], errors="coerce")

    return metrics


def _calculate_status(
    current_price: float,
    min_price: float,
    max_price: float,
) -> PriceStatus:

    if current_price == min_price:
        return "cheapest"
    if current_price == max_price:
        return "full price"
    return "discounted"


def _rows_to_group_analysis(df: pd.DataFrame) -> list[GroupPriceAnalysis]:
    return [
        GroupPriceAnalysis(
            group_id=int(row.group_id),
            group_name=str(row.group_name),
            current_price=float(row.current_price),
            best_vendor=str(row.best_vendor),
            category=str(row.category),
            discount=float(row.discount),
            status=row.status,
        )
        for row in df.itertuples(index=False)
    ]


def update_product_metrics_from_latest_history(
    price_history_path: Path = PRICE_HISTORY_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
) -> None:
    """
    Update product_metrics.csv using only the latest-dated rows
    currently stored in price_history.csv.
    """

    logger.info("Starting metrics update from latest price history rows")

    if not price_history_path.exists():
        logger.warning(
            "Price history file does not exist. Skipping metrics update: %s",
            price_history_path,
        )
        return

    try:
        price_history = pd.read_csv(price_history_path, dtype={"product_id": str})
    except pd.errors.EmptyDataError:
        logger.warning(
            "Price history file is completely empty. Skipping metrics update: %s",
            price_history_path,
        )
        return

    if price_history.empty:
        logger.warning(
            "Price history file has headers but no rows. Skipping metrics update: %s",
            price_history_path,
        )
        return

    missing_columns = set(PRICE_HISTORY_COLUMNS) - set(price_history.columns)
    if missing_columns:
        raise ValueError(
            f"price_history.csv is missing required columns: {sorted(missing_columns)}"
        )

    price_history = price_history[PRICE_HISTORY_COLUMNS].copy()
    price_history["date"] = pd.to_datetime(price_history["date"], errors="coerce")

    invalid_date_rows = price_history["date"].isna().sum()
    if invalid_date_rows:
        logger.warning(
            "Dropping price history rows with invalid dates: rows=%s", invalid_date_rows
        )

    price_history = price_history.dropna(subset=["date"])

    if price_history.empty:
        logger.warning("No valid dated rows found in price_history.csv")
        return

    latest_date = price_history["date"].max()
    latest_rows = price_history[price_history["date"] == latest_date].copy()
    latest_rows["date"] = latest_rows["date"].dt.strftime("%Y-%m-%d")

    logger.info(
        "Loaded latest price history rows for metrics update: latest_date=%s rows=%s",
        latest_date.strftime("%Y-%m-%d"),
        len(latest_rows),
    )

    update_product_metrics(
        latest_prices=latest_rows,
        product_metrics_path=product_metrics_path,
    )


def update_product_metrics(
    latest_prices: list[dict] | pd.DataFrame,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
) -> None:
    """
    Update product_metrics.csv using only the latest fetched price records,
    then rebuild grouped_product_metrics.csv.
    """

    logger.info("Starting product metrics update")

    product_metrics_path.parent.mkdir(parents=True, exist_ok=True)

    latest_df = pd.DataFrame(latest_prices)

    if latest_df.empty:
        logger.warning("No latest price records provided. Skipping metrics update.")
        return

    missing_latest_columns = set(PRICE_HISTORY_COLUMNS) - set(latest_df.columns)
    if missing_latest_columns:
        raise ValueError(
            f"latest price records are missing required columns: {sorted(missing_latest_columns)}"
        )

    latest_df = latest_df[PRICE_HISTORY_COLUMNS].copy()
    latest_df["product_id"] = latest_df["product_id"].astype(str)
    latest_df["vendor"] = latest_df["vendor"].astype(str)
    latest_df["date"] = pd.to_datetime(latest_df["date"], errors="coerce")
    latest_df["price"] = pd.to_numeric(latest_df["price"], errors="coerce")

    invalid_latest_rows = latest_df[
        latest_df["date"].isna()
        | latest_df["price"].isna()
        | latest_df["product_id"].isna()
        | latest_df["vendor"].isna()
    ]
    if not invalid_latest_rows.empty:
        logger.warning(
            "Dropping invalid latest price rows before metrics update: rows=%s",
            len(invalid_latest_rows),
        )

    latest_df = latest_df.dropna(subset=["date", "price", "product_id", "vendor"])

    if latest_df.empty:
        logger.warning("No valid latest price rows remain. Skipping metrics update.")
        return

    logger.info(
        "Loaded latest price records for metrics update: rows=%s unique_products=%s vendors=%s",
        len(latest_df),
        latest_df["product_id"].nunique(),
        sorted(latest_df["vendor"].dropna().unique().tolist()),
    )

    latest_metrics = (
        latest_df
        .groupby(["product_id", "vendor"], as_index=False)
        .agg(
            latest_max_price=("price", "max"),
            latest_min_price=("price", "min"),
            latest_seen=("date", "max"),
        )
    )

    existing_metrics = _load_existing_metrics(product_metrics_path)

    if existing_metrics.empty:
        logger.info("No existing metrics found. Initialising metrics from latest records.")
        new_metrics = latest_metrics.rename(columns={
            "latest_max_price": "max_price",
            "latest_min_price": "min_price",
            "latest_seen": "last_updated",
        })
        new_metrics["last_updated"] = new_metrics["last_updated"].dt.strftime("%Y-%m-%d")
        new_metrics = new_metrics[METRIC_COLUMNS]
        new_metrics.to_csv(product_metrics_path, index=False)
        logger.info(
            "Product metrics initialised: rows=%s output=%s",
            len(new_metrics),
            product_metrics_path,
        )
    else:
        merged = existing_metrics.merge(
            latest_metrics, on=["product_id", "vendor"], how="outer"
        )
        merged["max_price"] = merged[["max_price", "latest_max_price"]].max(axis=1)
        merged["min_price"] = merged[["min_price", "latest_min_price"]].min(axis=1)
        merged["last_updated"] = pd.to_datetime(merged["last_updated"], errors="coerce")
        merged["last_updated"] = merged[["last_updated", "latest_seen"]].max(axis=1)

        updated_metrics = merged[
            ["product_id", "vendor", "max_price", "min_price", "last_updated"]
        ].copy()
        updated_metrics["last_updated"] = updated_metrics["last_updated"].dt.strftime("%Y-%m-%d")
        updated_metrics = updated_metrics.sort_values(["vendor", "product_id"])
        updated_metrics.to_csv(product_metrics_path, index=False)

        logger.info(
            "Product metrics updated: existing_rows=%s latest_product_rows=%s final_rows=%s output=%s",
            len(existing_metrics),
            len(latest_metrics),
            len(updated_metrics),
            product_metrics_path,
        )

    # Always rebuild grouped metrics after any product_metrics update
    _refresh_grouped_metrics()


def _refresh_grouped_metrics(
    product_match_path: Path = PRODUCT_MATCH_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
    output_path: Path = GROUPED_PRODUCT_METRICS_PATH,
) -> None:
    """
    Rebuild grouped_product_metrics.csv by joining product_match.csv against
    the freshly updated product_metrics.csv and aggregating per group.

    Per group:
      max_price    -> max of all member max_prices
      min_price    -> min of all member min_prices
      last_updated -> most recent last_updated across members
    """
    if not product_match_path.exists():
        logger.warning(
            "product_match.csv does not exist yet. Skipping grouped metrics rebuild. "
            "Run --match-products or allow the pipeline to trigger matching first."
        )
        return

    if not product_metrics_path.exists():
        logger.warning(
            "product_metrics.csv does not exist yet. Skipping grouped metrics rebuild."
        )
        return

    try:
        from tools.product_matcher import _load_product_match
        match_df = _load_product_match(product_match_path)
    except Exception:
        logger.warning("Could not load product_match.csv. Skipping grouped metrics rebuild.", exc_info=True)
        return

    if match_df.empty:
        logger.warning("product_match.csv is empty. Skipping grouped metrics rebuild.")
        return

    metrics = pd.read_csv(product_metrics_path, dtype={"product_id": str})
    missing = set(METRIC_COLUMNS) - set(metrics.columns)
    if missing:
        raise ValueError(f"product_metrics.csv is missing columns: {sorted(missing)}")

    metrics["product_id"] = metrics["product_id"].astype(str)
    metrics["vendor"] = metrics["vendor"].astype(str)
    metrics["max_price"] = pd.to_numeric(metrics["max_price"], errors="coerce")
    metrics["min_price"] = pd.to_numeric(metrics["min_price"], errors="coerce")
    metrics["last_updated"] = pd.to_datetime(metrics["last_updated"], errors="coerce")

    merged = match_df.merge(
        metrics[["product_id", "vendor", "max_price", "min_price", "last_updated"]],
        on=["product_id", "vendor"],
        how="left",
    )

    grouped = (
        merged.groupby(["group_id", "group_name", "category"], as_index=False)
        .agg(
            max_price=("max_price", "max"),
            min_price=("min_price", "min"),
            last_updated=("last_updated", "max"),
        )
    )

    grouped["last_updated"] = grouped["last_updated"].dt.strftime("%Y-%m-%d")
    grouped = grouped.sort_values("group_id")[GROUPED_PRODUCT_METRICS_COLUMNS]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(output_path, index=False)

    logger.info(
        "Grouped product metrics rebuilt: groups=%s output=%s",
        len(grouped),
        output_path,
    )


def analyse_latest_prices_by_category(
    price_history_path: Path = PRICE_HISTORY_PATH,
    grouped_metrics_path: Path = GROUPED_PRODUCT_METRICS_PATH,
    product_match_path: Path = PRODUCT_MATCH_PATH,
) -> dict[str, CategoryPriceAnalysis]:
    """
    Analyse prices at the group level.

    For each group in grouped_product_metrics.csv:
      - Find the most recent price for each member in price_history.csv
      - The group's current price = cheapest of those most-recent member prices
      - The group's best_vendor = vendor of that cheapest member
      - discount = (group max_price - current_price) / group max_price * 100
      - status = cheapest / discounted / full price vs group max/min

    Groups are then compared against other groups within the same category.
    """
    for path in [price_history_path, grouped_metrics_path, product_match_path]:
        if not path.exists():
            raise FileNotFoundError(f"Required file does not exist: {path}")

    price_history = pd.read_csv(price_history_path, dtype={"product_id": str})
    grouped_metrics = pd.read_csv(grouped_metrics_path)
    match_df = pd.read_csv(product_match_path, dtype={"product_id": str, "group_id": int})

    # Validate columns
    missing_ph = set(PRICE_HISTORY_COLUMNS) - set(price_history.columns)
    if missing_ph:
        raise ValueError(f"price_history.csv is missing columns: {sorted(missing_ph)}")

    missing_gm = set(GROUPED_PRODUCT_METRICS_COLUMNS) - set(grouped_metrics.columns)
    if missing_gm:
        raise ValueError(f"grouped_product_metrics.csv is missing columns: {sorted(missing_gm)}")

    if price_history.empty:
        return {}

    # --- Step A: most recent price per (product_id, vendor) ---
    price_history["date"] = pd.to_datetime(price_history["date"], errors="coerce")
    price_history["price"] = pd.to_numeric(price_history["price"], errors="coerce")
    price_history = price_history.dropna(subset=["date", "price", "product_id", "vendor"])

    if price_history.empty:
        return {}

    # For each (product_id, vendor), keep only the row with the most recent date
    latest_per_product = (
        price_history
        .sort_values("date")
        .groupby(["product_id", "vendor"], as_index=False)
        .last()
        .rename(columns={"price": "current_price", "date": "last_seen_date"})
    )

    # --- Step B: join match groups to get (group_id, product_id, vendor, current_price) ---
    match_df["product_id"] = match_df["product_id"].astype(str)
    match_df["vendor"] = match_df["vendor"].astype(str)

    members_with_prices = match_df.merge(
        latest_per_product[["product_id", "vendor", "current_price", "last_seen_date"]],
        on=["product_id", "vendor"],
        how="left",
    )

    # --- Step C: per group, find the cheapest member (best current price) ---
    # Drop members with no price history at all
    members_with_prices = members_with_prices.dropna(subset=["current_price"])

    if members_with_prices.empty:
        return {}

    # For each group, pick the row with the lowest current_price.
    # Tie-break: most recent last_seen_date, then vendor name alphabetically.
    best_per_group = (
        members_with_prices
        .sort_values(
            ["group_id", "current_price", "last_seen_date", "vendor"],
            ascending=[True, True, False, True],
        )
        .groupby("group_id", as_index=False)
        .first()
        [["group_id", "vendor", "current_price"]]
        .rename(columns={"vendor": "best_vendor"})
    )

    # --- Step D: join grouped_metrics for max/min price reference ---
    grouped_metrics["group_id"] = grouped_metrics["group_id"].astype(int)
    grouped_metrics["max_price"] = pd.to_numeric(grouped_metrics["max_price"], errors="coerce")
    grouped_metrics["min_price"] = pd.to_numeric(grouped_metrics["min_price"], errors="coerce")

    analysis_df = grouped_metrics.merge(best_per_group, on="group_id", how="left")
    analysis_df = analysis_df.dropna(subset=["current_price", "max_price", "min_price"])
    analysis_df = analysis_df[analysis_df["max_price"] > 0].copy()

    # --- Step E: compute discount and status ---
    analysis_df["discount"] = (
        (
            (analysis_df["max_price"] - analysis_df["current_price"])
            / analysis_df["max_price"]
        )
        * 100
    ).clip(lower=0).round(1)

    analysis_df["status"] = analysis_df.apply(
        lambda row: _calculate_status(
            current_price=row["current_price"],
            min_price=row["min_price"],
            max_price=row["max_price"],
        ),
        axis=1,
    )

    # --- Step F: build CategoryPriceAnalysis per category ---
    analysis_by_category: dict[str, CategoryPriceAnalysis] = {}

    for category, category_df in analysis_df.groupby("category"):
        cheapest_sorted = category_df.sort_values(
            ["current_price", "group_name", "best_vendor"],
            ascending=[True, True, True],
        )
        discounted_sorted = category_df.sort_values(
            ["discount", "current_price", "group_name", "best_vendor"],
            ascending=[False, True, True, True],
        )

        all_groups = _rows_to_group_analysis(cheapest_sorted)

        cheapest_products = [g for g in all_groups if g.status == "cheapest"]

        top_five_cheapest = all_groups[:5]
        top_five_most_discounted = _rows_to_group_analysis(discounted_sorted.head(5))

        analysis_by_category[str(category)] = CategoryPriceAnalysis(
            category=str(category),
            cheapest_products=cheapest_products,
            top_five_cheapest=top_five_cheapest,
            top_five_most_discounted=top_five_most_discounted,
        )

    return analysis_by_category
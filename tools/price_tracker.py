from pathlib import Path
import logging

import pandas as pd

from config import PRODUCT_METRICS_PATH, PRICE_HISTORY_PATH
from data.model import PRICE_HISTORY_COLUMNS, METRIC_COLUMNS

logger = logging.getLogger(__name__)

def _empty_metrics_df() -> pd.DataFrame:
    return pd.DataFrame(columns=METRIC_COLUMNS)


def _load_existing_metrics(product_metrics_path: Path) -> pd.DataFrame:
    """
    Load product_metrics.csv if it exists and has content.

    Handles:
    - missing file
    - empty file
    - header-only file
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
            "Product metrics file exists but is completely empty. Rebuilding from latest records: %s",
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

    metrics["max_price"] = pd.to_numeric(
        metrics["max_price"],
        errors="coerce",
    )

    metrics["min_price"] = pd.to_numeric(
        metrics["min_price"],
        errors="coerce",
    )

    return metrics

def update_product_metrics_from_latest_history(
    price_history_path: Path = PRICE_HISTORY_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
) -> None:
    """
    Update product_metrics.csv using only the latest-dated rows
    currently stored in price_history.csv.

    This is useful for --no-fetch runs where no fresh API records exist,
    but you still want to refresh metrics from the latest available history.

    Note:
    This is not a full rebuild. If product_metrics.csv is empty, metrics
    will be initialised from the latest history rows only.
    """

    logger.info("Starting metrics update from latest price history rows")

    if not price_history_path.exists():
        logger.warning(
            "Price history file does not exist. Skipping metrics update: %s",
            price_history_path,
        )
        return

    try:
        price_history = pd.read_csv(
            price_history_path,
            dtype={"product_id": str},
        )
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

    price_history["date"] = pd.to_datetime(
        price_history["date"],
        errors="coerce",
    )

    invalid_date_rows = price_history["date"].isna().sum()

    if invalid_date_rows:
        logger.warning(
            "Dropping price history rows with invalid dates: rows=%s",
            invalid_date_rows,
        )

    price_history = price_history.dropna(subset=["date"])

    if price_history.empty:
        logger.warning("No valid dated rows found in price_history.csv")
        return

    latest_date = price_history["date"].max()

    latest_rows = price_history[
        price_history["date"] == latest_date
    ].copy()

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
    Update product_metrics.csv using only the latest fetched price records.
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

    latest_df["date"] = pd.to_datetime(
        latest_df["date"],
        errors="coerce",
    )

    latest_df["price"] = pd.to_numeric(
        latest_df["price"],
        errors="coerce",
    )

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

    latest_df = latest_df.dropna(
        subset=["date", "price", "product_id", "vendor"],
    )

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

        new_metrics = latest_metrics.rename(
            columns={
                "latest_max_price": "max_price",
                "latest_min_price": "min_price",
                "latest_seen": "last_updated",
            }
        )

        new_metrics["last_updated"] = new_metrics["last_updated"].dt.strftime("%Y-%m-%d")
        new_metrics = new_metrics[METRIC_COLUMNS]

        new_metrics.to_csv(product_metrics_path, index=False)

        logger.info(
            "Product metrics initialised: rows=%s output=%s",
            len(new_metrics),
            product_metrics_path,
        )
        return

    merged = existing_metrics.merge(
        latest_metrics,
        on=["product_id", "vendor"],
        how="outer",
    )

    merged["max_price"] = merged[["max_price", "latest_max_price"]].max(axis=1)
    merged["min_price"] = merged[["min_price", "latest_min_price"]].min(axis=1)

    merged["last_updated"] = pd.to_datetime(
        merged["last_updated"],
        errors="coerce",
    )

    merged["last_updated"] = merged[["last_updated", "latest_seen"]].max(axis=1)

    updated_metrics = merged[
        [
            "product_id",
            "vendor",
            "max_price",
            "min_price",
            "last_updated",
        ]
    ].copy()

    updated_metrics["last_updated"] = updated_metrics["last_updated"].dt.strftime("%Y-%m-%d")

    updated_metrics = updated_metrics.sort_values(
        ["vendor", "product_id"],
    )

    updated_metrics.to_csv(product_metrics_path, index=False)

    logger.info(
        "Product metrics updated: existing_rows=%s latest_product_rows=%s final_rows=%s output=%s",
        len(existing_metrics),
        len(latest_metrics),
        len(updated_metrics),
        product_metrics_path,
    )
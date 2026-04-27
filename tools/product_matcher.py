from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from price_bot.config import (
    PRODUCTS_PATH, 
    PRODUCT_MATCHES_PATH, 
    DATA_DIR, 
    PRODUCT_METRICS_PATH
)

from data.model import PRODUCT_MATCH_COLUMNS, ProductMatchCandidate


def normalise_product_name(name: str) -> str:
    name = name.lower()

    replacements = {
        "&": " and ",
        "-": " ",
        "/": " ",
        ",": " ",
        "(": " ",
        ")": " ",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    name = re.sub(r"\s+", " ", name)
    return name.strip()


def extract_product_attributes(name: str) -> dict:
    normalised = normalise_product_name(name)

    ply_match = re.search(r"\b(\d+)\s*ply\b", normalised)
    pack_match = re.search(r"\b(\d+)\s*(pack|pk|pcs|pieces)\b", normalised)
    size_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(g|kg|ml|l|m)\b", normalised)

    return {
        "ply": ply_match.group(1) if ply_match else None,
        "pack_count": pack_match.group(1) if pack_match else None,
        "size_value": size_match.group(1) if size_match else None,
        "size_unit": size_match.group(2) if size_match else None,
    }


def attribute_penalty(left_name: str, right_name: str) -> tuple[int, list[str]]:
    left_attrs = extract_product_attributes(left_name)
    right_attrs = extract_product_attributes(right_name)

    penalty = 0
    reasons = []

    if left_attrs["ply"] and right_attrs["ply"] and left_attrs["ply"] != right_attrs["ply"]:
        penalty += 25
        reasons.append(f"Different ply: {left_attrs['ply']} vs {right_attrs['ply']}")

    if (
        left_attrs["pack_count"]
        and right_attrs["pack_count"]
        and left_attrs["pack_count"] != right_attrs["pack_count"]
    ):
        penalty += 20
        reasons.append(
            f"Different pack count: {left_attrs['pack_count']} vs {right_attrs['pack_count']}"
        )

    if (
        left_attrs["size_value"]
        and right_attrs["size_value"]
        and left_attrs["size_unit"]
        and right_attrs["size_unit"]
        and (
            left_attrs["size_value"] != right_attrs["size_value"]
            or left_attrs["size_unit"] != right_attrs["size_unit"]
        )
    ):
        penalty += 20
        reasons.append(
            "Different size: "
            f"{left_attrs['size_value']}{left_attrs['size_unit']} vs "
            f"{right_attrs['size_value']}{right_attrs['size_unit']}"
        )

    return penalty, reasons

def calculate_price_score(
    left_max_price: float | None,
    right_max_price: float | None,
) -> tuple[float | None, str]:
    if left_max_price is None or right_max_price is None:
        return None, "Missing max_price for one or both products"

    if left_max_price <= 0 or right_max_price <= 0:
        return None, "Invalid max_price for one or both products"

    higher_price = max(left_max_price, right_max_price)
    lower_price = min(left_max_price, right_max_price)

    percentage_difference = ((higher_price - lower_price) / higher_price) * 100

    if percentage_difference <= 5:
        score = 100
    elif percentage_difference <= 10:
        score = 85
    elif percentage_difference <= 15:
        score = 70
    elif percentage_difference <= 25:
        score = 45
    else:
        score = 20

    reason = (
        f"max_price {left_max_price:.2f} vs {right_max_price:.2f}; "
        f"difference={percentage_difference:.1f}%"
    )

    return score, reason

def calculate_name_match_score(left_name: str, right_name: str) -> tuple[float, str]:
    left_normalised = normalise_product_name(left_name)
    right_normalised = normalise_product_name(right_name)

    token_set = fuzz.token_set_ratio(left_normalised, right_normalised)
    token_sort = fuzz.token_sort_ratio(left_normalised, right_normalised)
    partial = fuzz.partial_ratio(left_normalised, right_normalised)

    base_score = (
        token_set * 0.50
        + token_sort * 0.35
        + partial * 0.15
    )

    penalty, penalty_reasons = attribute_penalty(left_name, right_name)

    final_score = max(0, base_score - penalty)

    reasons = [
        f"name token_set={token_set:.1f}",
        f"token_sort={token_sort:.1f}",
        f"partial={partial:.1f}",
    ]

    if penalty_reasons:
        reasons.extend(penalty_reasons)

    return round(final_score, 2), "; ".join(reasons)

def calculate_final_match_score(
    name_score: float,
    price_score: float | None,
) -> float:
    if price_score is None:
        return round(name_score, 2)

    final_score = (name_score * 0.75) + (price_score * 0.25)

    return round(final_score, 2)

def _safe_float(value: object) -> float | None:
    if pd.isna(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_cross_vendor_match_candidates(
    products_path: Path = PRODUCTS_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
    min_score: float = 80,
) -> list[ProductMatchCandidate]:
    products = pd.read_csv(products_path)

    required_product_columns = {"product_id", "vendor", "product_name", "category"}
    missing_product_columns = required_product_columns - set(products.columns)

    if missing_product_columns:
        raise ValueError(f"products.csv is missing columns: {sorted(missing_product_columns)}")

    if product_metrics_path.exists():
        metrics = pd.read_csv(product_metrics_path)

        required_metric_columns = {"product_id", "vendor", "max_price"}
        missing_metric_columns = required_metric_columns - set(metrics.columns)

        if missing_metric_columns:
            raise ValueError(
                f"product_metrics.csv is missing columns: {sorted(missing_metric_columns)}"
            )

        products["product_id"] = products["product_id"].astype(str)
        products["vendor"] = products["vendor"].astype(str)

        metrics["product_id"] = metrics["product_id"].astype(str)
        metrics["vendor"] = metrics["vendor"].astype(str)

        products = products.merge(
            metrics[["product_id", "vendor", "max_price"]],
            on=["product_id", "vendor"],
            how="left",
        )
    else:
        products["max_price"] = None

    candidates: list[ProductMatchCandidate] = []

    for category, category_products in products.groupby("category"):
        rows = category_products.to_dict("records")

        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if left["vendor"] == right["vendor"]:
                    continue

                left_max_price = _safe_float(left.get("max_price"))
                right_max_price = _safe_float(right.get("max_price"))

                name_score, name_reason = calculate_name_match_score(
                    str(left["product_name"]),
                    str(right["product_name"]),
                )

                price_score, price_reason = calculate_price_score(
                    left_max_price,
                    right_max_price,
                )

                final_score = calculate_final_match_score(
                    name_score=name_score,
                    price_score=price_score,
                )

                if final_score >= min_score:
                    candidates.append(
                        ProductMatchCandidate(
                            category=category,
                            left_product_id=str(left["product_id"]),
                            left_vendor=str(left["vendor"]),
                            left_product_name=str(left["product_name"]),
                            left_max_price=left_max_price,
                            right_product_id=str(right["product_id"]),
                            right_vendor=str(right["vendor"]),
                            right_product_name=str(right["product_name"]),
                            right_max_price=right_max_price,
                            name_score=name_score,
                            price_score=price_score,
                            final_score=final_score,
                            match_reason=f"{name_reason}; {price_reason}",
                        )
                    )

    return sorted(candidates, key=lambda x: x.final_score, reverse=True)


def print_match_candidates(candidates: list[ProductMatchCandidate]) -> None:
    if not candidates:
        print("\nNo cross-vendor match candidates found.")
        return

    print("\nCROSS-VENDOR PRODUCT MATCH CANDIDATES")
    print("=" * 100)

    for candidate in candidates:
        left_price = (
            f"${candidate.left_max_price:.2f}"
            if candidate.left_max_price is not None
            else "N/A"
        )

        right_price = (
            f"${candidate.right_max_price:.2f}"
            if candidate.right_max_price is not None
            else "N/A"
        )

        price_score = (
            f"{candidate.price_score:.1f}"
            if candidate.price_score is not None
            else "N/A"
        )

        print(f"\nCategory: {candidate.category}")
        print(f"Final score: {candidate.final_score:.1f}")
        print(f"Name score:  {candidate.name_score:.1f}")
        print(f"Price score: {price_score}")

        print()
        print(f"{candidate.left_vendor}:")
        print(f"  Product ID: {candidate.left_product_id}")
        print(f"  Name:       {candidate.left_product_name}")
        print(f"  Max price:  {left_price}")

        print()
        print(f"{candidate.right_vendor}:")
        print(f"  Product ID: {candidate.right_product_id}")
        print(f"  Name:       {candidate.right_product_name}")
        print(f"  Max price:  {right_price}")

        print()
        print(f"Reason: {candidate.match_reason}")
        print("-" * 100)


def ensure_product_matches_file() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    if not PRODUCT_MATCHES_PATH.exists():
        pd.DataFrame(columns=PRODUCT_MATCH_COLUMNS).to_csv(
            PRODUCT_MATCHES_PATH,
            index=False,
        )


def build_product_matches_from_approved_candidates(
    approved_candidates: list[ProductMatchCandidate],
) -> pd.DataFrame:
    rows = []

    for index, candidate in enumerate(approved_candidates, start=1):
        match_group_id = f"{candidate.category}_{index:04d}"

        rows.append(
            {
                "match_group_id": match_group_id,
                "category": candidate.category,
                "product_id": candidate.left_product_id,
                "vendor": candidate.left_vendor,
                "product_name": candidate.left_product_name,
                "normalised_name": normalise_product_name(candidate.left_product_name),
                "match_confidence": candidate.score,
                "match_method": "fuzzy",
                "review_status": "approved",
                "last_updated": date.today().isoformat(),
            }
        )

        rows.append(
            {
                "match_group_id": match_group_id,
                "category": candidate.category,
                "product_id": candidate.right_product_id,
                "vendor": candidate.right_vendor,
                "product_name": candidate.right_product_name,
                "normalised_name": normalise_product_name(candidate.right_product_name),
                "match_confidence": candidate.score,
                "match_method": "fuzzy",
                "review_status": "approved",
                "last_updated": date.today().isoformat(),
            }
        )

    return pd.DataFrame(rows, columns=PRODUCT_MATCH_COLUMNS)
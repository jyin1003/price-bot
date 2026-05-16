from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from price_bot.config import (
    DATA_DIR,
    PRODUCTS_PATH,
    PRODUCT_MATCH_PATH,
    PRODUCT_METRICS_PATH,
    GROUPED_PRODUCT_METRICS_PATH,
    MATCH_MIN_SCORE,
)
from data.model import (
    ProductMatchCandidate,
    PRODUCT_MATCH_COLUMNS,
    GROUPED_PRODUCT_METRICS_COLUMNS,
    METRIC_COLUMNS,
)


# ---------------------------------------------------------------------------
# Name utilities
# ---------------------------------------------------------------------------

def normalise_product_name(name: str) -> str:
    name = name.lower()
    replacements = {"&": " and ", "-": " ", "/": " ", ",": " ", "(": " ", ")": " "}
    for old, new in replacements.items():
        name = name.replace(old, new)
    return re.sub(r"\s+", " ", name).strip()


def token_intersection_name(names: list[str]) -> str:
    """
    Return all tokens (words) that appear in *every* product name,
    preserving the order they appear in the first name.

    Example:
        "Kleenex Complete Clean 3 Ply Facial Tissues 95 Pack"
        "Kleenex Complete Clean Facial Tissues 3 Ply 95 Pack"
        -> "Kleenex Complete Clean 3 Ply Facial Tissues 95 Pack"

    Falls back to the first name if no common tokens are found.
    """
    if not names:
        return ""
    if len(names) == 1:
        return names[0]

    token_lists = [normalise_product_name(n).split() for n in names]
    common = set(token_lists[0]).intersection(*[set(t) for t in token_lists[1:]])
    ordered = [t for t in token_lists[0] if t in common]

    return " ".join(ordered).title() if ordered else names[0]



# ---------------------------------------------------------------------------
# Attribute extraction & scoring
# ---------------------------------------------------------------------------

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
    la = extract_product_attributes(left_name)
    ra = extract_product_attributes(right_name)
    penalty, reasons = 0, []
    if la["ply"] and ra["ply"] and la["ply"] != ra["ply"]:
        penalty += 25
        reasons.append(f"Different ply: {la['ply']} vs {ra['ply']}")
    if la["pack_count"] and ra["pack_count"] and la["pack_count"] != ra["pack_count"]:
        penalty += 20
        reasons.append(f"Different pack count: {la['pack_count']} vs {ra['pack_count']}")
    if (
        la["size_value"] and ra["size_value"]
        and la["size_unit"] and ra["size_unit"]
        and (la["size_value"] != ra["size_value"] or la["size_unit"] != ra["size_unit"])
    ):
        penalty += 20
        reasons.append(
            f"Different size: {la['size_value']}{la['size_unit']} vs "
            f"{ra['size_value']}{ra['size_unit']}"
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
    higher = max(left_max_price, right_max_price)
    lower = min(left_max_price, right_max_price)
    pct_diff = ((higher - lower) / higher) * 100
    if pct_diff <= 5:
        score = 100
    elif pct_diff <= 10:
        score = 85
    elif pct_diff <= 15:
        score = 70
    elif pct_diff <= 25:
        score = 45
    else:
        score = 20
    return score, (
        f"max_price {left_max_price:.2f} vs {right_max_price:.2f}; "
        f"difference={pct_diff:.1f}%"
    )


def _extract_brand(name: str) -> str:
    """First word of the normalised name is treated as the brand."""
    tokens = normalise_product_name(name).split()
    return tokens[0] if tokens else ""


def _extract_standalone_numbers(name: str) -> set[str]:
    """
    Return all standalone integers in the normalised name that are NOT
    immediately followed by a unit word (g, kg, ml, l, m, ply, pack, pk,
    pcs, pieces).  These are bare identifiers like product numbers or
    quantities that must match exactly between two products to be considered
    the same item.

    Example:
        "Kleenex 3 Ply 95 Pack"  ->  {}   (both 3 and 95 are bound to units)
        "Oral-B Pro 1000 Brush"  ->  {"1000"}
    """
    unit_words = {"g", "kg", "ml", "l", "m", "ply", "pack", "pk", "pcs", "pieces"}
    normalised = normalise_product_name(name)
    tokens = normalised.split()
    standalone: set[str] = set()
    for i, token in enumerate(tokens):
        if re.fullmatch(r"\d+", token):
            next_token = tokens[i + 1] if i + 1 < len(tokens) else ""
            if next_token not in unit_words:
                standalone.add(token)
    return standalone


def calculate_name_match_score(left_name: str, right_name: str) -> tuple[float, str]:
    ln = normalise_product_name(left_name)
    rn = normalise_product_name(right_name)

    # Hard disqualifier 1: brands must match
    left_brand = _extract_brand(left_name)
    right_brand = _extract_brand(right_name)
    if left_brand and right_brand and left_brand != right_brand:
        return 0.0, f"Brand mismatch: '{left_brand}' vs '{right_brand}'"

    # Hard disqualifier 2: bare numbers present in both must be identical sets
    left_nums = _extract_standalone_numbers(left_name)
    right_nums = _extract_standalone_numbers(right_name)
    if left_nums and right_nums and left_nums != right_nums:
        return 0.0, f"Number mismatch: {sorted(left_nums)} vs {sorted(right_nums)}"

    token_set = fuzz.token_set_ratio(ln, rn)
    token_sort = fuzz.token_sort_ratio(ln, rn)
    partial = fuzz.partial_ratio(ln, rn)
    base_score = token_set * 0.50 + token_sort * 0.35 + partial * 0.15
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
    return round(name_score * 0.75 + price_score * 0.25, 2)


def _safe_float(value: object) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# product_match.csv I/O
# ---------------------------------------------------------------------------

def _load_product_match(path: Path = PRODUCT_MATCH_PATH) -> pd.DataFrame:
    """Load product_match.csv, returning an empty frame with correct columns if absent."""
    if not path.exists():
        return pd.DataFrame(columns=PRODUCT_MATCH_COLUMNS)
    try:
        df = pd.read_csv(path, dtype={"product_id": str, "group_id": int})
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=PRODUCT_MATCH_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=PRODUCT_MATCH_COLUMNS)
    missing = set(PRODUCT_MATCH_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"product_match.csv is missing columns: {sorted(missing)}")
    return df[PRODUCT_MATCH_COLUMNS].copy()


def _save_product_match(df: pd.DataFrame, path: Path = PRODUCT_MATCH_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = (
        df.sort_values(["category", "group_id", "vendor", "product_id"])
        .reset_index(drop=True)
    )
    df.to_csv(path, index=False)


def _next_group_id(df: pd.DataFrame) -> int:
    """Return the next monotonically increasing group_id."""
    if df.empty or "group_id" not in df.columns:
        return 1
    return int(df["group_id"].max()) + 1


# ---------------------------------------------------------------------------
# Unmatched product check (used by main.py pipeline)
# ---------------------------------------------------------------------------

def has_unmatched_products(
    products_path: Path = PRODUCTS_PATH,
    product_match_path: Path = PRODUCT_MATCH_PATH,
) -> bool:
    """
    Return True if there are any (product_id, vendor) pairs in products.csv
    that are not yet present in product_match.csv.

    Used by main.py to decide whether to trigger the interactive matching
    session mid-pipeline.
    """
    if not products_path.exists():
        return False

    try:
        products = pd.read_csv(products_path, dtype={"product_id": str})
    except pd.errors.EmptyDataError:
        return False

    if products.empty:
        return False

    match_df = _load_product_match(product_match_path)

    if match_df.empty:
        return True

    assigned_keys = set(
        zip(
            match_df["product_id"].astype(str),
            match_df["vendor"].astype(str),
        )
    )

    for row in products.itertuples(index=False):
        if (str(row.product_id), str(row.vendor)) not in assigned_keys:
            return True

    return False


# ---------------------------------------------------------------------------
# Candidate generation (used for preview mode)
# ---------------------------------------------------------------------------

def find_cross_vendor_match_candidates(
    products_path: Path = PRODUCTS_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
    min_score: float = MATCH_MIN_SCORE,
) -> list[ProductMatchCandidate]:
    products = pd.read_csv(products_path)
    required = {"product_id", "vendor", "product_name", "category"}
    missing = required - set(products.columns)
    if missing:
        raise ValueError(f"products.csv is missing columns: {sorted(missing)}")

    if product_metrics_path.exists():
        metrics = pd.read_csv(product_metrics_path)
        req_m = {"product_id", "vendor", "max_price"}
        miss_m = req_m - set(metrics.columns)
        if miss_m:
            raise ValueError(f"product_metrics.csv is missing columns: {sorted(miss_m)}")
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

    for category, cat_df in products.groupby("category"):
        rows = cat_df.to_dict("records")
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if left["vendor"] == right["vendor"]:
                    continue
                lmp = _safe_float(left.get("max_price"))
                rmp = _safe_float(right.get("max_price"))
                name_score, name_reason = calculate_name_match_score(
                    str(left["product_name"]), str(right["product_name"])
                )
                price_score, price_reason = calculate_price_score(lmp, rmp)
                final_score = calculate_final_match_score(name_score, price_score)
                if final_score >= min_score:
                    candidates.append(ProductMatchCandidate(
                        category=str(category),
                        left_product_id=str(left["product_id"]),
                        left_vendor=str(left["vendor"]),
                        left_product_name=str(left["product_name"]),
                        left_max_price=lmp,
                        right_product_id=str(right["product_id"]),
                        right_vendor=str(right["vendor"]),
                        right_product_name=str(right["product_name"]),
                        right_max_price=rmp,
                        name_score=name_score,
                        price_score=price_score,
                        final_score=final_score,
                        match_reason=f"{name_reason}; {price_reason}",
                    ))

    return sorted(candidates, key=lambda x: x.final_score, reverse=True)


# ---------------------------------------------------------------------------
# Interactive review session
# ---------------------------------------------------------------------------

def _prompt_yn(question: str) -> tuple[bool, bool]:
    """
    Prompt until the user types y, n, or N.

    Returns (accepted, skip_all) where:
      y -> (True,  False)  add to this group
      n -> (False, False)  skip this group, keep comparing
      N -> (False, True)   skip all remaining groups, go straight to singleton
    """
    while True:
        answer = input(f"{question} (y/n/N to skip all): ").strip()
        if answer == "y":
            return True, False
        if answer == "n":
            return False, False
        if answer == "N":
            return False, True
        print("  Please enter y, n, or N (capital N to skip all).")


def _key(product_id: str, vendor: str) -> str:
    return f"{vendor}::{product_id}"


def run_interactive_matching(
    products_path: Path = PRODUCTS_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
    product_match_path: Path = PRODUCT_MATCH_PATH,
    min_score: float = MATCH_MIN_SCORE,
) -> pd.DataFrame:
    """
    Interactive CLI matching session.

    Flow
    ----
    1. Load all products from products.csv.
    2. Load existing product_match.csv (may be empty on first run).
    3. Identify products not yet in product_match.csv (new products).
    4. For each new product, find all existing groups in the same category
       with at least one member scoring >= min_score. Present them highest
       score first. First 'y' assigns the product to that group; remaining
       candidates are skipped. If all are 'n' (or none exist), the product
       becomes a new singleton group.
    5. Recompute group_name for every touched group using token intersection.
    6. Save and return the updated DataFrame.

    Re-run behaviour
    ----------------
    - Products already in product_match.csv are skipped silently.
    - Only genuinely new (product_id, vendor) combos are presented.
    """

    print("\n" + "=" * 60)
    print("PRODUCT MATCH — INTERACTIVE REVIEW")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load state
    # ------------------------------------------------------------------
    all_products = pd.read_csv(products_path, dtype={"product_id": str})
    match_df = _load_product_match(product_match_path)

    if match_df.empty:
        assigned_keys: set[str] = set()
    else:
        assigned_keys = {
            _key(str(r.product_id), str(r.vendor))
            for r in match_df.itertuples(index=False)
        }

    # ------------------------------------------------------------------
    # 2. Identify new products
    # ------------------------------------------------------------------
    new_products = [
        row for row in all_products.itertuples(index=False)
        if _key(str(row.product_id), str(row.vendor)) not in assigned_keys
    ]

    if not new_products:
        print("\nNo new products to review. product_match.csv is up to date.")
        return match_df

    print(f"\n{len(new_products)} new product(s) to review.\n")

    # ------------------------------------------------------------------
    # 3. Max price lookup for scoring
    # ------------------------------------------------------------------
    price_lookup: dict[str, float | None] = {}
    if product_metrics_path.exists():
        metrics = pd.read_csv(product_metrics_path, dtype={"product_id": str})
        for r in metrics.itertuples(index=False):
            price_lookup[_key(str(r.product_id), str(r.vendor))] = _safe_float(r.max_price)

    # ------------------------------------------------------------------
    # 4. Mutable groups dict: group_id -> list of row dicts
    # ------------------------------------------------------------------
    groups: dict[int, list[dict]] = {}
    if not match_df.empty:
        for gid, gdf in match_df.groupby("group_id"):
            groups[int(gid)] = gdf.to_dict("records")

    preexisting_group_ids: set[int] = set(groups.keys())
    next_gid = _next_group_id(match_df)
    touched_group_ids: set[int] = set()

    # ------------------------------------------------------------------
    # 5. Process each new product
    # ------------------------------------------------------------------
    for new_row in new_products:
        new_pid = str(new_row.product_id)
        new_vendor = str(new_row.vendor)
        new_name = str(new_row.product_name)
        new_category = str(new_row.category)
        new_price = price_lookup.get(_key(new_pid, new_vendor))

        new_price_label = f"${new_price:.2f}" if new_price is not None else "N/A"
        print(f"\n{'─' * 60}")
        print(f"New product:")
        print(f"  Vendor   : {new_vendor}")
        print(f"  ID       : {new_pid}")
        print(f"  Name     : {new_name}")
        print(f"  Category : {new_category}")
        print(f"  Max price: {new_price_label}")
        print(f"{'─' * 60}")

        # Score against every existing group in the same category
        scored_groups: list[tuple[float, int]] = []

        for gid, members in groups.items():
            if members[0].get("category", "") != new_category:
                continue

            best_score = 0.0
            for member in members:
                member_price = price_lookup.get(
                    _key(str(member["product_id"]), str(member["vendor"]))
                )
                name_score, _ = calculate_name_match_score(
                    new_name, str(member["product_name"])
                )
                price_score, _ = calculate_price_score(new_price, member_price)
                final = calculate_final_match_score(name_score, price_score)
                if final > best_score:
                    best_score = final

            if best_score >= min_score:
                scored_groups.append((best_score, gid))

        scored_groups.sort(key=lambda x: x[0], reverse=True)

        assigned = False
        skip_all = False

        for _score, gid in scored_groups:
            if skip_all:
                break

            members = groups[gid]
            group_name = members[0].get("group_name", "")

            print(f"\n  Group {gid} — \"{group_name}\":")
            for m in members:
                m_price = price_lookup.get(_key(str(m["product_id"]), str(m["vendor"])))
                m_price_label = f"${m_price:.2f}" if m_price is not None else "N/A"
                print(f"    {m['vendor']:<22} {m_price_label:>7}  {m['product_name']}")

            accepted, skip_all = _prompt_yn(
                f"  Add '{new_vendor:<22} {new_price_label:>7} {new_name}' to this group?"
            )
            if accepted:
                groups[gid].append({
                    "group_id": gid,
                    "group_name": group_name,
                    "category": new_category,
                    "product_id": new_pid,
                    "vendor": new_vendor,
                    "product_name": new_name,
                })
                # Only recalculate the name for groups created this session
                if gid not in preexisting_group_ids:
                    new_group_name = token_intersection_name(
                        [m["product_name"] for m in groups[gid]]
                    )
                    for m in groups[gid]:
                        m["group_name"] = new_group_name
                touched_group_ids.add(gid)
                assigned = True
                print(f"  ✓ Added to group {gid}.")
                break
            elif skip_all:
                print(f"  Skipping all remaining groups for this product.")
            else:
                print(f"  Skipped group {gid}.")

        if not assigned:
            gid = next_gid
            next_gid += 1
            groups[gid] = [{
                "group_id": gid,
                "group_name": new_name,
                "category": new_category,
                "product_id": new_pid,
                "vendor": new_vendor,
                "product_name": new_name,
            }]
            touched_group_ids.add(gid)
            print(f"  ✓ No match — created singleton group {gid}.")

    # ------------------------------------------------------------------
    # 6. Recompute group_name for new (non-pre-existing) touched groups.
    #    Pre-existing group names are never changed.
    # ------------------------------------------------------------------
    for gid in touched_group_ids:
        if gid in preexisting_group_ids:
            continue
        members = groups[gid]
        new_group_name = token_intersection_name([m["product_name"] for m in members])
        for m in members:
            m["group_name"] = new_group_name

    # ------------------------------------------------------------------
    # 7. Rebuild DataFrame and save
    # ------------------------------------------------------------------
    all_rows: list[dict] = [m for members in groups.values() for m in members]
    updated_df = pd.DataFrame(all_rows, columns=PRODUCT_MATCH_COLUMNS)
    updated_df["group_id"] = updated_df["group_id"].astype(int)

    _save_product_match(updated_df, product_match_path)

    total_groups = updated_df["group_id"].nunique()
    total_products = len(updated_df)
    print(f"\n{'=' * 60}")
    print(f"Review complete.")
    print(f"  Total groups  : {total_groups}")
    print(f"  Total products: {total_products}")
    print(f"  Saved to      : {product_match_path}")
    print(f"{'=' * 60}\n")

    return updated_df


# ---------------------------------------------------------------------------
# grouped_product_metrics.csv
# ---------------------------------------------------------------------------

def update_grouped_product_metrics(
    product_match_path: Path = PRODUCT_MATCH_PATH,
    product_metrics_path: Path = PRODUCT_METRICS_PATH,
    output_path: Path = GROUPED_PRODUCT_METRICS_PATH,
) -> None:
    """
    Rebuild grouped_product_metrics.csv by aggregating product_metrics.csv
    over the groups defined in product_match.csv.

    Per group:
      max_price    -> max of all member max_prices
      min_price    -> min of all member min_prices
      last_updated -> most recent last_updated across members
    """
    if not product_match_path.exists() or not product_metrics_path.exists():
        return

    match_df = _load_product_match(product_match_path)
    if match_df.empty:
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


# ---------------------------------------------------------------------------
# Legacy terminal print (kept for dry-run preview with --match-products)
# ---------------------------------------------------------------------------

def print_match_candidates(candidates: list[ProductMatchCandidate]) -> None:
    if not candidates:
        print("\nNo cross-vendor match candidates found.")
        return

    print("\nCROSS-VENDOR PRODUCT MATCH CANDIDATES")
    print("=" * 100)

    for c in candidates:
        left_price = f"${c.left_max_price:.2f}" if c.left_max_price is not None else "N/A"
        right_price = f"${c.right_max_price:.2f}" if c.right_max_price is not None else "N/A"
        price_score = f"{c.price_score:.1f}" if c.price_score is not None else "N/A"

        print(f"\nCategory: {c.category}")
        print(
            f"Final score: {c.final_score:.1f}  "
            f"Name score: {c.name_score:.1f}  "
            f"Price score: {price_score}"
        )
        print(f"  {c.left_vendor}:  {c.left_product_name}  ({left_price})")
        print(f"  {c.right_vendor}:  {c.right_product_name}  ({right_price})")
        print("-" * 100)
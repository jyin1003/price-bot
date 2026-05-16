from data.model import CategoryPriceAnalysis, GroupPriceAnalysis


def print_to_terminal(analysis: dict[str, CategoryPriceAnalysis]) -> None:
    if not analysis:
        print("\nNo price analysis available.")
        return

    for category, result in analysis.items():
        category_title = f" {category.upper()} "

        cheapest_width = _calculate_table_width(result.cheapest_products)
        top_five_width = _calculate_table_width(result.top_five_cheapest)
        most_discounted_width = _calculate_table_width(result.top_five_most_discounted)

        section_width = max(
            len(category_title),
            len("CHEAPEST PRODUCTS"),
            len("TOP 5 CHEAPEST PRODUCTS"),
            len("TOP 5 MOST DISCOUNTED PRODUCTS"),
            cheapest_width,
            top_five_width,
            most_discounted_width,
        )

        print("\n" + "=" * section_width)
        print(category_title)
        print("=" * section_width)

        print("\nCHEAPEST PRODUCTS")
        print("-" * section_width)

        if result.cheapest_products:
            _print_group_table(result.cheapest_products)
        else:
            print("No products are currently at their cheapest price.")

        print("\nTOP 5 CHEAPEST PRODUCTS")
        print("-" * section_width)

        if result.top_five_cheapest:
            _print_group_table(result.top_five_cheapest)
        else:
            print("No products available.")

        print("\nTOP 5 MOST DISCOUNTED PRODUCTS")
        print("-" * section_width)

        if result.top_five_most_discounted:
            _print_group_table(result.top_five_most_discounted)
        else:
            print("No discounted products available.")

        print()


def _print_group_table(groups: list[GroupPriceAnalysis]) -> None:
    rows = _build_group_rows(groups)
    widths = _calculate_column_widths(rows)

    print(
        f"{'Product':<{widths['Product']}}  "
        f"{'Best Vendor':<{widths['Best Vendor']}}  "
        f"{'Price':>{widths['Price']}}  "
        f"{'% Off':>{widths['% Off']}}  "
        f"{'Status':<{widths['Status']}}"
    )

    print(
        f"{'-' * widths['Product']}  "
        f"{'-' * widths['Best Vendor']}  "
        f"{'-' * widths['Price']}  "
        f"{'-' * widths['% Off']}  "
        f"{'-' * widths['Status']}"
    )

    for row in rows:
        print(
            f"{row['Product']:<{widths['Product']}}  "
            f"{row['Best Vendor']:<{widths['Best Vendor']}}  "
            f"{row['Price']:>{widths['Price']}}  "
            f"{row['% Off']:>{widths['% Off']}}  "
            f"{row['Status']:<{widths['Status']}}"
        )


def _build_group_rows(groups: list[GroupPriceAnalysis]) -> list[dict[str, str]]:
    return [
        {
            "Product": str(group.group_name),
            "Best Vendor": str(group.best_vendor),
            "Price": f"${group.current_price:.2f}",
            "% Off": f"{group.discount:.1f}%",
            "Status": str(group.status),
        }
        for group in groups
    ]


def _calculate_column_widths(rows: list[dict[str, str]]) -> dict[str, int]:
    headers = ["Product", "Best Vendor", "Price", "% Off", "Status"]

    if not rows:
        return {header: len(header) for header in headers}

    return {
        header: max(
            len(header),
            max(len(row[header]) for row in rows),
        )
        for header in headers
    }


def _calculate_table_width(groups: list[GroupPriceAnalysis]) -> int:
    if not groups:
        return 0

    rows = _build_group_rows(groups)
    widths = _calculate_column_widths(rows)

    spaces_between_columns = 2 * (len(widths) - 1)

    return sum(widths.values()) + spaces_between_columns
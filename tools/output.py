from data.model import CategoryPriceAnalysis, ProductPriceAnalysis


def print_to_terminal(analysis: dict[str, CategoryPriceAnalysis]) -> None:
    if not analysis:
        print("\nNo price analysis available.")
        return

    for category, result in analysis.items():
        category_title = f" {category.upper()} "

        cheapest_width = _calculate_table_width(result.cheapest_products)
        top_five_width = _calculate_table_width(result.top_five_cheapest)

        section_width = max(
            len(category_title),
            len("CHEAPEST PRODUCTS"),
            len("TOP 5 CHEAPEST PRODUCTS"),
            cheapest_width,
            top_five_width,
        )

        print("\n" + "=" * section_width)
        print(category_title)
        print("=" * section_width)

        print("\nCHEAPEST PRODUCTS")
        print("-" * section_width)

        if result.cheapest_products:
            _print_product_table(result.cheapest_products)
        else:
            print("No products are currently at their cheapest price.")

        print("\nTOP 5 CHEAPEST PRODUCTS")
        print("-" * section_width)

        if result.top_five_cheapest:
            _print_product_table(result.top_five_cheapest)
        else:
            print("No products available.")

        print()


def _print_product_table(products: list[ProductPriceAnalysis]) -> None:
    rows = _build_product_rows(products)
    widths = _calculate_column_widths(rows)

    print(
        f"{'Product':<{widths['Product']}}  "
        f"{'Vendor':<{widths['Vendor']}}  "
        f"{'Price':>{widths['Price']}}  "
        f"{'% Off':>{widths['% Off']}}  "
        f"{'Status':<{widths['Status']}}"
    )

    print(
        f"{'-' * widths['Product']}  "
        f"{'-' * widths['Vendor']}  "
        f"{'-' * widths['Price']}  "
        f"{'-' * widths['% Off']}  "
        f"{'-' * widths['Status']}"
    )

    for row in rows:
        print(
            f"{row['Product']:<{widths['Product']}}  "
            f"{row['Vendor']:<{widths['Vendor']}}  "
            f"{row['Price']:>{widths['Price']}}  "
            f"{row['% Off']:>{widths['% Off']}}  "
            f"{row['Status']:<{widths['Status']}}"
        )


def _build_product_rows(products: list[ProductPriceAnalysis]) -> list[dict[str, str]]:
    return [
        {
            "Product": str(product.product_name),
            "Vendor": str(product.vendor),
            "Price": f"${product.current_price:.2f}",
            "% Off": f"{product.discount:.1f}%",
            "Status": str(product.status),
        }
        for product in products
    ]


def _calculate_column_widths(rows: list[dict[str, str]]) -> dict[str, int]:
    headers = ["Product", "Vendor", "Price", "% Off", "Status"]

    return {
        header: max(
            len(header),
            max(len(row[header]) for row in rows),
        )
        for header in headers
    }


def _calculate_table_width(products: list[ProductPriceAnalysis]) -> int:
    if not products:
        return 0

    rows = _build_product_rows(products)
    widths = _calculate_column_widths(rows)

    spaces_between_columns = 2 * (len(widths) - 1)

    return sum(widths.values()) + spaces_between_columns
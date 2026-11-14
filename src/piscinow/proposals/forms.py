from datetime import date

from piscinow.proposals.rules import parse_amount


def parse_proposal_form(
    item_desc: list[str], item_amount: list[str], scope: str, lead_time_days: str, valid_until: str, exclusions: str,
    item_product: list[str] | None = None,
) -> tuple[dict | None, list[str]]:
    """Turn raw form fields into service arguments, or explain what is wrong with the typing.

    Business rules (totals, limits, dates in the future, whose product it is) stay in the service;
    this only reads text. An item is (description, amount or None, product id or None): with a
    catalog product chosen, a blank description or amount is filled from the product by the service.
    """
    errors: list[str] = []
    items: list[tuple] = []
    products = item_product or []
    rows = max(len(item_desc), len(item_amount), len(products))
    for index in range(rows):
        description = (item_desc[index] if index < len(item_desc) else "").strip()
        raw_amount = (item_amount[index] if index < len(item_amount) else "").strip()
        product = (products[index] if index < len(products) else "").strip() or None
        if not description and not raw_amount and not product:
            continue
        amount = parse_amount(raw_amount) if raw_amount else None
        if raw_amount and amount is None:
            errors.append(f"Informe um valor válido para o item {index + 1} (ex.: 18000,00).")
        elif product:
            items.append((description, amount, product))
        elif not description:
            errors.append(f"O item {index + 1} tem valor mas não tem descrição.")
        elif amount is None:
            errors.append(f"Informe um valor válido para o item {index + 1} (ex.: 18000,00).")
        else:
            items.append((description, amount, None))

    try:
        days = int(lead_time_days.strip())
    except ValueError:
        errors.append("Informe o prazo estimado em dias, só com números.")
        days = 0
    try:
        validity = date.fromisoformat(valid_until.strip())
    except ValueError:
        errors.append("Informe a validade como uma data.")
        validity = None

    if errors:
        return None, errors
    return {
        "items": items, "scope": scope, "lead_time_days": days, "valid_until": validity, "exclusions": exclusions,
    }, []

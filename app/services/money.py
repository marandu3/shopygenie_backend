"""Central money-handling rules (see MASTER PROMPT §18, §118).

All authoritative financial arithmetic goes through Decimal, quantized to
the currency's minor-unit precision with a single, consistent rounding
strategy (ROUND_HALF_UP — the conventional retail/accounting rounding rule).
Never do `a - b` on raw floats for money in service code; use these helpers.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value) -> Decimal:
    """Coerce any numeric input to a Decimal quantized to 2dp."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def percent_of(base: Decimal, percent: Decimal) -> Decimal:
    return money(base * percent / Decimal(100))

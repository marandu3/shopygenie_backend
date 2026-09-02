import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.debt import Debt
from app.models.expense import Expense
from app.models.product import Product
from app.models.purchase import Purchase, PurchaseStatus
from app.models.return_models import SaleReturn
from app.models.sale import Payment, Sale, SaleItem, SaleStatus
from app.models.supplier import Supplier
from app.schemas.report import (
    BusinessSummaryReport,
    ComparisonMetric,
    ComparisonReport,
    CustomerReport,
    CustomerSpend,
    DebtAgingBucket,
    DebtAgingReport,
    HeatmapCell,
    HeatmapReport,
    InventoryReport,
    ParetoLine,
    ParetoReport,
    PaymentMethodTotal,
    ProductMovementSummary,
    ReportFilters,
    SalesPowerPoint,
    SalesPowerReport,
    SalesReport,
    SupplierPurchaseSummary,
    SupplierReport,
    TimeSeriesPoint,
    TimeSeriesReport,
)
from app.services.money import money


def _sale_conditions(organization_id: uuid.UUID, filters: ReportFilters) -> list:
    conditions = [Sale.organization_id == organization_id, Sale.status == SaleStatus.COMPLETED]
    if filters.start_date:
        conditions.append(Sale.created_at >= filters.start_date)
    if filters.end_date:
        conditions.append(Sale.created_at <= filters.end_date)
    if filters.branch_id:
        conditions.append(Sale.branch_id == filters.branch_id)
    if filters.customer_id:
        conditions.append(Sale.customer_id == filters.customer_id)
    return conditions


async def build_business_summary(
    db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters
) -> BusinessSummaryReport:
    """All figures computed via SQL aggregation (never "load everything into
    Python and sum it") so this scales to real transaction volumes.

    Accounting model (MASTER PROMPT §20, §32):
      revenue             = completed sales total
      cogs                = sum(unit_cost_price * quantity) for sold items
      gross_profit        = revenue - cogs
      operating_expenses  = Expense records ONLY — never purchases, never debts
      net_profit          = gross_profit - operating_expenses
      outstanding_receivables = uncleared Debt balances — reported separately,
                                 never subtracted as if it were an expense.
    """
    sale_conditions = _sale_conditions(organization_id, filters)

    revenue_row = (
        await db.execute(
            select(func.coalesce(func.sum(Sale.total_amount), 0), func.count(Sale.id)).where(*sale_conditions)
        )
    ).one()
    revenue = money(revenue_row[0])
    total_transactions = int(revenue_row[1])

    item_conditions = list(sale_conditions)
    item_query = select(
        func.coalesce(func.sum(SaleItem.unit_cost_price * SaleItem.quantity), 0),
        func.coalesce(func.sum(SaleItem.quantity), 0),
    ).select_from(SaleItem).join(Sale, Sale.id == SaleItem.sale_id).where(*item_conditions)
    if filters.product_id:
        item_query = item_query.where(SaleItem.product_id == filters.product_id)
    cogs_row = (await db.execute(item_query)).one()
    cogs = money(cogs_row[0])
    total_units_sold = int(cogs_row[1])

    gross_profit = money(revenue - cogs)
    gross_margin_percent = float(money((gross_profit / revenue * 100) if revenue > 0 else Decimal("0")))

    expense_conditions = [Expense.organization_id == organization_id]
    if filters.start_date:
        expense_conditions.append(Expense.expense_date >= filters.start_date.date())
    if filters.end_date:
        expense_conditions.append(Expense.expense_date <= filters.end_date.date())
    if filters.branch_id:
        expense_conditions.append(Expense.branch_id == filters.branch_id)
    operating_expenses = money(
        (await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(*expense_conditions))).scalar_one()
    )

    net_profit = money(gross_profit - operating_expenses)
    net_margin_percent = float(money((net_profit / revenue * 100) if revenue > 0 else Decimal("0")))

    purchase_conditions = [Purchase.organization_id == organization_id, Purchase.status == PurchaseStatus.COMPLETED]
    if filters.start_date:
        purchase_conditions.append(Purchase.created_at >= filters.start_date)
    if filters.end_date:
        purchase_conditions.append(Purchase.created_at <= filters.end_date)
    total_purchases = money(
        (await db.execute(select(func.coalesce(func.sum(Purchase.total_amount), 0)).where(*purchase_conditions))).scalar_one()
    )

    debt_conditions = [Debt.organization_id == organization_id, Debt.cleared.is_(False)]
    if filters.customer_id:
        debt_conditions.append(Debt.customer_id == filters.customer_id)
    outstanding_receivables = money(
        (await db.execute(select(func.coalesce(func.sum(Debt.balance), 0)).where(*debt_conditions))).scalar_one()
    )

    average_sale_amount = money(revenue / total_transactions) if total_transactions else Decimal("0")

    most_sold_product = await _extreme_product_by_quantity(db, sale_conditions, descending=True)
    least_sold_product = await _extreme_product_by_quantity(db, sale_conditions, descending=False)
    top_customer = await _extreme_customer_by_revenue(db, sale_conditions, descending=True)
    lowest_customer = await _extreme_customer_by_revenue(db, sale_conditions, descending=False)

    return BusinessSummaryReport(
        revenue=float(revenue),
        cogs=float(cogs),
        gross_profit=float(gross_profit),
        gross_margin_percent=gross_margin_percent,
        operating_expenses=float(operating_expenses),
        net_profit=float(net_profit),
        net_margin_percent=net_margin_percent,
        total_purchases=float(total_purchases),
        outstanding_receivables=float(outstanding_receivables),
        total_transactions=total_transactions,
        average_sale_amount=float(average_sale_amount),
        total_units_sold=total_units_sold,
        most_sold_product=most_sold_product,
        least_sold_product=least_sold_product,
        top_spending_customer=top_customer,
        lowest_spending_customer=lowest_customer,
        generated_at=datetime.now(timezone.utc),
    )


async def _extreme_product_by_quantity(db: AsyncSession, sale_conditions: list, *, descending: bool) -> str | None:
    order = func.sum(SaleItem.quantity).desc() if descending else func.sum(SaleItem.quantity).asc()
    query = (
        select(SaleItem.product_name, func.sum(SaleItem.quantity).label("qty"))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*sale_conditions)
        .group_by(SaleItem.product_name)
        .order_by(order)
        .limit(1)
    )
    row = (await db.execute(query)).first()
    return row[0] if row else None


async def _extreme_customer_by_revenue(db: AsyncSession, sale_conditions: list, *, descending: bool) -> str | None:
    order = func.sum(Sale.total_amount).desc() if descending else func.sum(Sale.total_amount).asc()
    query = (
        select(Customer.name, func.sum(Sale.total_amount).label("total"))
        .select_from(Sale)
        .join(Customer, Customer.id == Sale.customer_id)
        .where(*sale_conditions)
        .group_by(Customer.name)
        .order_by(order)
        .limit(1)
    )
    row = (await db.execute(query)).first()
    return row[0] if row else None


async def build_sales_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> SalesReport:
    sale_conditions = _sale_conditions(organization_id, filters)

    totals_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Sale.subtotal), 0),
                func.coalesce(func.sum(Sale.discount_total), 0),
                func.coalesce(func.sum(Sale.tax_total), 0),
                func.coalesce(func.sum(Sale.total_amount), 0),
                func.count(Sale.id),
            ).where(*sale_conditions)
        )
    ).one()
    gross_sales, discounts, tax, net_sales, transactions = (
        money(totals_row[0]), money(totals_row[1]), money(totals_row[2]), money(totals_row[3]), int(totals_row[4])
    )

    units_row = (
        await db.execute(
            select(func.coalesce(func.sum(SaleItem.quantity), 0))
            .select_from(SaleItem)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*sale_conditions)
        )
    ).scalar_one()
    units_sold = int(units_row)

    refund_row = (
        await db.execute(
            select(func.coalesce(func.sum(SaleReturn.refund_amount), 0))
            .select_from(SaleReturn)
            .join(Sale, Sale.id == SaleReturn.sale_id)
            .where(*sale_conditions)
        )
    ).scalar_one()
    refund_amount = money(refund_row)

    payment_rows = await db.execute(
        select(Payment.method, func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .join(Sale, Sale.id == Payment.sale_id)
        .where(*sale_conditions)
        .group_by(Payment.method)
    )
    payment_breakdown = [PaymentMethodTotal(method=row[0].value, total=float(money(row[1]))) for row in payment_rows.all()]

    average_transaction = money(net_sales / transactions) if transactions else Decimal("0")

    return SalesReport(
        gross_sales=float(gross_sales),
        discounts=float(discounts),
        tax=float(tax),
        net_sales=float(net_sales),
        refund_amount=float(refund_amount),
        transactions=transactions,
        units_sold=units_sold,
        average_transaction=float(average_transaction),
        payment_breakdown=payment_breakdown,
        generated_at=datetime.now(timezone.utc),
    )


async def build_inventory_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> InventoryReport:
    products_result = await db.execute(
        select(Product.id, Product.name, Product.current_stock, Product.cost_price, Product.low_stock_alert)
        .where(Product.organization_id == organization_id, Product.is_active.is_(True))
    )
    products = products_result.all()

    total_stock_value = money(sum((row.current_stock * row.cost_price for row in products), Decimal("0")))
    low_stock_count = sum(1 for row in products if row.low_stock_alert is not None and row.current_stock < row.low_stock_alert)
    out_of_stock_count = sum(1 for row in products if row.current_stock <= 0)

    sale_conditions = _sale_conditions(organization_id, filters)
    movement_rows = await db.execute(
        select(SaleItem.product_id, func.sum(SaleItem.quantity), func.sum(SaleItem.line_total))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*sale_conditions)
        .group_by(SaleItem.product_id)
    )
    movement_by_product = {row[0]: (int(row[1]), money(row[2])) for row in movement_rows.all()}

    summaries = [
        ProductMovementSummary(
            product_id=row.id,
            product_name=row.name,
            units_sold=movement_by_product.get(row.id, (0, Decimal("0")))[0],
            revenue=float(movement_by_product.get(row.id, (0, Decimal("0")))[1]),
        )
        for row in products
    ]
    fast_movers = sorted(summaries, key=lambda s: s.units_sold, reverse=True)[:5]
    slow_movers = sorted(summaries, key=lambda s: s.units_sold)[:5]

    return InventoryReport(
        total_stock_value=float(total_stock_value),
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        fast_movers=fast_movers,
        slow_movers=slow_movers,
        generated_at=datetime.now(timezone.utc),
    )


async def build_customer_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> CustomerReport:
    total_customers = (
        await db.execute(select(func.count(Customer.id)).where(Customer.organization_id == organization_id, Customer.is_active.is_(True)))
    ).scalar_one()

    new_customers_conditions = [Customer.organization_id == organization_id]
    if filters.start_date:
        new_customers_conditions.append(Customer.created_at >= filters.start_date)
    if filters.end_date:
        new_customers_conditions.append(Customer.created_at <= filters.end_date)
    new_customers = (await db.execute(select(func.count(Customer.id)).where(*new_customers_conditions))).scalar_one()

    sale_conditions = _sale_conditions(organization_id, filters)
    top_rows = await db.execute(
        select(Customer.id, Customer.name, func.sum(Sale.total_amount), func.count(Sale.id))
        .select_from(Sale)
        .join(Customer, Customer.id == Sale.customer_id)
        .where(*sale_conditions)
        .group_by(Customer.id, Customer.name)
        .order_by(func.sum(Sale.total_amount).desc())
        .limit(5)
    )
    top_customers = [
        CustomerSpend(customer_id=row[0], customer_name=row[1], total_spent=float(money(row[2])), transactions=int(row[3]))
        for row in top_rows.all()
    ]

    debt_conditions = [Debt.organization_id == organization_id, Debt.cleared.is_(False)]
    if filters.customer_id:
        debt_conditions.append(Debt.customer_id == filters.customer_id)
    total_outstanding = money(
        (await db.execute(select(func.coalesce(func.sum(Debt.balance), 0)).where(*debt_conditions))).scalar_one()
    )

    return CustomerReport(
        total_customers=total_customers,
        new_customers=new_customers,
        top_customers=top_customers,
        total_outstanding_receivables=float(total_outstanding),
        generated_at=datetime.now(timezone.utc),
    )


async def build_supplier_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> SupplierReport:
    conditions = [Purchase.organization_id == organization_id, Purchase.status == PurchaseStatus.COMPLETED]
    if filters.start_date:
        conditions.append(Purchase.created_at >= filters.start_date)
    if filters.end_date:
        conditions.append(Purchase.created_at <= filters.end_date)

    rows = await db.execute(
        select(Purchase.supplier_id, Supplier.name, func.sum(Purchase.total_amount), func.count(Purchase.id))
        .select_from(Purchase)
        .outerjoin(Supplier, Supplier.id == Purchase.supplier_id)
        .where(*conditions)
        .group_by(Purchase.supplier_id, Supplier.name)
        .order_by(func.sum(Purchase.total_amount).desc())
    )
    suppliers = [
        SupplierPurchaseSummary(
            supplier_id=row[0], supplier_name=row[1] or "No supplier", total_purchased=float(money(row[2])), purchase_count=int(row[3])
        )
        for row in rows.all()
    ]

    return SupplierReport(suppliers=suppliers, generated_at=datetime.now(timezone.utc))


async def build_debt_aging_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> DebtAgingReport:
    conditions = [Debt.organization_id == organization_id, Debt.cleared.is_(False)]
    if filters.customer_id:
        conditions.append(Debt.customer_id == filters.customer_id)

    result = await db.execute(select(Debt.created_at, Debt.balance).where(*conditions))
    rows = result.all()

    now = datetime.now(timezone.utc)
    buckets = {"0-30 days": [0, Decimal("0")], "31-60 days": [0, Decimal("0")], "61-90 days": [0, Decimal("0")], "90+ days": [0, Decimal("0")]}

    for created_at, balance in rows:
        age_days = (now - created_at).days
        if age_days <= 30:
            key = "0-30 days"
        elif age_days <= 60:
            key = "31-60 days"
        elif age_days <= 90:
            key = "61-90 days"
        else:
            key = "90+ days"
        buckets[key][0] += 1
        buckets[key][1] += balance

    bucket_list = [DebtAgingBucket(label=label, count=count, amount=float(money(amount))) for label, (count, amount) in buckets.items()]
    total_outstanding = money(sum((amount for _, amount in buckets.values()), Decimal("0")))

    return DebtAgingReport(buckets=bucket_list, total_outstanding=float(total_outstanding), generated_at=datetime.now(timezone.utc))


async def _period_metrics(db: AsyncSession, *, organization_id: uuid.UUID, start: datetime, end: datetime) -> dict:
    conditions = [Sale.organization_id == organization_id, Sale.status == SaleStatus.COMPLETED, Sale.created_at >= start, Sale.created_at <= end]

    revenue_row = (
        await db.execute(select(func.coalesce(func.sum(Sale.total_amount), 0), func.count(Sale.id)).where(*conditions))
    ).one()
    revenue = money(revenue_row[0])
    transactions = int(revenue_row[1])

    cogs = money(
        (
            await db.execute(
                select(func.coalesce(func.sum(SaleItem.unit_cost_price * SaleItem.quantity), 0))
                .select_from(SaleItem)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(*conditions)
            )
        ).scalar_one()
    )

    return {"revenue": revenue, "gross_profit": money(revenue - cogs), "transactions": Decimal(transactions)}


def _change_percent(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None  # never fabricate a percentage against a zero baseline (§48)
    return float(money((current - previous) / previous * 100))


async def build_comparison_report(
    db: AsyncSession, *, organization_id: uuid.UUID, current_start: datetime, current_end: datetime
) -> ComparisonReport:
    """Current period vs the immediately-preceding period of equal length —
    covers "today vs yesterday", "this week vs last week", etc. uniformly:
    the caller just resolves whichever preset to concrete dates."""
    duration = current_end - current_start
    previous_end = current_start - timedelta(microseconds=1)
    previous_start = previous_end - duration

    current = await _period_metrics(db, organization_id=organization_id, start=current_start, end=current_end)
    previous = await _period_metrics(db, organization_id=organization_id, start=previous_start, end=previous_end)

    metrics = [
        ComparisonMetric(
            label=key,
            current=float(current[key]),
            previous=float(previous[key]),
            change_percent=_change_percent(current[key], previous[key]),
        )
        for key in ("revenue", "gross_profit", "transactions")
    ]

    return ComparisonReport(
        current_start=current_start, current_end=current_end,
        previous_start=previous_start, previous_end=previous_end,
        metrics=metrics, generated_at=datetime.now(timezone.utc),
    )


async def build_timeseries_report(
    db: AsyncSession, *, organization_id: uuid.UUID, start: datetime, end: datetime, metric: str
) -> TimeSeriesReport:
    """Daily-bucketed series with gaps filled to 0 — a missing day must read
    as "no activity", never be silently omitted as if that day didn't exist
    (MASTER PROMPT §50)."""
    conditions = [Sale.organization_id == organization_id, Sale.status == SaleStatus.COMPLETED, Sale.created_at >= start, Sale.created_at <= end]

    if metric == "transactions":
        value_expr = func.count(Sale.id)
    else:
        value_expr = func.coalesce(func.sum(Sale.total_amount), 0)

    rows = await db.execute(
        select(func.date(Sale.created_at).label("day"), value_expr.label("value")).where(*conditions).group_by("day")
    )
    by_day: dict[str, float] = {str(row.day): float(row.value) for row in rows.all()}

    points: list[TimeSeriesPoint] = []
    cursor = start.date()
    end_date = end.date()
    while cursor <= end_date:
        key = cursor.isoformat()
        points.append(TimeSeriesPoint(date=key, value=by_day.get(key, 0.0)))
        cursor += timedelta(days=1)

    return TimeSeriesReport(metric=metric, points=points, generated_at=datetime.now(timezone.utc))


async def build_heatmap_report(
    db: AsyncSession, *, organization_id: uuid.UUID, start: datetime | None, end: datetime | None
) -> HeatmapReport:
    """Sales volume by day-of-week x hour — identifies peak operating
    periods (MASTER PROMPT §55). ISODOW is 1=Monday..7=Sunday; converted to
    0-indexed Monday for a friendlier frontend grid."""
    conditions = [Sale.organization_id == organization_id, Sale.status == SaleStatus.COMPLETED]
    if start:
        conditions.append(Sale.created_at >= start)
    if end:
        conditions.append(Sale.created_at <= end)

    dow_expr = func.extract("isodow", Sale.created_at)
    hour_expr = func.extract("hour", Sale.created_at)

    rows = await db.execute(
        select(dow_expr.label("dow"), hour_expr.label("hour"), func.sum(Sale.total_amount), func.count(Sale.id))
        .where(*conditions)
        .group_by("dow", "hour")
    )

    cells = [
        HeatmapCell(day_of_week=int(row.dow) - 1, hour=int(row.hour), revenue=float(money(row[2])), transactions=int(row[3]))
        for row in rows.all()
    ]

    return HeatmapReport(cells=cells, generated_at=datetime.now(timezone.utc))


async def build_pareto_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> ParetoReport:
    """Which products make up ~80% of revenue (MASTER PROMPT §56)."""
    sale_conditions = _sale_conditions(organization_id, filters)

    rows = await db.execute(
        select(SaleItem.product_id, SaleItem.product_name, func.sum(SaleItem.line_total))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*sale_conditions)
        .group_by(SaleItem.product_id, SaleItem.product_name)
        .order_by(func.sum(SaleItem.line_total).desc())
    )
    product_rows = rows.all()

    total_revenue = sum((money(row[2]) for row in product_rows), Decimal("0"))
    lines: list[ParetoLine] = []
    running_total = Decimal("0")

    for product_id, product_name, revenue in product_rows:
        revenue = money(revenue)
        running_total += revenue
        cumulative_percent = float(money((running_total / total_revenue * 100))) if total_revenue > 0 else 0.0
        lines.append(
            ParetoLine(
                product_id=product_id,
                product_name=product_name,
                revenue=float(revenue),
                cumulative_percent=cumulative_percent,
                in_top_80_percent=cumulative_percent <= 80.0,
            )
        )

    return ParetoReport(lines=lines, generated_at=datetime.now(timezone.utc))


async def build_sales_power_report(db: AsyncSession, *, organization_id: uuid.UUID, filters: ReportFilters) -> SalesPowerReport:
    """MASTER PROMPT §54: individual sale observations as a real scatter
    dataset, plus a genuine trend/volatility/growth interpretation — never
    just a decorative chart."""
    sale_conditions = _sale_conditions(organization_id, filters)
    result = await db.execute(select(Sale.created_at, Sale.total_amount).where(*sale_conditions).order_by(Sale.created_at))
    rows = result.all()

    points = [SalesPowerPoint(timestamp=ts, value=float(money(val))) for ts, val in rows]
    if not points:
        return SalesPowerReport(
            points=[], trend_start_value=None, trend_end_value=None, trend_direction="insufficient_data",
            peak_value=None, peak_timestamp=None, weakest_value=None, weakest_timestamp=None,
            volatility=0.0, growth_percent=None,
        )

    values = [p.value for p in points]
    n = len(values)

    # Simple linear regression (x = point index) for the trend line's
    # endpoints — enough to say "growing"/"declining" without pretending
    # false statistical precision.
    if n >= 2:
        mean_x = (n - 1) / 2
        mean_y = sum(values) / n
        numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
        denominator = sum((i - mean_x) ** 2 for i in range(n))
        slope = numerator / denominator if denominator else 0.0
        intercept = mean_y - slope * mean_x
        trend_start = intercept
        trend_end = intercept + slope * (n - 1)
        direction = "flat"
        if trend_end > trend_start * 1.05:
            direction = "growing"
        elif trend_end < trend_start * 0.95:
            direction = "declining"
    else:
        trend_start = trend_end = values[0]
        direction = "insufficient_data"

    mean_value = sum(values) / n
    variance = sum((v - mean_value) ** 2 for v in values) / n
    volatility = round(variance ** 0.5, 2)

    peak_idx = max(range(n), key=lambda i: values[i])
    weak_idx = min(range(n), key=lambda i: values[i])

    growth_percent = None
    if n >= 2:
        half = n // 2
        first_half = values[:half] or values[:1]
        second_half = values[half:] or values[-1:]
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        if first_avg > 0:
            growth_percent = round(((second_avg - first_avg) / first_avg) * 100, 1)

    return SalesPowerReport(
        points=points,
        trend_start_value=round(trend_start, 2),
        trend_end_value=round(trend_end, 2),
        trend_direction=direction,
        peak_value=values[peak_idx],
        peak_timestamp=points[peak_idx].timestamp,
        weakest_value=values[weak_idx],
        weakest_timestamp=points[weak_idx].timestamp,
        volatility=volatility,
        growth_percent=growth_percent,
    )

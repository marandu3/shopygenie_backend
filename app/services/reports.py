import uuid
from datetime import datetime, timezone
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
    CustomerReport,
    CustomerSpend,
    DebtAgingBucket,
    DebtAgingReport,
    InventoryReport,
    PaymentMethodTotal,
    ProductMovementSummary,
    ReportFilters,
    SalesReport,
    SupplierPurchaseSummary,
    SupplierReport,
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

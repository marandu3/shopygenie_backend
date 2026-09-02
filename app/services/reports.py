import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.debt import Debt
from app.models.expense import Expense
from app.models.purchase import Purchase, PurchaseStatus
from app.models.sale import Sale, SaleItem, SaleStatus
from app.schemas.report import BusinessSummaryReport, ReportFilters
from app.services.money import money


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
    sale_conditions = [Sale.organization_id == organization_id, Sale.status == SaleStatus.COMPLETED]
    if filters.start_date:
        sale_conditions.append(Sale.created_at >= filters.start_date)
    if filters.end_date:
        sale_conditions.append(Sale.created_at <= filters.end_date)
    if filters.branch_id:
        sale_conditions.append(Sale.branch_id == filters.branch_id)
    if filters.customer_id:
        sale_conditions.append(Sale.customer_id == filters.customer_id)

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

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.schemas.report_builder import ALLOWED_GROUP_BY, ALLOWED_METRICS, ReportBuilderRequest, ReportBuilderResult, ReportBuilderRow
from app.services.money import money
from app.services.reports import _sale_conditions

# Metrics that need SaleItem (join required); everything else is Sale-only.
_ITEM_METRICS = {"gross_profit", "cogs", "units_sold"}


def _value_expr(metric: str):
    if metric == "revenue":
        return func.coalesce(func.sum(Sale.total_amount), 0)
    if metric == "transactions":
        return func.count(func.distinct(Sale.id))
    if metric == "cogs":
        return func.coalesce(func.sum(SaleItem.unit_cost_price * SaleItem.quantity), 0)
    if metric == "units_sold":
        return func.coalesce(func.sum(SaleItem.quantity), 0)
    if metric == "gross_profit":
        # SUM(line_total) - SUM(cost) computed post-hoc per group (see build_report), so
        # here we just need both partial sums — see the dedicated branch below.
        raise ValueError("gross_profit is computed from two sub-aggregates, not a single expression")
    raise ValueError(f"Unknown metric: {metric}")


async def build_report(db: AsyncSession, *, organization_id: uuid.UUID, request: ReportBuilderRequest) -> ReportBuilderResult:
    if request.metric not in ALLOWED_METRICS:
        raise ValidationAppError(f"Unknown metric: {request.metric}", code="INVALID_METRIC")
    if request.group_by not in ALLOWED_GROUP_BY:
        raise ValidationAppError(f"Unknown group_by: {request.group_by}", code="INVALID_GROUP_BY")

    conditions = _sale_conditions(organization_id, request.filters)
    needs_items = request.metric in _ITEM_METRICS or request.group_by == "product"

    if request.metric == "gross_profit":
        rows = await _gross_profit_rows(db, conditions, request.group_by)
    else:
        rows = await _single_metric_rows(db, conditions, request.metric, request.group_by, needs_items)

    total = money(sum(Decimal(str(r.value)) for r in rows)) if rows else Decimal("0")
    return ReportBuilderResult(metric=request.metric, group_by=request.group_by, rows=rows, total=float(total))


def _group_expr(group_by: str | None):
    if group_by == "day":
        return func.date(Sale.created_at)
    if group_by == "month":
        return func.to_char(Sale.created_at, "YYYY-MM")
    if group_by == "customer":
        return Sale.customer_id
    if group_by == "product":
        return SaleItem.product_id
    return None


async def _single_metric_rows(db, conditions, metric, group_by, needs_items) -> list[ReportBuilderRow]:
    value_expr = _value_expr(metric)
    group_expr = _group_expr(group_by)

    query = select(value_expr.label("value"))
    if group_expr is not None:
        query = query.add_columns(group_expr.label("grp"))
    query = query.select_from(Sale).where(*conditions)
    if needs_items:
        query = query.join(SaleItem, SaleItem.sale_id == Sale.id)
    if group_expr is not None:
        query = query.group_by(group_expr)

    result = await db.execute(query)
    rows_raw = result.all()

    if group_by is None:
        value = rows_raw[0][0] if rows_raw else 0
        return [ReportBuilderRow(label="Total", value=float(value))]

    labels = await _resolve_labels(db, group_by, [r[1] for r in rows_raw])
    rows = [ReportBuilderRow(label=labels.get(r[1], str(r[1])), value=float(r[0])) for r in rows_raw]
    rows.sort(key=lambda r: r.value, reverse=True)
    return rows


async def _gross_profit_rows(db, conditions, group_by) -> list[ReportBuilderRow]:
    group_expr = _group_expr(group_by)
    revenue_col = func.coalesce(func.sum(SaleItem.line_total), 0)
    cost_col = func.coalesce(func.sum(SaleItem.unit_cost_price * SaleItem.quantity), 0)

    query = select(revenue_col.label("revenue"), cost_col.label("cost"))
    if group_expr is not None:
        query = query.add_columns(group_expr.label("grp"))
    query = query.select_from(Sale).join(SaleItem, SaleItem.sale_id == Sale.id).where(*conditions)
    if group_expr is not None:
        query = query.group_by(group_expr)

    result = await db.execute(query)
    rows_raw = result.all()

    if group_by is None:
        if not rows_raw:
            return [ReportBuilderRow(label="Total", value=0.0)]
        revenue, cost = rows_raw[0][0], rows_raw[0][1]
        return [ReportBuilderRow(label="Total", value=float(money(Decimal(str(revenue)) - Decimal(str(cost)))))]

    labels = await _resolve_labels(db, group_by, [r[2] for r in rows_raw])
    rows = [
        ReportBuilderRow(label=labels.get(r[2], str(r[2])), value=float(money(Decimal(str(r[0])) - Decimal(str(r[1])))))
        for r in rows_raw
    ]
    rows.sort(key=lambda r: r.value, reverse=True)
    return rows


async def _resolve_labels(db: AsyncSession, group_by: str, ids: list) -> dict:
    """day/month groups are already human-readable strings; product/customer
    groups are UUIDs that need a name lookup."""
    if group_by in ("day", "month"):
        return {i: str(i) for i in ids}
    if group_by == "product":
        result = await db.execute(select(Product.id, Product.name).where(Product.id.in_([i for i in ids if i])))
        return {row.id: row.name for row in result.all()}
    if group_by == "customer":
        ids = [i for i in ids if i]
        if not ids:
            return {}
        result = await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(ids)))
        names = {row.id: row.name for row in result.all()}
        return {i: names.get(i, "Walk-in") for i in ids} | {None: "Walk-in"}
    return {}

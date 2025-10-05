from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from schema.report import ReportSummary, ReportFilters, ReportType
from database.config import sales_collection, purchases_collection, debts_collection, expenditures_collection

router = APIRouter()


# ---------- Helper Functions ----------
def build_query(filters: ReportFilters):
    """Build MongoDB query based on filters"""
    query = {}
    if filters.start_date and filters.end_date:
        query["date"] = {"$gte": filters.start_date, "$lte": filters.end_date}
    elif filters.start_date:
        query["date"] = {"$gte": filters.start_date}
    elif filters.end_date:
        query["date"] = {"$lte": filters.end_date}

    if filters.category:
        query["category"] = filters.category
    if filters.customer_id:
        query["customer_id"] = filters.customer_id
    if filters.product_id:
        query["product_id"] = filters.product_id
    if filters.min_amount or filters.max_amount:
        query["amount"] = {}
        if filters.min_amount:
            query["amount"]["$gte"] = filters.min_amount
        if filters.max_amount:
            query["amount"]["$lte"] = filters.max_amount

    return query


def apply_report_type(report_type: ReportType, filters: ReportFilters) -> ReportFilters:
    """Apply auto date ranges if user did not pass them"""
    now = datetime.now(timezone.utc)

    if report_type == ReportType.DAILY:
        filters.start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        filters.end_date = now
    elif report_type == ReportType.WEEKLY:
        filters.start_date = now - timedelta(days=7)
        filters.end_date = now
    elif report_type == ReportType.MONTHLY:
        filters.start_date = now - timedelta(days=30)
        filters.end_date = now
    elif report_type == ReportType.YEARLY:
        filters.start_date = now - timedelta(days=365)
        filters.end_date = now
    # CUSTOM = keep whatever user passed

    return filters


# ---------- Endpoint ----------
@router.post("/reports/generate", response_model=ReportSummary)
async def generate_report(report_type: ReportType, filters: ReportFilters):
    try:
        # Auto-apply date ranges if needed
        filters = apply_report_type(report_type, filters)

        # Build queries
        sales_query = build_query(filters)
        purchases_query = build_query(filters)
        debts_query = build_query(filters)
        expenditures_query = build_query(filters)

        # Fetch totals
        total_sales = sum([doc.get("amount", 0) for doc in sales_collection.find(sales_query, {"_id": 0, "amount": 1})])
        total_purchases = sum([doc.get("amount", 0) for doc in purchases_collection.find(purchases_query, {"_id": 0, "amount": 1})])
        total_debts = sum([doc.get("amount", 0) for doc in debts_collection.find(debts_query, {"_id": 0, "amount": 1})])
        total_expenditures = sum([doc.get("amount", 0) for doc in expenditures_collection.find(expenditures_query, {"_id": 0, "amount": 1})])

        # Compute net profit
        net_profit = (total_sales - total_purchases - total_expenditures)

        # Most/least sold product
        sales_pipeline = [
            {"$match": sales_query},
            {"$group": {"_id": "$product_id", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}}
        ]
        sales_stats = list(sales_collection.aggregate(sales_pipeline))
        most_sold_product = str(sales_stats[0]["_id"]) if sales_stats else None
        least_sold_product = str(sales_stats[-1]["_id"]) if len(sales_stats) > 1 else None

        # Best/worst customer
        customer_pipeline = [
            {"$match": sales_query},
            {"$group": {"_id": "$customer_id", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}}
        ]
        customer_stats = list(sales_collection.aggregate(customer_pipeline))
        best_customer = str(customer_stats[0]["_id"]) if customer_stats else None
        worst_customer = str(customer_stats[-1]["_id"]) if len(customer_stats) > 1 else None

        # Build final report
        report = ReportSummary(
            total_sales=total_sales,
            total_purchases=total_purchases,
            total_debts=total_debts,
            total_expenditures=total_expenditures,
            net_profit=net_profit,
            most_sold_product=most_sold_product,
            least_sold_product=least_sold_product,
            best_customer=best_customer,
            worst_customer=worst_customer,
            ReportType=report_type,
            generated_at=datetime.now(timezone.utc)
        )

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

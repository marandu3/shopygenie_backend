from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from database.config import (
    sales_collection,
    purchases_collection,
    debts_collection,
    products_collection,
    customers_collection,
    expenditures_collection
)
from schema.report import ReportSummary, ReportFilters, ReportType

router = APIRouter()

def build_base_queries(filters: ReportFilters):
    """Build base queries for all collections"""
    sales_query = {}
    purchases_query = {}
    debts_query = {}
    expenditures_query = {}

    # Date filters
    if filters.start_date:
        sales_query["created_at"] = {"$gte": filters.start_date}
        purchases_query["created_at"] = {"$gte": filters.start_date}
        debts_query["created_at"] = {"$gte": filters.start_date}
        expenditures_query["created_at"] = {"$gte": filters.start_date}
    
    if filters.end_date:
        date_filter = {"$lte": filters.end_date}
        for query in [sales_query, purchases_query, debts_query, expenditures_query]:
            if "created_at" in query:
                query["created_at"].update(date_filter)
            else:
                query["created_at"] = date_filter

    # Category filter
    if filters.category:
        sales_query["items.category"] = filters.category
        purchases_query["items.category"] = filters.category

    # Amount filters
    if filters.min_amount is not None:
        sales_query["total_amount"] = {"$gte": filters.min_amount}
        purchases_query["total_amount"] = {"$gte": filters.min_amount}
    
    if filters.max_amount is not None:
        if "total_amount" in sales_query:
            sales_query["total_amount"]["$lte"] = filters.max_amount
            purchases_query["total_amount"]["$lte"] = filters.max_amount
        else:
            sales_query["total_amount"] = {"$lte": filters.max_amount}
            purchases_query["total_amount"] = {"$lte": filters.max_amount}

    return sales_query, purchases_query, debts_query, expenditures_query

def get_customer_info(customer_id: str) -> Dict[str, Any]:
    """Get customer information by ID"""
    if customer_id and customer_id.strip():
        customer_doc = customers_collection.find_one({"id": customer_id.strip()})
        if customer_doc:
            return {
                "id": customer_doc["id"],
                "name": customer_doc["name"],
                "email": customer_doc.get("email"),
                "phone": customer_doc.get("phone")
            }
    return None

def get_product_info(product_id: int) -> Dict[str, Any]:
    """Get product information by ID"""
    if product_id:
        product_doc = products_collection.find_one({"id": product_id})
        if product_doc:
            return {
                "id": product_doc["id"],
                "name": product_doc["name"],
                "category": product_doc.get("category"),
                "price": product_doc.get("price")
            }
    return None

def apply_entity_filters(filters: ReportFilters, sales_query: Dict, purchases_query: Dict, debts_query: Dict):
    """Apply entity filters and return entity info for report title"""
    entity_info = None
    entity_type = None
    
    # Customer filter
    if filters.customer_id and filters.customer_id.strip():
        customer_info = get_customer_info(filters.customer_id)
        if not customer_info:
            raise HTTPException(status_code=404, detail=f"Customer with ID {filters.customer_id} not found")
        
        sales_query["customer_id"] = filters.customer_id.strip()
        debts_query["customer_name"] = customer_info["name"]
        entity_info = customer_info
        entity_type = "customer"
    
    # Product filter
    elif filters.product_id:
        product_info = get_product_info(filters.product_id)
        if not product_info:
            raise HTTPException(status_code=404, detail=f"Product with ID {filters.product_id} not found")
        
        product_id_str = str(filters.product_id)
        sales_query["items.product_id"] = product_id_str
        purchases_query["items.product_id"] = product_id_str
        entity_info = product_info
        entity_type = "product"
    
    return entity_info, entity_type

def generate_report_title(filters: ReportFilters, entity_info: Dict[str, Any], entity_type: str, report_type: ReportType) -> str:
    """Generate appropriate report title based on filters and entity"""
    
    # Base title for entity-specific reports
    if entity_type == "customer" and entity_info:
        return f"Customer Report: {entity_info['name']}"
    elif entity_type == "product" and entity_info:
        return f"Product Report: {entity_info['name']}"
    
    # Category-specific report
    elif filters.category:
        return f"Category Report: {filters.category}"
    
    # Date-specific reports
    elif filters.start_date and filters.end_date:
        date_format = "%Y-%m-%d"
        start_str = filters.start_date.strftime(date_format)
        end_str = filters.end_date.strftime(date_format)
        
        if report_type == ReportType.DAILY:
            return f"Daily Report: {start_str}"
        elif report_type == ReportType.WEEKLY:
            return f"Weekly Report: {start_str} to {end_str}"
        elif report_type == ReportType.MONTHLY:
            return f"Monthly Report: {filters.start_date.strftime('%B %Y')}"
        elif report_type == ReportType.YEARLY:
            return f"Yearly Report: {filters.start_date.strftime('%Y')}"
        else:
            return f"Custom Period Report: {start_str} to {end_str}"
    
    # Amount-filtered report
    elif filters.min_amount is not None or filters.max_amount is not None:
        amount_filters = []
        if filters.min_amount is not None:
            amount_filters.append(f"Min: ${filters.min_amount}")
        if filters.max_amount is not None:
            amount_filters.append(f"Max: ${filters.max_amount}")
        return f"Amount Filtered Report ({', '.join(amount_filters)})"
    
    # General report
    return "General Business Report"

def calculate_financial_metrics(sales_data: List, purchases_data: List, debts_data: List, expenditures_data: List):
    """Calculate financial metrics from the data"""
    total_sales = sum(sale.get("total_amount", 0) for sale in sales_data)
    total_purchases = sum(purchase.get("total_amount", 0) for purchase in purchases_data)
    total_debts = sum(debt.get("amount", 0) for debt in debts_data)
    total_expenditures = total_purchases + total_debts + sum(exp.get("amount", 0) for exp in expenditures_data)
    net_profit = total_sales - total_expenditures
    
    return total_sales, total_purchases, total_debts, total_expenditures, net_profit

def calculate_customer_metrics(sales_data: List, is_customer_specific: bool = False):
    """Calculate customer-related metrics"""
    # For customer-specific reports, don't calculate best/worst customer
    if is_customer_specific:
        total_customers = 1
        return total_customers, None, None
    
    total_customers = len(set(sale.get("customer_id") for sale in sales_data if sale.get("customer_id")))
    
    best_customer = worst_customer = None
    if sales_data:
        customer_totals = {}
        for sale in sales_data:
            cid = sale.get("customer_id")
            if cid:
                customer_totals[cid] = customer_totals.get(cid, 0) + sale.get("total_amount", 0)
        
        if customer_totals:
            best_customer_id = max(customer_totals, key=customer_totals.get)
            worst_customer_id = min(customer_totals, key=customer_totals.get)
            
            best_customer_doc = customers_collection.find_one({"id": best_customer_id})
            worst_customer_doc = customers_collection.find_one({"id": worst_customer_id})
            
            best_customer = best_customer_doc["name"] if best_customer_doc else best_customer_id
            worst_customer = worst_customer_doc["name"] if worst_customer_doc else worst_customer_id
    
    return total_customers, best_customer, worst_customer

def calculate_product_metrics(sales_data: List, is_product_specific: bool = False):
    """Calculate product-related metrics"""
    total_products_sold = sum(
        item.get("quantity", 0) 
        for sale in sales_data 
        for item in sale.get("items", [])
    )
    
    # For product-specific reports, don't calculate most/least sold products
    if is_product_specific:
        return total_products_sold, None, None
    
    most_sold_product = least_sold_product = None
    if sales_data:
        product_counts = {}
        for sale in sales_data:
            for item in sale.get("items", []):
                pid = item.get("product_id")
                qty = item.get("quantity", 0)
                if pid:
                    product_counts[pid] = product_counts.get(pid, 0) + qty
        
        if product_counts:
            most_pid = max(product_counts, key=product_counts.get)
            least_pid = min(product_counts, key=product_counts.get)
            
            most_product_doc = products_collection.find_one({"id": int(most_pid)})
            least_product_doc = products_collection.find_one({"id": int(least_pid)})
            
            most_sold_product = most_product_doc["name"] if most_product_doc else str(most_pid)
            least_sold_product = least_product_doc["name"] if least_product_doc else str(least_pid)
    
    return total_products_sold, most_sold_product, least_sold_product

def determine_report_type(filters: ReportFilters):
    """Determine the report type based on filters"""
    if filters.start_date and filters.end_date:
        delta = filters.end_date - filters.start_date
        if delta.days == 0:
            return ReportType.DAILY
        elif delta.days <= 7:
            return ReportType.WEEKLY
        elif delta.days <= 31:
            return ReportType.MONTHLY
        elif delta.days >= 365:
            return ReportType.YEARLY
    
    return ReportType.CUSTOM

@router.post("/report", response_model=ReportSummary)
async def generate_report(filters: ReportFilters = ReportFilters()):
    """
    Generate comprehensive business report with optional filters.
    
    When no filters are applied: Returns General Business Report
    When customer_id filter is applied: Returns "Customer Report: [Customer Name]"
    When product_id filter is applied: Returns "Product Report: [Product Name]"
    When other filters are applied: Returns appropriate titled report
    
    - **start_date**: Start date for the report period
    - **end_date**: End date for the report period  
    - **category**: Filter by product category
    - **customer_id**: Filter by specific customer
    - **product_id**: Filter by specific product
    - **min_amount**: Minimum transaction amount
    - **max_amount**: Maximum transaction amount
    """
    try:
        # Build base queries
        sales_query, purchases_query, debts_query, expenditures_query = build_base_queries(filters)
        
        # Apply entity-specific filters and get entity info for report title
        entity_info, entity_type = apply_entity_filters(filters, sales_query, purchases_query, debts_query)
        
        # Fetch data from all collections
        sales_data = list(sales_collection.find(sales_query, {"_id": 0}))
        purchases_data = list(purchases_collection.find(purchases_query, {"_id": 0}))
        debts_data = list(debts_collection.find(debts_query, {"_id": 0}))
        expenditures_data = list(expenditures_collection.find(expenditures_query, {"_id": 0}))
        
        # Calculate metrics
        total_sales, total_purchases, total_debts, total_expenditures, net_profit = calculate_financial_metrics(
            sales_data, purchases_data, debts_data, expenditures_data
        )
        
        # Determine if this is a specific entity report
        is_customer_specific = entity_type == "customer"
        is_product_specific = entity_type == "product"
        
        total_customers, best_customer, worst_customer = calculate_customer_metrics(
            sales_data, is_customer_specific
        )
        total_products_sold, most_sold_product, least_sold_product = calculate_product_metrics(
            sales_data, is_product_specific
        )
        
        # Calculate additional metrics
        average_sale_amount = total_sales / len(sales_data) if sales_data else 0.0
        total_transactions = len(sales_data) + len(purchases_data)
        
        # Determine report type and generate title
        report_type = determine_report_type(filters)
        report_title = generate_report_title(filters, entity_info, entity_type, report_type)
        
        # Build applied filters info
        applied_filters = {}
        if filters.start_date:
            applied_filters["start_date"] = filters.start_date
        if filters.end_date:
            applied_filters["end_date"] = filters.end_date
        if filters.category:
            applied_filters["category"] = filters.category
        if filters.customer_id:
            applied_filters["customer_id"] = filters.customer_id
        if filters.product_id:
            applied_filters["product_id"] = filters.product_id
        if filters.min_amount is not None:
            applied_filters["min_amount"] = filters.min_amount
        if filters.max_amount is not None:
            applied_filters["max_amount"] = filters.max_amount
        
        # Construct and return report
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
            total_customers=total_customers,
            total_products_sold=total_products_sold,
            average_sale_amount=average_sale_amount,
            total_transactions=total_transactions,
            report_type=report_type,
            report_title=report_title,
            applied_filters=applied_filters,
            generated_at=datetime.now(timezone.utc)
        )
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")

@router.get("/report/general", response_model=ReportSummary)
async def get_general_report():
    """
    Generate a general overview report without any filters.
    This provides a high-level summary of the entire business.
    """
    return await generate_report(ReportFilters())
from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timezone
from database.config import sales_collection, products_collection, customers_collection, debts_collection
from schema.sales import Sale, CreateSale, SaleItem
from schema.debts import Debt
from utils.idincrement import increment_id
from pymongo.collection import ReturnDocument

router = APIRouter()


@router.post("/sale", response_model=Sale)
async def create_sale(sale: CreateSale):
    new_sale_id = increment_id(sales_collection)

    # Fetch customer
    customer = customers_collection.find_one({"id": sale.customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer with ID {sale.customer_id} not found")

    total_amount = 0.0
    updated_items = []

    # Loop through products
    for item in sale.items:
        product = products_collection.find_one({"id": item.product_id})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {item.product_id} not found")

        # Stock check
        current_stock = product.get("current_stock", 0)
        if current_stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough stock for product {product['name']}. "
                       f"Available: {current_stock}, requested: {item.quantity}"
            )

        # Prices with discount
        selling_price = product["selling_price"]
        total_price = (selling_price - item.discount) * item.quantity

        # Update stock
        new_stock = current_stock - item.quantity
        products_collection.update_one(
            {"id": item.product_id},
            {"$set": {"current_stock": new_stock, "updated_at": datetime.now(timezone.utc)}}
        )

        updated_items.append(SaleItem(
            product_id=item.product_id,
            product_name=product["name"],
            quantity=item.quantity,
            selling_price=selling_price,
            discount=item.discount,
            total_price=total_price
        ).model_dump())

        total_amount += total_price

    # Final Sale Document
    sale_dict = {
        "id": new_sale_id,
        "customer_id": sale.customer_id,
        "customer_name": customer["name"],
        "items": updated_items,
        "payment_method": sale.payment_method,
        "total_amount": total_amount,
        "created_at": datetime.now(timezone.utc)
    }

    # Save sale
    sales_collection.insert_one(sale_dict)

    # Handle Debt if payment_method = debt
    if sale.payment_method == "debt":
        new_debt_id = increment_id(debts_collection)
        previous_balance = customer.get("balance", 0.0)
        new_balance = previous_balance + total_amount

        debt_dict = {
            "id": new_debt_id,
            "customer_name": customer["name"],
            "sale_id": new_sale_id,
            "amount": total_amount,
            "cleared": False,
            "balance": new_balance,
            "payment": [],
            "created_at": datetime.now(timezone.utc)
        }

        debts_collection.insert_one(debt_dict)

        # Update customer balance
        customers_collection.update_one(
            {"id": sale.customer_id},
            {"$set": {"balance": new_balance}}
        )

    return Sale(**sale_dict)


@router.get("/sales", response_model=List[Sale])
async def get_all_sales():
    sales = list(sales_collection.find({}, {"_id": 0}))
    if not sales:
        raise HTTPException(status_code=404, detail="No sales found")
    return [Sale(**sale) for sale in sales]


@router.get("/sales/{sale_id}", response_model=Sale)
async def get_sale_by_id(sale_id: str):
    sale = sales_collection.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return Sale(**sale)

# routers/purchase_router.py
from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timezone
from database.config import purchases_collection, products_collection
from schema.purchase import Purchase, PurchaseItem
from utils.idincrement import increment_id

router = APIRouter()


@router.post("/purchase", response_model=Purchase)
async def create_purchase(purchase: Purchase):
    new_purchase_id = increment_id(purchases_collection)
    purchase_dict = purchase.model_dump()
    purchase_dict["id"] = new_purchase_id
    purchase_dict["created_at"] = datetime.now(timezone.utc)

    total_amount = 0.0
    updated_items = []

    # Process each item
    for item in purchase.items:
        product = products_collection.find_one({"id": item.product_id})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product with ID {item.product_id} not found")

        # Auto-fill details
        cost_price = product["cost_price"]
        product_name = product["name"]
        total_cost = cost_price * item.quantity

        # Update stock
        new_stock = product.get("current_stock", 0) + item.quantity
        products_collection.update_one(
            {"id": item.product_id},
            {"$set": {"current_stock": new_stock, "updated_at": datetime.now(timezone.utc)}}
        )

        updated_items.append(PurchaseItem(
            product_id=item.product_id,
            quantity=item.quantity,
            cost_price=cost_price,
            total_cost=total_cost,
            product_name=product_name
        ).model_dump())

        total_amount += total_cost

    purchase_dict["items"] = updated_items
    purchase_dict["total_amount"] = total_amount

    purchases_collection.insert_one(purchase_dict)
    return Purchase(**purchase_dict)


@router.get("/purchases", response_model=List[Purchase])
async def get_all_purchases():
    purchases = list(purchases_collection.find({}, {"_id": 0}))
    if not purchases:
        raise HTTPException(status_code=404, detail="No purchases found")
    return [Purchase(**purchase) for purchase in purchases]


@router.get("/purchases/{purchase_id}", response_model=Purchase)
async def get_purchase_by_id(purchase_id: str):
    purchase = purchases_collection.find_one({"id": purchase_id}, {"_id": 0})
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return Purchase(**purchase)


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str):
    result = purchases_collection.delete_one({"id": purchase_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return {"detail": "Purchase deleted successfully"}

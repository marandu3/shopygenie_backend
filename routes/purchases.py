from fastapi import APIRouter, HTTPException
from typing import List
from database.config import purchases_collection
from schema.purchase import Purchase
from datetime import datetime, timezone
from utils.idincrement import increment_id

router = APIRouter()


# Create a new purchase
@router.post("/purchase", response_model=Purchase)
async def create_purchase(purchase: Purchase):
    new_purchase_id = increment_id(purchases_collection)
    purchase_dict = purchase.model_dump()
    purchase_dict["id"] = new_purchase_id
    purchase_dict["created_at"] = datetime.now(timezone.utc)

    purchases_collection.insert_one(purchase_dict)
    return Purchase(**purchase_dict)


# Get all purchases
@router.get("/purchases", response_model=List[Purchase])
async def get_all_purchases():
    purchases = list(purchases_collection.find({}, {"_id": 0}))
    if not purchases:
        raise HTTPException(status_code=404, detail="No purchases found")
    return [Purchase(**purchase) for purchase in purchases]


# Get purchase by ID
@router.get("/purchases/{purchase_id}", response_model=Purchase)
async def get_purchase_by_id(purchase_id: str):
    purchase = purchases_collection.find_one({"id": purchase_id}, {"_id": 0})
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return Purchase(**purchase)


# Update purchase
@router.put("/purchases/{purchase_id}", response_model=Purchase)
async def update_purchase(purchase_id: str, purchase: Purchase):
    update_data = purchase.model_dump(exclude_unset=True)

    updated_purchase = purchases_collection.find_one_and_update(
        {"id": purchase_id},
        {"$set": update_data},
        return_document=True,
        projection={"_id": 0}
    )
    if not updated_purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return Purchase(**updated_purchase)


# Delete purchase
@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str):
    result = purchases_collection.delete_one({"id": purchase_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return {"detail": "Purchase deleted successfully"}

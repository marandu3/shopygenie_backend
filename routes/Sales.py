from fastapi import APIRouter, HTTPException
from typing import List
from database.config import sales_collection
from schema.sales import Sale, create_Sale
from datetime import datetime, timezone
from utils.idincrement import increment_id
from pymongo.collection import ReturnDocument

router = APIRouter()


# Create a new sale
@router.post("/sale", response_model=Sale)
async def create_sale(sale: create_Sale):
    new_sale_id = increment_id(sales_collection)
    sale_dict = sale.model_dump()
    sale_dict["id"] = new_sale_id
    sale_dict["created_at"] = datetime.now(timezone.utc)

    sales_collection.insert_one(sale_dict)
    return Sale(**sale_dict)


# Get all sales
@router.get("/sales", response_model=List[Sale])
async def get_all_sales():
    sales = list(sales_collection.find({}, {"_id": 0}))
    if not sales:
        raise HTTPException(status_code=404, detail="No sales found")
    return [Sale(**sale) for sale in sales]


# Get sale by ID
@router.get("/sales/{sale_id}", response_model=Sale)
async def get_sale_by_id(sale_id: str):
    sale = sales_collection.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return Sale(**sale)


# Update sale
@router.put("/sales/{sale_id}", response_model=Sale)
async def update_sale(sale_id: str, sale: Sale):
    update_data = sale.model_dump(exclude_unset=True)

    updated_sale = sales_collection.find_one_and_update(
        {"id": sale_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0}
    )
    if not updated_sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return Sale(**updated_sale)

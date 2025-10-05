from fastapi import APIRouter, Depends, HTTPException
from utils.idincrement import increment_id
from database.config import expenditures_collection
from schema.expenditure import Expenditure
from typing import List
from datetime import datetime, timezone

router = APIRouter()

# ──────────────────────────────────────────────
# Create a new expenditure entry
@router.post("/expenditures", response_model=Expenditure, status_code=201)
async def create_expenditure(expenditure: Expenditure): 
    try:
        # prevent duplicate expenditure entry for same description/amount/date
        if expenditures_collection.find_one(
            {"description": expenditure.description, "amount": expenditure.amount, "date": expenditure.date}
        ):
            raise HTTPException(status_code=400, detail="Expenditure entry already exists")

        new_expenditure_id = str(increment_id(expenditures_collection))  # always string ID
        expenditure_dict = expenditure.model_dump()
        expenditure_dict.update({
            "id": new_expenditure_id,
            "created_at": datetime.now(timezone.utc),
        })

        expenditures_collection.insert_one(expenditure_dict)
        return Expenditure(**expenditure_dict)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create expenditure: {str(e)}")
    
# ──────────────────────────────────────────────
# Get all expenditures
@router.get("/expenditures", response_model=List[Expenditure])
async def get_expenditures():
    expenditures = list(expenditures_collection.find({}, {"_id": 0}))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Get expenditure by ID
@router.get("/expenditures/{expenditure_id}", response_model=Expenditure)
async def get_expenditure_by_id(expenditure_id: str):
    expenditure = expenditures_collection.find_one({"id": expenditure_id}, {"_id": 0})
    if not expenditure:
        raise HTTPException(status_code=404, detail="Expenditure entry not found")
    return Expenditure(**expenditure)

# ──────────────────────────────────────────────
# Delete expenditure by ID
@router.delete("/expenditures/{expenditure_id}", status_code=204)
async def delete_expenditure(expenditure_id: str):
    result = expenditures_collection.delete_one({"id": expenditure_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expenditure entry not found")
    return
# ──────────────────────────────────────────────    
# Get expenditures by category
@router.get("/expenditures/category/{category}", response_model=List[Expenditure])
async def get_expenditures_by_category(category: str):
    expenditures = list(expenditures_collection.find({"category": category}, {"_id": 0}))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found for this category")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Get expenditures by date range
@router.get("/expenditures/date-range/", response_model=List[Expenditure])
async def get_expenditures_by_date_range(start_date: datetime, end_date: datetime):
    expenditures = list(expenditures_collection.find(
        {"date": {"$gte": start_date, "$lte": end_date}}, {"_id": 0}
    ))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found in this date range")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Update expenditure entry
@router.put("/expenditures/{expenditure_id}", response_model=Expenditure)
async def update_expenditure(expenditure_id: str, expenditure: Expenditure):
    update_data = expenditure.model_dump(exclude_unset=True)
    update_data["date"] = update_data.get("date", datetime.now(timezone.utc))
    update_data["updated_at"] = datetime.now(timezone.utc)

    updated_expenditure = expenditures_collection.find_one_and_update(
        {"id": expenditure_id},
        {"$set": update_data},
        return_document=True,
        projection={"_id": 0},
    )
    if not updated_expenditure:
        raise HTTPException(status_code=404, detail="Expenditure entry not found")
    return Expenditure(**updated_expenditure)

# ──────────────────────────────────────────────
# Delete all expenditures (use with caution)
@router.delete("/expenditures", status_code=204)
async def delete_all_expenditures():
    expenditures_collection.delete_many({})
    return  

# ──────────────────────────────────────────────
# Get total expenditure amount
@router.get("/expenditures/total-amount", response_model=float)
async def get_total_expenditure_amount():
    total = expenditures_collection.aggregate([
        {"$group": {"_id": None, "total_amount": {"$sum": "$amount"}}}
    ])
    total_amount = next(total, {}).get("total_amount", 0.0)
    return total_amount

# ──────────────────────────────────────────────
# Get average expenditure amount
@router.get("/expenditures/average-amount", response_model=float)
async def get_average_expenditure_amount():
    average = expenditures_collection.aggregate([
        {"$group": {"_id": None, "average_amount": {"$avg": "$amount"}}}
    ])
    average_amount = next(average, {}).get("average_amount", 0.0)
    return average_amount

# ──────────────────────────────────────────────
# Get expenditure count
@router.get("/expenditures/count", response_model=int)
async def get_expenditure_count():
    count = expenditures_collection.count_documents({})
    return count

# ──────────────────────────────────────────────
# Get expenditures sorted by amount
@router.get("/expenditures/sorted-by-amount", response_model=List[Expenditure])
async def get_expenditures_sorted_by_amount(descending: bool = False):
    sort_order = -1 if descending else 1
    expenditures = list(expenditures_collection.find({}, {"_id": 0}).sort("amount", sort_order))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found")
    return [Expenditure(**expenditure) for expenditure in expenditures] 

# ──────────────────────────────────────────────
# Get expenditures sorted by date
@router.get("/expenditures/sorted-by-date", response_model=List[Expenditure])
async def get_expenditures_sorted_by_date(descending: bool = False):    
    sort_order = -1 if descending else 1
    expenditures = list(expenditures_collection.find({}, {"_id": 0}).sort("date", sort_order))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Get expenditures with amount greater than a specified value
@router.get("/expenditures/amount-greater-than/{amount}", response_model=List[Expenditure])
async def get_expenditures_amount_greater_than(amount: float):
    expenditures = list(expenditures_collection.find({"amount": {"$gt": amount}}, {"_id": 0}))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found with amount greater than specified value")
    return [Expenditure(**expenditure) for expenditure in expenditures] 

# ──────────────────────────────────────────────
# Get expenditures with amount less than a specified value
@router.get("/expenditures/amount-less-than/{amount}", response_model=List[Expenditure])
async def get_expenditures_amount_less_than(amount: float):
    expenditures = list(expenditures_collection.find({"amount": {"$lt": amount}}, {"_id": 0}))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found with amount less than specified value")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Get expenditures with amount equal to a specified value
@router.get("/expenditures/amount-equal-to/{amount}", response_model=List[Expenditure])
async def get_expenditures_amount_equal_to(amount: float):
    expenditures = list(expenditures_collection.find({"amount": amount}, {"_id": 0}))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found with amount equal to specified value")
    return [Expenditure(**expenditure) for expenditure in expenditures]

# ──────────────────────────────────────────────
# Get latest expenditure entries (most recent first)
@router.get("/expenditures/latest", response_model=List[Expenditure])
async def get_latest_expenditures(limit: int = 5):
    expenditures = list(expenditures_collection.find({}, {"_id": 0}).sort("date", -1).limit(limit))
    if not expenditures:
        raise HTTPException(status_code=404, detail="No expenditures found")
    return [Expenditure(**expenditure) for expenditure in expenditures]
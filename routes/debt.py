from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime, timezone
from pymongo.collection import ReturnDocument

from database.config import debts_collection
from schema.debts import Debt
from utils.idincrement import increment_id

router = APIRouter()


# ──────────────────────────────────────────────
# Create a new debt entry
@router.post("/debts", response_model=Debt, status_code=status.HTTP_201_CREATED)
async def create_debt(debt: Debt):
    try:
        # prevent duplicate debt entry for same customer/amount/due_date
        if debts_collection.find_one(
            {"customer_id": debt.customer_id, "amount": debt.amount, "due_date": debt.due_date}
        ):
            raise HTTPException(status_code=400, detail="Debt entry already exists")

        new_debt_id = str(increment_id(debts_collection))  # always string ID
        debt_dict = debt.model_dump()
        debt_dict.update({
            "id": new_debt_id,
            "status": debt_dict.get("status", "unpaid"),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })

        debts_collection.insert_one(debt_dict)
        return Debt(**debt_dict)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create debt: {str(e)}")


# ──────────────────────────────────────────────
# Get all debts
@router.get("/debts", response_model=List[Debt])
async def get_debts():
    debts = list(debts_collection.find({}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No debts found")
    return [Debt(**debt) for debt in debts]


# ──────────────────────────────────────────────
# Get debt by ID
@router.get("/debts/{debt_id}", response_model=Debt)
async def get_debt_by_id(debt_id: str):
    debt = debts_collection.find_one({"id": debt_id}, {"_id": 0})
    if not debt:
        raise HTTPException(status_code=404, detail="Debt entry not found")
    return Debt(**debt)


# ──────────────────────────────────────────────
# Get debts by customer ID
@router.get("/debts/customer/{customer_id}", response_model=List[Debt])
async def get_debts_by_customer(customer_id: str):
    debts = list(debts_collection.find({"customer_id": customer_id}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No debts found for this customer")
    return [Debt(**debt) for debt in debts]


# ──────────────────────────────────────────────
# Update debt entry
@router.put("/debts/{debt_id}", response_model=Debt)
async def update_debt(debt_id: str, debt: Debt):
    update_data = debt.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    updated_debt = debts_collection.find_one_and_update(
        {"id": debt_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not updated_debt:
        raise HTTPException(status_code=404, detail="Debt entry not found")
    return Debt(**updated_debt)


# ──────────────────────────────────────────────
# Delete debt entry
@router.delete("/debts/{debt_id}")
async def delete_debt(debt_id: str):
    result = debts_collection.delete_one({"id": debt_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Debt entry not found")
    return {"detail": "Debt entry deleted successfully"}


# ──────────────────────────────────────────────
# Mark as paid
@router.put("/debts/{debt_id}/pay", response_model=Debt)
async def pay_debt(debt_id: str):
    updated_debt = debts_collection.find_one_and_update(
        {"id": debt_id},
        {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not updated_debt:
        raise HTTPException(status_code=404, detail="Debt entry not found")
    return Debt(**updated_debt)


# ──────────────────────────────────────────────
# Mark as unpaid
@router.put("/debts/{debt_id}/unpay", response_model=Debt)
async def unpay_debt(debt_id: str):
    updated_debt = debts_collection.find_one_and_update(
        {"id": debt_id},
        {"$set": {"status": "unpaid", "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not updated_debt:
        raise HTTPException(status_code=404, detail="Debt entry not found")
    return Debt(**updated_debt)


# ──────────────────────────────────────────────
# Get unpaid debts
@router.get("/debts/unpaid", response_model=List[Debt])
async def get_unpaid_debts():
    debts = list(debts_collection.find({"status": "unpaid"}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No unpaid debts found")
    return [Debt(**debt) for debt in debts]


# ──────────────────────────────────────────────
# Get paid debts
@router.get("/debts/paid", response_model=List[Debt])
async def get_paid_debts():
    debts = list(debts_collection.find({"status": "paid"}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No paid debts found")
    return [Debt(**debt) for debt in debts]


# ──────────────────────────────────────────────
# Total debts
@router.get("/debts/total", response_model=float)
async def get_total_debt():
    result = list(debts_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]))
    return float(result[0]["total"]) if result else 0.0


# ──────────────────────────────────────────────
# Total unpaid debts
@router.get("/debts/total/unpaid", response_model=float)
async def get_total_unpaid_debt():
    result = list(debts_collection.aggregate([
        {"$match": {"status": "unpaid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]))
    return float(result[0]["total"]) if result else 0.0


# ──────────────────────────────────────────────
# Total paid debts
@router.get("/debts/total/paid", response_model=float)
async def get_total_paid_debt():
    result = list(debts_collection.aggregate([
        {"$match": {"status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]))
    return float(result[0]["total"]) if result else 0.0

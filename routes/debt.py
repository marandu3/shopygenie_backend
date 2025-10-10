from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timezone
from pymongo.collection import ReturnDocument
from database.config import debts_collection, customers_collection
from schema.debts import Debt, DebtPayment
from utils.idincrement import increment_id

router = APIRouter()


# Get all debts
@router.get("/debts", response_model=List[Debt])
async def get_all_debts():
    debts = list(debts_collection.find({}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No debts found")
    return [Debt(**debt) for debt in debts]


# Get debt by ID
@router.get("/debts/{debt_id}", response_model=Debt)
async def get_debt_by_id(debt_id: str):
    debt = debts_collection.find_one({"id": debt_id}, {"_id": 0})
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")
    return Debt(**debt)


# Get debts by customer
@router.get("/debts/customer/{customer_id}", response_model=List[Debt])
async def get_debts_by_customer(customer_id: str):
    customer = customers_collection.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    debts = list(debts_collection.find({"customer_name": customer["name"]}, {"_id": 0}))
    if not debts:
        raise HTTPException(status_code=404, detail="No debts found for this customer")
    return [Debt(**debt) for debt in debts]


# Partial or full payment
@router.put("/debts/{debt_id}/pay", response_model=Debt)
async def pay_debt(debt_id: str, amount: float):
    debt = debts_collection.find_one({"id": debt_id})
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    new_balance = max(0, debt["balance"] - amount)
    cleared = new_balance == 0

    payment_record = DebtPayment(
        amount=amount,
        date=datetime.now(timezone.utc),
        method="cash"
    ).model_dump()

    updated_debt = debts_collection.find_one_and_update(
        {"id": debt_id},
        {"$set": {"balance": new_balance, "cleared": cleared, "updated_at": datetime.now(timezone.utc)},
         "$push": {"payment": payment_record}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )

    # Update customer balance
    customer = customers_collection.find_one({"name": debt["customer_name"]})
    if customer:
        customers_collection.update_one(
            {"id": customer["id"]},
            {"$set": {"balance": new_balance}}
        )

    return Debt(**updated_debt)


# Delete debt (only for corrections)
@router.delete("/debts/{debt_id}")
async def delete_debt(debt_id: str):
    result = debts_collection.delete_one({"id": debt_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Debt not found")
    return {"detail": "Debt deleted successfully"}


# Aggregate totals
@router.get("/debts/total", response_model=float)
async def get_total_debt():
    result = list(debts_collection.aggregate([{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]))
    return float(result[0]["total"]) if result else 0.0


@router.get("/debts/total/unpaid", response_model=float)
async def get_total_unpaid_debt():
    result = list(debts_collection.aggregate([
        {"$match": {"cleared": False}},
        {"$group": {"_id": None, "total": {"$sum": "$balance"}}},
    ]))
    return float(result[0]["total"]) if result else 0.0


@router.get("/debts/total/paid", response_model=float)
async def get_total_paid_debt():
    result = list(debts_collection.aggregate([
        {"$match": {"cleared": True}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]))
    return float(result[0]["total"]) if result else 0.0

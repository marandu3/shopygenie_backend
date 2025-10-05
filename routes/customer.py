from fastapi import APIRouter, Depends, HTTPException
from database.config import customers_collection
from schema.customers import Customer
from typing import List
from utils.idincrement import increment_id

router = APIRouter()

# Create a new customer
@router.post("/customer", response_model=Customer)
async def create_customer(customer: Customer):
    if customers_collection.find_one({"name": customer.name}):
        raise HTTPException(status_code=400, detail="Customer with this email already exists")

    new_customer_id = increment_id(customers_collection)
    customer_dict = customer.model_dump()
    customer_dict["id"] = new_customer_id

    customers_collection.insert_one(customer_dict)
    return Customer(**customer_dict)

# Get all customers
@router.get("/customers", response_model=List[Customer])
async def get_all_customers():
    customers = list(customers_collection.find({}, {"_id": 0}))
    if not customers:
        raise HTTPException(status_code=404, detail="No customers found")
    return [Customer(**customer) for customer in customers]

# Get customer by ID
@router.get("/customers/{customer_id}", response_model=Customer)
async def get_customer_by_id(customer_id: str):
    customer = customers_collection.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return Customer(**customer)

# Update customer
@router.put("/customers/{customer_id}", response_model=Customer)
async def update_customer(customer_id: str, customer: Customer):
    update_data = customer.model_dump(exclude_unset=True)

    updated_customer = customers_collection.find_one_and_update(
        {"id": customer_id},
        {"$set": update_data},
        return_document=True,
        projection={"_id": 0}
    )
    if not updated_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return Customer(**updated_customer)

# Delete customer
@router.delete("/customers/{customer_id}")
async def delete_customer(customer_id: str):
    result = customers_collection.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"detail": "Customer deleted successfully"}


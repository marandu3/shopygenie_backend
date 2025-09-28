from fastapi import APIRouter, Depends, HTTPException
from typing import List
from database.config import products_collection
from schema.products import ProductSchema
from utils.idincrement import increment_product_id
from datetime import datetime, timezone

router = APIRouter()

@router.post("/product", response_model=ProductSchema)
async def create_product(product: ProductSchema):
    # Check if product exists by name
    if products_collection.find_one({"name": product.name}):
        raise HTTPException(status_code=400, detail="Product already exists")

    # Generate new product id
    new_product_id = increment_product_id()

    # Convert to dict
    product_dict = product.model_dump()

    # Override id and timestamps
    product_dict["id"] = str(new_product_id)
    product_dict["created_at"] = datetime.now(timezone.utc)
    product_dict["updated_at"] = datetime.now(timezone.utc)

    # Insert into MongoDB
    products_collection.insert_one(product_dict)

    # Return as ProductSchema
    return ProductSchema(**product_dict)


@router.get("/products", response_model=List[ProductSchema])
async def get_all_products():
    products = list(products_collection.find())
    if not products:
        raise HTTPException(status_code=404, detail="No products found")
    return [ProductSchema(**product) for product in products]

@router.get("/products/{product_id}", response_model=ProductSchema)
async def get_product_by_id(product_id: int):
    product = products_collection.find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductSchema(**product)

@router.put("/products/{product_id}", response_model=ProductSchema)
async def update_product(product_id: int, product: ProductSchema):
    update_data = product.model_dump(exclude_unset=True)

    # Update the updated_at timestamp
    update_data["updated_at"] = datetime.now(timezone.utc)

    updated_product = products_collection.find_one_and_update(
        {"id": product_id},
        {"$set": update_data},
        return_document=True
    )

    if not updated_product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductSchema(**updated_product)

@router.delete("/products/{product_id}")
async def delete_product(product_id: int):
    result = products_collection.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"detail": "Product deleted successfully"}

@router.get("/stock/levels")
async def get_stock_levels():
    products = list(products_collection.find({}, {"_id": 0, "name": 1, "current_stock": 1, "low_stock_alert": 1}))
    if not products:
        raise HTTPException(status_code=404, detail="No products found")
    return products


#return total stock valuation (sum of current_stock * cost_price for all products) and per product valuation
@router.get("/stock/valuation")
async def get_stock_valuation():
    products = list(products_collection.find({}, {"_id": 0, "name": 1, "current_stock": 1, "cost_price": 1}))
    if not products:
        raise HTTPException(status_code=404, detail="No products found")

    total_valuation = 0.0
    product_valuations = []

    for product in products:
        valuation = product["current_stock"] * product["cost_price"]
        total_valuation += valuation
        product_valuations.append({
            "name": product["name"],
            "current_stock": product["current_stock"],
            "cost_price": product["cost_price"],
            "valuation": valuation
        })

    return {
        "total_valuation": total_valuation,
        "product_valuations": product_valuations
    }

#return products that are below their low_stock_alert level
@router.get("/stock/low")
async def get_low_stock_products():
    products = list(products_collection.find({
        "$expr": {
            "$lt": ["$current_stock", "$low_stock_alert"]
        }
    }, {"_id": 0, "name": 1, "current_stock": 1, "low_stock_alert": 1}))

    if not products:
        raise HTTPException(status_code=404, detail="No low stock products found")

    return products
    

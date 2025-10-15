from fastapi import APIRouter, HTTPException
from typing import List
from database.config import products_collection
from schema.products import ProductSchema
from utils.idincrement import increment_id
from datetime import datetime, timezone

router = APIRouter()


# Create a new product
@router.post("/product", response_model=ProductSchema)
async def create_product(product: ProductSchema):
    if products_collection.find_one({"name": product.name}):
        raise HTTPException(status_code=400, detail="Product already exists")

    new_product_id = increment_id(products_collection)

    product_dict = product.model_dump()
    product_dict["id"] = new_product_id
    product_dict["created_at"] = datetime.now(timezone.utc)
    product_dict["updated_at"] = datetime.now(timezone.utc)

    products_collection.insert_one(product_dict)
    return ProductSchema(**product_dict)


@router.get("/products", response_model=List[ProductSchema])
async def get_all_products():
    products_cursor = products_collection.find({}, {"_id": 0})
    products = []
    for product in products_cursor:
        try:
            products.append(ProductSchema(**product))
        except Exception:
            continue  # skip invalid products (optional)
    if not products:
        raise HTTPException(status_code=404, detail="No valid products found")
    return products



# Get product by ID
@router.get("/products/{product_id}", response_model=ProductSchema)
async def get_product_by_id(product_id: str):
    product = products_collection.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductSchema(**product)


# Update product by ID
@router.put("/products/{product_id}", response_model=ProductSchema)
async def update_product(product_id: str, product: ProductSchema):
    update_data = product.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    updated_product = products_collection.find_one_and_update(
        {"id": product_id},
        {"$set": update_data},
        return_document=True,
        projection={"_id": 0}
    )
    if not updated_product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductSchema(**updated_product)


# Delete product by ID
@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    result = products_collection.delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"detail": "Product deleted successfully"}


# Get stock levels
@router.get("/stock/levels")
async def get_stock_levels():
    products = list(products_collection.find({}, {"_id": 0, "name": 1, "current_stock": 1, "low_stock_alert": 1}))
    if not products:
        raise HTTPException(status_code=404, detail="No products found")
    return products


# Stock valuation
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


# Products below low stock alert
@router.get("/stock/low")
async def get_low_stock_products():
    products = list(products_collection.find(
        {"$expr": {"$lt": ["$current_stock", "$low_stock_alert"]}},
        {"_id": 0, "name": 1, "current_stock": 1, "low_stock_alert": 1}
    ))

    if not products:
        raise HTTPException(status_code=404, detail="No low stock products found")

    return products

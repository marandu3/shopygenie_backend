# utils/idincrement.py

from database.config import users_collection
from database.config import products_collection

def increment_user_id():
    max_user = users_collection.find_one(sort=[("id", -1)], projection={"id": 1})
    if not max_user:
        return 1
    return int(max_user["id"]) + 1  # always cast to int

def increment_product_id():
    max_user = products_collection.find_one(sort=[("id", -1)], projection={"id": 1})
    if not max_user:
        return 1
    return int(max_user["id"]) + 1  # always cast to int

# routes/user.py

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pymongo.collection import ReturnDocument
from typing import List

from database.config import users_collection
from schema.user import (
    Usercreate,
    UserInResponse,
    Userupdate,
)
from schema.token import Token, TokenData
from utils.hashing import hash_password, verify_password
from utils.idincrement import increment_user_id
from auth.auth import create_access_token, decode_access_token


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")


# ──────────────────────────────────────────────
# Decode current user from JWT token
async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return TokenData(username=payload.get("sub"))


# ──────────────────────────────────────────────
# Login: exchange username/password for JWT token
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_collection.find_one({"username": form_data.username})

    # Ensure user exists and has hashed_password
    if not user or "hashed_password" not in user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user["username"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}


# ──────────────────────────────────────────────
# Create user (registration)
@router.post("/user", response_model=UserInResponse)
async def create_user(user: Usercreate):
    if users_collection.find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user_id = increment_user_id()
    user_dict = user.model_dump()

    plain_password = user_dict.pop("password")
    user_dict["id"] = new_user_id
    user_dict["hashed_password"] = hash_password(plain_password)

    users_collection.insert_one(user_dict)

    # Filter out sensitive fields before returning
    return UserInResponse(**{k: v for k, v in user_dict.items() if k != "hashed_password"})


# ──────────────────────────────────────────────
# Get all users
@router.get("/users", response_model=List[UserInResponse])
async def get_users(current_user: TokenData = Depends(get_current_user)):
    users = users_collection.find({}, {"_id": 0, "hashed_password": 0})
    user_list = [UserInResponse(**user) for user in users]
    if not user_list:
        raise HTTPException(status_code=404, detail="No users found")
    return user_list


# ──────────────────────────────────────────────
# Get user by ID
@router.get("/users/{user_id}", response_model=UserInResponse)
async def get_user(user_id: int, current_user: TokenData = Depends(get_current_user)):
    user = users_collection.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInResponse(**user)


# ──────────────────────────────────────────────
# Update user details
@router.put("/users/{user_id}", response_model=UserInResponse)
async def update_user(
    user_id: int,
    user: Userupdate,
    current_user: TokenData = Depends(get_current_user)
):
    update_data = user.model_dump(exclude_unset=True)

    # prevent updating password here (use change-password endpoint instead)
    if "password" in update_data:
        update_data.pop("password")

    updated_user = users_collection.find_one_and_update(
        {"id": user_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "hashed_password": 0}
    )
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInResponse(**updated_user)


# ──────────────────────────────────────────────
# Change password
@router.put("/users/{user_id}/change-password", response_model=UserInResponse)
async def change_password(
    user_id: int,
    new_password: str,
    current_user: TokenData = Depends(get_current_user)
):
    if not users_collection.find_one({"id": user_id}):
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = hash_password(new_password)
    updated_user = users_collection.find_one_and_update(
        {"id": user_id},
        {"$set": {"hashed_password": hashed_password}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "hashed_password": 0}
    )
    return UserInResponse(**updated_user)


# ──────────────────────────────────────────────
# Delete user
@router.delete("/users/{user_id}", response_model=UserInResponse)
async def delete_user(user_id: int, current_user: TokenData = Depends(get_current_user)):
    deleted_user = users_collection.find_one_and_delete(
        {"id": user_id}, projection={"_id": 0, "hashed_password": 0}
    )
    if not deleted_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInResponse(**deleted_user)

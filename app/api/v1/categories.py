import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import PRODUCTS_CREATE, PRODUCTS_VIEW
from app.db.session import get_db
from app.models.product import Category
from app.schemas.product import CategoryCreate, CategoryOut

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryCreate,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    category = Category(organization_id=org_id, name=payload.name)
    db.add(category)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("A category with this name already exists")
    await db.refresh(category)
    return category


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Category).where(Category.organization_id == org_id, Category.is_active.is_(True)).order_by(Category.name)
    )
    return list(result.scalars())


@router.delete("/{category_id}")
async def deactivate_category(
    category_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    category = await db.get(Category, category_id)
    if category is None or category.organization_id != org_id:
        raise NotFoundError("Category not found")

    category.is_active = False
    await db.commit()
    return {"detail": "Category deactivated"}

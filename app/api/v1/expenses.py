import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import EXPENSES_CREATE, EXPENSES_VIEW
from app.db.session import get_db
from app.models.expense import Expense, ExpenseCategory
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCategoryOut, ExpenseCreate, ExpenseOut, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["Expenses"])


@router.post("/categories", response_model=ExpenseCategoryOut, status_code=201)
async def create_expense_category(
    payload: ExpenseCategoryCreate,
    ctx: AuthContext = Depends(require_permission(EXPENSES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    category = ExpenseCategory(organization_id=org_id, name=payload.name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/categories", response_model=list[ExpenseCategoryOut])
async def list_expense_categories(
    ctx: AuthContext = Depends(require_permission(EXPENSES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.organization_id == org_id, ExpenseCategory.is_active.is_(True)).order_by(ExpenseCategory.name)
    )
    return list(result.scalars())


@router.post("", response_model=ExpenseOut, status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    ctx: AuthContext = Depends(require_permission(EXPENSES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    expense = Expense(organization_id=org_id, recorded_by=ctx.user_id, **payload.model_dump())
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return expense


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    ctx: AuthContext = Depends(require_permission(EXPENSES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Expense).where(Expense.organization_id == org_id).order_by(Expense.expense_date.desc())
    )
    return list(result.scalars())


@router.put("/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdate,
    ctx: AuthContext = Depends(require_permission(EXPENSES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.organization_id != org_id:
        raise NotFoundError("Expense not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)

    await db.commit()
    await db.refresh(expense)
    return expense

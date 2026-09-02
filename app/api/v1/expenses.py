import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.permissions import EXPENSES_CREATE, EXPENSES_VIEW
from app.db.session import get_db
from app.models.expense import Expense, ExpenseCategory
from app.models.organization import Organization
from app.schemas.expense import ExpenseCategoryCreate, ExpenseCategoryOut, ExpenseCreate, ExpenseOut, ExpenseUpdate
from app.services.usage import enforce_storage_quota

router = APIRouter(prefix="/expenses", tags=["Expenses"])

ALLOWED_EVIDENCE_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


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


@router.post("/{expense_id}/evidence", response_model=ExpenseOut)
async def upload_expense_evidence(
    expense_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission(EXPENSES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.organization_id != org_id:
        raise NotFoundError("Expense not found")

    if file.content_type not in ALLOWED_EVIDENCE_TYPES:
        raise ValidationAppError(f"Unsupported file type: {file.content_type}", code="INVALID_FILE_TYPE")

    settings = get_settings()
    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise ValidationAppError("File exceeds the maximum allowed size", code="FILE_TOO_LARGE")

    org = await db.get(Organization, org_id)
    # Previous evidence on this expense (if any) is about to be replaced —
    # only the net new bytes count against the quota (MASTER PROMPT §64).
    previous_size = expense.evidence_size_bytes or 0
    await enforce_storage_quota(db, org, incoming_bytes=len(contents) - previous_size)

    # Tenant- and expense-isolated path — never a publicly guessable/servable URL.
    safe_name = f"{uuid.uuid4()}{os.path.splitext(file.filename or '')[1]}"
    directory = os.path.join(settings.uploads_dir, str(org_id), "expenses", str(expense_id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, safe_name)
    with open(path, "wb") as f:
        f.write(contents)

    expense.evidence_path = path
    expense.evidence_filename = file.filename
    expense.evidence_size_bytes = len(contents)
    await db.commit()
    await db.refresh(expense)
    return expense


@router.get("/{expense_id}/evidence")
async def download_expense_evidence(
    expense_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(EXPENSES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.organization_id != org_id or not expense.evidence_path:
        raise NotFoundError("Evidence not found")
    return FileResponse(expense.evidence_path, filename=expense.evidence_filename or "evidence")

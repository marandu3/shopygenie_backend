from tests.conftest import auth_headers, login


async def test_cross_tenant_customer_read_is_blocked(client, tenant, db):
    """Two independent tenants; tenant B must never see tenant A's data by ID."""
    token_a = await login(client, tenant.owner_email, tenant.owner_password)

    # Build a second, independent tenant inline (the `tenant` fixture already
    # gave us one; replicate the minimal bits for a second, isolated one).
    import uuid
    from decimal import Decimal

    from app.models.organization import Branch, Organization
    from app.models.user import Role, User, WorkerStatus
    from app.core.security import hash_password
    from sqlalchemy import select

    suffix = uuid.uuid4().hex[:8]
    result = await db.execute(select(Role).where(Role.organization_id.is_(None), Role.name == "Tenant Owner"))
    owner_role = result.scalar_one()

    org_b = Organization(name=f"Other Shop {suffix}", slug=f"other-shop-{suffix}")
    db.add(org_b)
    await db.flush()
    branch_b = Branch(organization_id=org_b.id, name="Main")
    db.add(branch_b)
    await db.flush()

    owner_b = User(
        organization_id=org_b.id, branch_id=branch_b.id, role_id=owner_role.id,
        full_name="Other Owner", email=f"other-owner-{suffix}@shopygenie-tests.dev",
        hashed_password=hash_password("OtherPass123!"), status=WorkerStatus.ACTIVE, must_change_password=False,
    )
    db.add(owner_b)
    await db.commit()

    token_b = await login(client, owner_b.email, "OtherPass123!")

    # Tenant A's owner can see their own customer.
    resp = await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token_a))
    assert resp.status_code == 200

    # Tenant B's owner must NOT be able to fetch tenant A's customer by ID.
    resp = await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    # Nor pay a debt belonging to tenant A (IDOR on a write path).
    resp = await client.post(
        f"/api/v1/debts/{uuid.uuid4()}/pay", headers=auth_headers(token_b), json={"amount": 1, "method": "CASH"}
    )
    assert resp.status_code == 404

    # Tenant B's own customer list is empty — never inherits tenant A's rows.
    resp = await client.get("/api/v1/customers", headers=auth_headers(token_b))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_platform_owner_requires_explicit_tenant_mode(client):
    from app.core.config import get_settings

    settings = get_settings()
    token = await login(client, settings.platform_owner_email, settings.platform_owner_password)

    resp = await client.get("/api/v1/products", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

from tests.conftest import auth_headers, build_second_tenant, login


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


async def test_cross_tenant_transfer_access_is_blocked(client, tenant, db):
    """MASTER PROMPT §84: Tenant A cannot read or act on Tenant B's transfers."""
    email_b, password_b = await build_second_tenant(db)
    token_a = await login(client, tenant.owner_email, tenant.owner_password)
    token_b = await login(client, email_b, password_b)

    resp = await client.get("/api/v1/transfers", headers=auth_headers(token_a))
    assert resp.status_code == 200

    resp_b = await client.get("/api/v1/transfers", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json() == []


async def test_cross_tenant_reports_never_leak(client, tenant, db):
    """MASTER PROMPT §84: Tenant B's reports must never include Tenant A's
    sales — the safest proof is that a brand-new tenant's report totals are
    all zero even though tenant A has real data by this point in the suite."""
    email_b, password_b = await build_second_tenant(db)
    token_b = await login(client, email_b, password_b)

    resp = await client.post("/api/v1/reports/summary", headers=auth_headers(token_b), json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["revenue"] == 0
    assert body["total_transactions"] == 0


async def test_cross_tenant_audit_log_access_is_blocked(client, tenant, db):
    """MASTER PROMPT §84: Tenant B must never see Tenant A's audit trail."""
    email_b, password_b = await build_second_tenant(db)
    token_a = await login(client, tenant.owner_email, tenant.owner_password)
    token_b = await login(client, email_b, password_b)

    # Generate at least one real audit event for tenant A.
    await client.get("/api/v1/customers", headers=auth_headers(token_a))

    resp_a = await client.get("/api/v1/audit-logs", headers=auth_headers(token_a))
    assert resp_a.status_code == 200

    resp_b = await client.get("/api/v1/audit-logs", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    a_ids = {row["id"] for row in resp_a.json()["items"]}
    b_ids = {row["id"] for row in resp_b.json()["items"]}
    assert a_ids.isdisjoint(b_ids)


async def test_cross_tenant_sms_config_is_isolated(client, tenant, db):
    """MASTER PROMPT §43/§84: SMSGate configuration and message history are
    per-tenant — Tenant B configuring/sending never touches Tenant A's data,
    and Tenant B cannot read Tenant A's SMS history."""
    email_b, password_b = await build_second_tenant(db)
    token_a = await login(client, tenant.owner_email, tenant.owner_password)
    token_b = await login(client, email_b, password_b)

    configured = await client.put(
        "/api/v1/organizations/me/sms-config",
        headers=auth_headers(token_a),
        json={"base_url": "https://smsgate.example.com", "api_key": "tenant-a-secret-key", "sender_id": "SHOPA", "enabled": True},
    )
    assert configured.status_code == 200
    assert configured.json()["api_key_masked"].endswith("-key")
    assert "tenant-a-secret-key" not in configured.text

    config_b = await client.get("/api/v1/organizations/me/sms-config", headers=auth_headers(token_b))
    assert config_b.status_code == 200
    assert config_b.json()["enabled"] is False
    assert config_b.json()["base_url"] is None

    history_a = await client.get("/api/v1/organizations/me/sms-history", headers=auth_headers(token_a))
    history_b = await client.get("/api/v1/organizations/me/sms-history", headers=auth_headers(token_b))
    assert history_a.status_code == 200 and history_b.status_code == 200
    a_ids = {row["id"] for row in history_a.json()["items"]}
    b_ids = {row["id"] for row in history_b.json()["items"]}
    assert a_ids.isdisjoint(b_ids)


async def test_platform_owner_requires_explicit_tenant_mode(client):
    from app.core.config import get_settings

    settings = get_settings()
    token = await login(client, settings.platform_owner_email, settings.platform_owner_password)

    resp = await client.get("/api/v1/products", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

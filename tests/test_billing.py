from tests.conftest import auth_headers, login


async def test_owner_can_submit_and_list_own_activation_requests(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    resp = await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(token),
        json={"plan_requested": "PROFESSIONAL", "reference_number": "MPESA-XYZ-001", "note": "Paid via M-Pesa"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["plan_requested"] == "PROFESSIONAL"

    listed = await client.get("/api/v1/billing/activation-requests", headers=auth_headers(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_cashier_without_billing_permission_cannot_submit_request(client, tenant):
    token = await login(client, tenant.cashier_email, tenant.cashier_password)

    resp = await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(token),
        json={"plan_requested": "BASIC", "reference_number": "REF-1"},
    )
    assert resp.status_code == 403


async def test_platform_owner_approves_activation_request_and_activates_org(client, tenant, settings=None):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)
    submit = await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(owner_token),
        json={"plan_requested": "BUSINESS", "reference_number": "BANK-REF-777"},
    )
    request_id = submit.json()["id"]

    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)

    pending = await client.get(
        "/api/v1/platform/activation-requests?status=PENDING", headers=auth_headers(platform_token)
    )
    assert pending.status_code == 200
    assert any(r["id"] == request_id for r in pending.json()["items"])

    approve = await client.post(
        f"/api/v1/platform/activation-requests/{request_id}/approve",
        headers=auth_headers(platform_token),
        json={"duration_days": 30, "review_note": "Confirmed against bank statement"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    status_resp = await client.get("/api/v1/billing/status", headers=auth_headers(owner_token))
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["subscription_status"] == "ACTIVE"
    assert body["subscription_plan"] == "BUSINESS"
    assert body["subscription_expires_at"] is not None

    # Cannot review the same request twice.
    reapprove = await client.post(
        f"/api/v1/platform/activation-requests/{request_id}/approve",
        headers=auth_headers(platform_token),
        json={"duration_days": 30},
    )
    assert reapprove.status_code == 409


async def test_platform_owner_rejects_activation_request_without_activating_org(client, tenant):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)
    submit = await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(owner_token),
        json={"plan_requested": "BASIC", "reference_number": "REF-BOGUS"},
    )
    request_id = submit.json()["id"]

    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)

    reject = await client.post(
        f"/api/v1/platform/activation-requests/{request_id}/reject",
        headers=auth_headers(platform_token),
        json={"review_note": "Reference number does not match any deposit"},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "REJECTED"

    status_resp = await client.get("/api/v1/billing/status", headers=auth_headers(owner_token))
    assert status_resp.json()["subscription_status"] == "TRIAL"


async def test_tenant_cannot_see_another_tenants_activation_requests(client, db):
    from tests.conftest import Tenant  # noqa: F401 - just documents fixture shape

    # Build two isolated tenants directly (the `tenant` fixture only gives one).
    import uuid as uuid_lib
    from decimal import Decimal

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.organization import Branch, Organization
    from app.models.user import Role, User, WorkerStatus

    result = await db.execute(select(Role).where(Role.organization_id.is_(None), Role.name == "Tenant Owner"))
    owner_role = result.scalar_one()

    orgs = []
    for _ in range(2):
        suffix = uuid_lib.uuid4().hex[:8]
        org = Organization(name=f"Org {suffix}", slug=f"org-{suffix}", tax_rate_percent=Decimal("0"))
        db.add(org)
        await db.flush()
        branch = Branch(organization_id=org.id, name="Main")
        db.add(branch)
        password = "OwnerPass123!"
        owner = User(
            organization_id=org.id, branch_id=branch.id, role_id=owner_role.id,
            full_name="Owner", email=f"owner-{suffix}@shopygenie-tests.dev",
            hashed_password=hash_password(password), status=WorkerStatus.ACTIVE, must_change_password=False,
        )
        db.add(owner)
        await db.flush()
        orgs.append((owner.email, password))
    await db.commit()

    (email_a, password_a), (email_b, password_b) = orgs
    token_a = await login(client, email_a, password_a)
    token_b = await login(client, email_b, password_b)

    await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(token_a),
        json={"plan_requested": "BASIC", "reference_number": "REF-A"},
    )

    listed_b = await client.get("/api/v1/billing/activation-requests", headers=auth_headers(token_b))
    assert listed_b.json()["total"] == 0

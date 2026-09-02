import uuid

from tests.conftest import auth_headers, login


# ---------- Held sales ----------

async def test_held_sale_create_list_and_discard(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    created = await client.post(
        "/api/v1/held-sales",
        headers=auth_headers(token),
        json={"label": "Kikapu 1", "items": [{"product_id": str(tenant.product_id), "quantity": 2, "discount_amount": 0}]},
    )
    assert created.status_code == 201, created.text
    held_id = created.json()["id"]

    listed = await client.get("/api/v1/held-sales", headers=auth_headers(token))
    assert listed.status_code == 200
    assert any(h["id"] == held_id for h in listed.json())

    detail = await client.get(f"/api/v1/held-sales/{held_id}", headers=auth_headers(token))
    assert detail.status_code == 200
    assert detail.json()["items"][0]["quantity"] == 2

    discard = await client.delete(f"/api/v1/held-sales/{held_id}", headers=auth_headers(token))
    assert discard.status_code == 204

    listed_after = await client.get("/api/v1/held-sales", headers=auth_headers(token))
    assert all(h["id"] != held_id for h in listed_after.json())


# ---------- Inventory transfers ----------

async def test_transfer_full_lifecycle(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    branches = await client.get("/api/v1/organizations/me/branches", headers=auth_headers(token))
    source_branch_id = branches.json()[0]["id"]

    new_branch = await client.post(
        "/api/v1/organizations/me/branches", headers=auth_headers(token), json={"name": "Branch 2"}
    )
    dest_branch_id = new_branch.json()["id"]

    created = await client.post(
        "/api/v1/transfers",
        headers=auth_headers(token),
        json={
            "source_branch_id": source_branch_id,
            "destination_branch_id": dest_branch_id,
            "items": [{"product_id": str(tenant.product_id), "quantity": 3}],
        },
    )
    assert created.status_code == 201, created.text
    transfer_id = created.json()["id"]
    assert created.json()["status"] == "REQUESTED"

    approved = await client.post(f"/api/v1/transfers/{transfer_id}/approve", headers=auth_headers(token))
    assert approved.json()["status"] == "APPROVED"

    in_transit = await client.post(f"/api/v1/transfers/{transfer_id}/in-transit", headers=auth_headers(token))
    assert in_transit.json()["status"] == "IN_TRANSIT"

    received = await client.post(f"/api/v1/transfers/{transfer_id}/receive", headers=auth_headers(token))
    assert received.json()["status"] == "COMPLETED"

    # Can't skip states out of order.
    reject_attempt = await client.post(f"/api/v1/transfers/{transfer_id}/reject", headers=auth_headers(token), json={"reason": "too late"})
    assert reject_attempt.status_code == 422


async def test_transfer_same_branch_rejected(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    branches = await client.get("/api/v1/organizations/me/branches", headers=auth_headers(token))
    branch_id = branches.json()[0]["id"]

    resp = await client.post(
        "/api/v1/transfers",
        headers=auth_headers(token),
        json={"source_branch_id": branch_id, "destination_branch_id": branch_id, "items": [{"product_id": str(tenant.product_id), "quantity": 1}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_TRANSFER"


# ---------- Tenant account requests ----------

async def test_account_request_public_submit_and_platform_approval(client, tenant):
    suffix = uuid.uuid4().hex[:8]
    submitted = await client.post(
        "/api/v1/account-requests",
        json={
            "organization_name": "Duka la Amani",
            "applicant_name": "Amani Mushi",
            "email": f"amani-{suffix}@example.com",
            "phone": "+255700111222",
        },
    )
    assert submitted.status_code == 201, submitted.text
    request_id = submitted.json()["id"]
    assert submitted.json()["status"] == "PENDING"

    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)

    listed = await client.get("/api/v1/platform/account-requests?status=PENDING", headers=auth_headers(platform_token))
    assert listed.status_code == 200
    assert any(r["id"] == request_id for r in listed.json()["items"])

    approved = await client.post(
        f"/api/v1/platform/account-requests/{request_id}/approve",
        headers=auth_headers(platform_token),
        json={"slug": f"duka-la-amani-{request_id[:8]}"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["organization_id"] is not None


async def test_account_request_rejection(client, tenant):
    suffix = uuid.uuid4().hex[:8]
    submitted = await client.post(
        "/api/v1/account-requests",
        json={"organization_name": "Bogus Shop", "applicant_name": "Nobody", "email": f"nobody-{suffix}@example.com"},
    )
    request_id = submitted.json()["id"]

    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)
    rejected = await client.post(
        f"/api/v1/platform/account-requests/{request_id}/reject", headers=auth_headers(platform_token), json={"note": "Duplicate submission"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


# ---------- Platform owner invitations ----------

async def test_platform_owner_invitation_accept_grants_platform_org_membership(client, tenant):
    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)
    email = f"second-owner-{uuid.uuid4().hex[:8]}@example.com"

    created = await client.post(
        "/api/v1/platform/owner-invitations", headers=auth_headers(platform_token), json={"email": email}
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    assert token  # only ever returned once

    accepted = await client.post(
        "/api/v1/platform/owner-invitations/accept",
        json={"token": token, "full_name": "Second Owner", "password": "SecureOwnerPass123!"},
    )
    assert accepted.status_code == 200, accepted.text

    login_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "SecureOwnerPass123!"})
    assert login_resp.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=auth_headers(login_resp.json()["access_token"]))
    body = me.json()
    assert body["is_platform_owner"] is True
    assert body["organization_id"] is not None  # belongs to the dedicated Platform Organization


async def test_platform_owner_invitation_rejects_reused_token(client, tenant):
    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)
    email = f"third-owner-{uuid.uuid4().hex[:8]}@example.com"
    created = await client.post(
        "/api/v1/platform/owner-invitations", headers=auth_headers(platform_token), json={"email": email}
    )
    token = created.json()["token"]

    first = await client.post(
        "/api/v1/platform/owner-invitations/accept", json={"token": token, "full_name": "Third Owner", "password": "AnotherPass123!"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/platform/owner-invitations/accept", json={"token": token, "full_name": "Third Owner Again", "password": "AnotherPass123!"}
    )
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "INVALID_INVITATION_STATUS"


# ---------- Usage metering ----------

async def test_sms_usage_counted_on_worker_invite(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")

    await client.post(
        "/api/v1/workers",
        headers=auth_headers(token),
        json={"full_name": "SMS Test Hire", "email": f"smstest-{tenant.org_id}@shopygenie-tests.dev", "phone": "+255700999888", "role_id": cashier_role_id},
    )

    usage = await client.get("/api/v1/billing/usage", headers=auth_headers(token))
    assert usage.status_code == 200
    metrics = {m["metric"]: m["count"] for m in usage.json()["metrics"]}
    assert metrics.get("sms_messages", 0) >= 1


# ---------- Expense evidence ----------

async def test_expense_evidence_upload_and_download(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    expense = await client.post(
        "/api/v1/expenses",
        headers=auth_headers(token),
        json={"description": "Umeme", "amount": 5000, "expense_date": "2026-01-15"},
    )
    expense_id = expense.json()["id"]

    upload = await client.post(
        f"/api/v1/expenses/{expense_id}/evidence",
        headers=auth_headers(token),
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nfakepngdata", "image/png")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["evidence_filename"] == "receipt.png"

    download = await client.get(f"/api/v1/expenses/{expense_id}/evidence", headers=auth_headers(token))
    assert download.status_code == 200
    assert download.content == b"\x89PNG\r\n\x1a\nfakepngdata"


async def test_expense_evidence_rejects_bad_content_type(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    expense = await client.post(
        "/api/v1/expenses", headers=auth_headers(token), json={"description": "Test", "amount": 100, "expense_date": "2026-01-15"}
    )
    expense_id = expense.json()["id"]

    upload = await client.post(
        f"/api/v1/expenses/{expense_id}/evidence",
        headers=auth_headers(token),
        files={"file": ("virus.exe", b"MZfake", "application/x-msdownload")},
    )
    assert upload.status_code == 422
    assert upload.json()["error"]["code"] == "INVALID_FILE_TYPE"

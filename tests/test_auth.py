from tests.conftest import auth_headers, login


async def test_wrong_password_rejected(client, tenant):
    resp = await client.post("/api/v1/auth/login", json={"email": tenant.owner_email, "password": "wrong"})
    assert resp.status_code == 401


async def test_account_locks_after_repeated_failed_logins(client, tenant):
    for _ in range(5):
        resp = await client.post("/api/v1/auth/login", json={"email": tenant.owner_email, "password": "wrong"})
        assert resp.status_code == 401

    # 6th attempt, even with the CORRECT password, must now be locked out.
    resp = await client.post("/api/v1/auth/login", json={"email": tenant.owner_email, "password": tenant.owner_password})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ACCOUNT_LOCKED"


async def test_cashier_cannot_invite_workers(client, tenant):
    """RBAC: a Cashier role has no workers.invite permission. The permission
    check must run before the request body is even inspected."""
    import uuid

    token = await login(client, tenant.cashier_email, tenant.cashier_password)

    resp = await client.post(
        "/api/v1/workers",
        headers=auth_headers(token),
        json={"full_name": "New Person", "email": "new-person@shopygenie-tests.dev", "role_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_worker_invite_forces_password_change_on_first_login(client, tenant, db):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)

    roles_resp = await client.get("/api/v1/workers/roles", headers=auth_headers(owner_token))
    cashier_role_id = next(r["id"] for r in roles_resp.json() if r["name"] == "Cashier")

    invited_email = f"invited-person-{tenant.org_id}@shopygenie-tests.dev"
    invite_resp = await client.post(
        "/api/v1/workers",
        headers=auth_headers(owner_token),
        json={"full_name": "Invited Person", "email": invited_email, "role_id": cashier_role_id},
    )
    assert invite_resp.status_code == 201
    assert invite_resp.json()["must_change_password"] is True

    # We don't have the temp password here (it only ever goes out via SMS),
    # so directly assert the DB state a worker invite must leave behind.
    from sqlalchemy import select
    from app.models.user import User, WorkerStatus

    result = await db.execute(select(User).where(User.email == invited_email))
    worker = result.scalar_one()
    assert worker.status == WorkerStatus.INVITED
    assert worker.must_change_password is True
    assert worker.hashed_password != ""  # never stores plaintext


async def test_change_password_blocks_everything_else_until_done(client, tenant, db):
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.user import User

    result = await db.execute(select(User).where(User.email == tenant.owner_email))
    owner = result.scalar_one()
    owner.must_change_password = True
    owner.hashed_password = hash_password("TempPass123!")
    await db.commit()

    token = await login(client, tenant.owner_email, "TempPass123!")

    blocked = await client.get("/api/v1/products", headers=auth_headers(token))
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    change_resp = await client.post(
        "/api/v1/auth/change-password", headers=auth_headers(token), json={"new_password": "BrandNewPass123!"}
    )
    assert change_resp.status_code == 200
    assert change_resp.json()["must_change_password"] is False

    allowed = await client.get("/api/v1/products", headers=auth_headers(token))
    assert allowed.status_code == 200

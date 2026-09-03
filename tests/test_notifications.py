from tests.conftest import auth_headers, build_second_tenant, login


async def test_worker_invite_creates_org_notification(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")
    resp = await client.post(
        "/api/v1/workers",
        headers=auth_headers(token),
        json={"full_name": "New Hire", "email": f"newhire-{tenant.org_id}@shopygenie-tests.dev", "role_id": cashier_role_id},
    )
    assert resp.status_code == 201, resp.text

    listed = await client.get("/api/v1/notifications", headers=auth_headers(token))
    assert listed.status_code == 200
    body = listed.json()
    assert any(n["title"] == "New worker invited" for n in body["items"])


async def test_unread_count_decreases_after_marking_read(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")
    await client.post(
        "/api/v1/workers",
        headers=auth_headers(token),
        json={"full_name": "Another Hire", "email": f"another-{tenant.org_id}@shopygenie-tests.dev", "role_id": cashier_role_id},
    )

    before = await client.get("/api/v1/notifications/unread-count", headers=auth_headers(token))
    assert before.json()["unread_count"] >= 1

    listed = await client.get("/api/v1/notifications", headers=auth_headers(token))
    notification_id = listed.json()["items"][0]["id"]

    read_resp = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=auth_headers(token))
    assert read_resp.status_code == 200

    after = await client.get("/api/v1/notifications/unread-count", headers=auth_headers(token))
    assert after.json()["unread_count"] == before.json()["unread_count"] - 1


async def test_mark_all_read_clears_unread_count(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")
    for i in range(2):
        await client.post(
            "/api/v1/workers",
            headers=auth_headers(token),
            json={"full_name": f"Hire {i}", "email": f"hire{i}-{tenant.org_id}@shopygenie-tests.dev", "role_id": cashier_role_id},
        )

    await client.post("/api/v1/notifications/read-all", headers=auth_headers(token))
    after = await client.get("/api/v1/notifications/unread-count", headers=auth_headers(token))
    assert after.json()["unread_count"] == 0


async def test_billing_activation_request_notifies_platform_owner(client, tenant):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.post(
        "/api/v1/billing/activation-requests",
        headers=auth_headers(owner_token),
        json={"plan_requested": "STANDARD", "reference_number": "NOTIF-TEST-1"},
    )

    from app.core.config import get_settings

    platform_token = await login(client, get_settings().platform_owner_email, get_settings().platform_owner_password)
    listed = await client.get("/api/v1/notifications", headers=auth_headers(platform_token))
    assert listed.status_code == 200
    assert any(n["title"] == "New billing activation request" for n in listed.json()["items"])


async def test_tenant_cannot_see_platform_wide_notifications(client, tenant):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)
    listed = await client.get("/api/v1/notifications", headers=auth_headers(owner_token))
    assert listed.status_code == 200
    # Every item must be scoped to this tenant's own org, never the platform-wide feed.
    for n in listed.json()["items"]:
        assert n["organization_id"] == str(tenant.org_id)


async def test_tenant_cannot_mark_another_tenants_notification_read(client, tenant, db):
    """MASTER PROMPT — notification security §14: ownership must be
    enforced server-side. A user who somehow obtains another tenant's
    notification id (e.g. by guessing a UUID) must not be able to write a
    read-marker against it — the backend rejects it as not found, the same
    response as a genuinely unknown id, so existence is never confirmed."""
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)

    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(owner_token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")
    await client.post(
        "/api/v1/workers",
        headers=auth_headers(owner_token),
        json={"full_name": "Cross Tenant Target", "email": f"cross-{tenant.org_id}@shopygenie-tests.dev", "role_id": cashier_role_id},
    )
    listed = await client.get("/api/v1/notifications", headers=auth_headers(owner_token))
    notification_id = listed.json()["items"][0]["id"]

    other_email, other_password = await build_second_tenant(db)
    other_token = await login(client, other_email, other_password)

    read_resp = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=auth_headers(other_token))
    assert read_resp.status_code == 404

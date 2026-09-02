"""Coverage for the gaps identified in a full re-audit against the 124-
section MASTER PROMPT: per-tenant SMSGate config, custom roles, sale/debt
SMS notifications, billing plan configurability, WhatsApp/storage quotas,
platform-level report builder, and sales-power analytics."""

from tests.conftest import auth_headers, login


# ---------- Custom roles (MASTER PROMPT §42, §88) ----------

async def test_owner_can_create_edit_and_delete_a_custom_role(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    created = await client.post(
        "/api/v1/workers/roles",
        headers=auth_headers(token),
        json={"name": "Stock Clerk", "permissions": ["inventory.view", "inventory.adjust"]},
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["is_system"] is False
    assert set(role["permissions"]) == {"inventory.view", "inventory.adjust"}

    updated = await client.put(
        f"/api/v1/workers/roles/{role['id']}",
        headers=auth_headers(token),
        json={"name": "Senior Stock Clerk", "permissions": ["inventory.view"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Senior Stock Clerk"
    assert updated.json()["permissions"] == ["inventory.view"]

    deleted = await client.delete(f"/api/v1/workers/roles/{role['id']}", headers=auth_headers(token))
    assert deleted.status_code == 204


async def test_custom_role_rejects_unknown_permission_code(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.post(
        "/api/v1/workers/roles", headers=auth_headers(token), json={"name": "Bad Role", "permissions": ["not.a.real.permission"]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PERMISSION"


async def test_system_role_cannot_be_edited_or_deleted(client, tenant):
    """System roles have organization_id=None — a tenant-scoped update/delete
    correctly 404s (not "found but read-only") rather than confirming a
    cross-scope role exists (MASTER PROMPT §12: don't reveal existence)."""
    token = await login(client, tenant.owner_email, tenant.owner_password)
    roles = await client.get("/api/v1/workers/roles", headers=auth_headers(token))
    cashier_role_id = next(r["id"] for r in roles.json() if r["name"] == "Cashier")

    resp = await client.put(f"/api/v1/workers/roles/{cashier_role_id}", headers=auth_headers(token), json={"name": "Hacked"})
    assert resp.status_code == 404

    resp2 = await client.delete(f"/api/v1/workers/roles/{cashier_role_id}", headers=auth_headers(token))
    assert resp2.status_code == 404


async def test_cashier_cannot_manage_roles(client, tenant):
    token = await login(client, tenant.cashier_email, tenant.cashier_password)
    resp = await client.post("/api/v1/workers/roles", headers=auth_headers(token), json={"name": "X", "permissions": []})
    assert resp.status_code == 403


# ---------- Per-tenant SMSGate configuration (MASTER PROMPT §43, §44) ----------

async def test_sms_config_update_test_send_and_history(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    updated = await client.put(
        "/api/v1/organizations/me/sms-config",
        headers=auth_headers(token),
        json={"base_url": "https://smsgate.example.com", "api_key": "super-secret-key-123", "sender_id": "SHOPYGENIE", "enabled": True},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["enabled"] is True
    assert body["api_key_masked"].endswith("-123")
    assert "super-secret-key-123" not in updated.text  # never returned in plaintext

    # No real SMSGate credentials exist, so this exercises the failure path
    # of a real (attempted) network call, not the console stub — either way
    # the test/config-test endpoint must respond, not crash.
    tested = await client.post(
        "/api/v1/organizations/me/sms-config/test", headers=auth_headers(token), json={"phone": "+255700000001"}
    )
    assert tested.status_code == 200

    history = await client.get("/api/v1/organizations/me/sms-history", headers=auth_headers(token))
    assert history.status_code == 200
    assert history.json()["total"] >= 1
    assert any(m["message_type"] == "TEST" for m in history.json()["items"])


async def test_cashier_cannot_view_sms_config(client, tenant):
    token = await login(client, tenant.cashier_email, tenant.cashier_password)
    resp = await client.get("/api/v1/organizations/me/sms-config", headers=auth_headers(token))
    assert resp.status_code == 403


# ---------- Sale receipt SMS (MASTER PROMPT §45) ----------

async def test_sale_notify_customer_immediately_and_resend_later(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    sale = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [{"amount": 150, "method": "CASH"}],
            "notify_customer": True,
        },
    )
    assert sale.status_code == 201, sale.text
    sale_id = sale.json()["id"]

    history = await client.get("/api/v1/organizations/me/sms-history", headers=auth_headers(token))
    assert any(m["message_type"] == "SALE_RECEIPT" and m["related_sale_id"] == sale_id for m in history.json()["items"])

    resend = await client.post(f"/api/v1/sales/{sale_id}/notify", headers=auth_headers(token), json={"channel": "sms"})
    assert resend.status_code == 200
    assert resend.json()["message_type"] == "SALE_RECEIPT"


async def test_notify_sale_with_no_customer_is_rejected(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    sale = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )
    sale_id = sale.json()["id"]

    resp = await client.post(f"/api/v1/sales/{sale_id}/notify", headers=auth_headers(token), json={"channel": "sms"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NO_CUSTOMER"


# ---------- Debt reminders / bulk SMS progress (MASTER PROMPT §46) ----------

async def test_send_debt_reminders_reports_per_recipient_results(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [],
            "allow_credit": True,
        },
    )

    resp = await client.post("/api/v1/debts/send-reminders", headers=auth_headers(token), json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["total"] == body["sent"] + body["failed"]
    assert len(body["results"]) == body["total"]


# ---------- Billing plan configurability (MASTER PROMPT §61) ----------

async def test_public_billing_plans_lists_four_configurable_tiers(client):
    resp = await client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert codes == {"BASIC", "PROFESSIONAL", "BUSINESS", "ENTERPRISE"}


async def test_platform_owner_can_edit_a_billing_plan(client):
    from app.core.config import get_settings

    settings = get_settings()
    token = await login(client, settings.platform_owner_email, settings.platform_owner_password)

    plans = await client.get("/api/v1/platform/billing-plans", headers=auth_headers(token))
    assert plans.status_code == 200
    basic = next(p for p in plans.json() if p["code"] == "BASIC")

    updated = await client.put(
        f"/api/v1/platform/billing-plans/{basic['id']}",
        headers=auth_headers(token),
        json={"price_monthly": 19999, "description": "Updated by platform owner"},
    )
    assert updated.status_code == 200
    assert updated.json()["price_monthly"] == 19999
    assert updated.json()["description"] == "Updated by platform owner"
    assert updated.json()["code"] == "BASIC"  # code itself is never editable

    # Restore, so other tests reading the seeded default aren't affected.
    await client.put(
        f"/api/v1/platform/billing-plans/{basic['id']}",
        headers=auth_headers(token),
        json={"price_monthly": 15000, "description": "For a single shop just getting started."},
    )


async def test_tenant_owner_cannot_edit_billing_plans(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    plans = await client.get("/api/v1/platform/billing-plans", headers=auth_headers(token))
    assert plans.status_code == 403


# ---------- WhatsApp / storage usage & quotas (MASTER PROMPT §63-66) ----------

async def test_usage_endpoint_reports_whatsapp_and_storage_quota_shape(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.get("/api/v1/billing/usage", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert "whatsapp" in body and "storage_bytes" in body
    assert body["whatsapp"]["used"] == 0
    assert body["whatsapp"]["exhausted"] is False


async def test_whatsapp_send_hard_blocks_once_quota_exhausted(client, tenant, db):
    """MASTER PROMPT §66: hard-block, don't silently fail."""
    import uuid as uuid_lib

    from sqlalchemy import select

    from app.models.billing import BillingPlanConfig
    from app.models.organization import Organization, SubscriptionPlan
    from app.services.notifications import send_whatsapp
    from app.services.usage import increment_usage

    org = await db.get(Organization, tenant.org_id)
    org.subscription_plan = SubscriptionPlan.BASIC
    await db.flush()

    result = await db.execute(select(BillingPlanConfig).where(BillingPlanConfig.code == SubscriptionPlan.BASIC))
    plan = result.scalar_one()
    original_quota = plan.whatsapp_quota_monthly
    plan.whatsapp_quota_monthly = 1
    await db.commit()

    try:
        await send_whatsapp(organization_id=tenant.org_id, to="+255700000000", message="Hi")  # consumes the 1 allowed unit

        from app.core.exceptions import ValidationAppError

        raised = False
        try:
            await send_whatsapp(organization_id=tenant.org_id, to="+255700000000", message="Hi again")
        except ValidationAppError as exc:
            raised = True
            assert exc.code == "WHATSAPP_QUOTA_EXHAUSTED"
        assert raised
    finally:
        plan.whatsapp_quota_monthly = original_quota
        await db.commit()


# ---------- Platform-level report builder (MASTER PROMPT §60) ----------

async def test_platform_report_builder_aggregates_are_platform_only(client):
    from app.core.config import get_settings

    settings = get_settings()
    token = await login(client, settings.platform_owner_email, settings.platform_owner_password)

    resp = await client.post(
        "/api/v1/platform/reports/builder", headers=auth_headers(token), json={"metric": "subscription_distribution"}
    )
    assert resp.status_code == 200
    assert resp.json()["metric"] == "subscription_distribution"

    bad = await client.post("/api/v1/platform/reports/builder", headers=auth_headers(token), json={"metric": "not_real"})
    assert bad.status_code == 422


async def test_tenant_owner_cannot_use_platform_report_builder(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.post(
        "/api/v1/platform/reports/builder", headers=auth_headers(token), json={"metric": "subscription_distribution"}
    )
    assert resp.status_code == 403


# ---------- Sales-power scatter analytics (MASTER PROMPT §54) ----------

async def test_sales_power_report_returns_real_scatter_points(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )

    resp = await client.post("/api/v1/reports/sales-power", headers=auth_headers(token), json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) >= 1
    assert body["trend_direction"] in {"growing", "declining", "flat", "insufficient_data"}


# ---------- Report builder CSV export (MASTER PROMPT §121) ----------

async def test_report_builder_csv_export(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.post(
        "/api/v1/reports/builder/export.csv", headers=auth_headers(token), json={"metric": "revenue"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "total" in resp.text


# ---------- Readiness health check (MASTER PROMPT §109) ----------

async def test_health_ready_reports_database_connectivity(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

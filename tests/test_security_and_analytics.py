from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers, login


async def test_login_rate_limit_blocks_after_threshold(client, tenant):
    # The limiter is IP-based and shared across accounts — 10 requests/60s.
    for _ in range(10):
        await client.post("/api/v1/auth/login", json={"email": tenant.owner_email, "password": "wrong"})

    resp = await client.post("/api/v1/auth/login", json={"email": tenant.owner_email, "password": tenant.owner_password})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


async def test_sales_list_is_paginated(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    for _ in range(3):
        resp = await client.post(
            "/api/v1/sales",
            headers=auth_headers(token),
            json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
        )
        assert resp.status_code == 201

    page1 = await client.get("/api/v1/sales?page=1&page_size=2", headers=auth_headers(token))
    assert page1.status_code == 200
    body = page1.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2

    page2 = await client.get("/api/v1/sales?page=2&page_size=2", headers=auth_headers(token))
    assert len(page2.json()["items"]) == 1


async def test_audit_log_records_sale_creation(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    sale_resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )
    sale_id = sale_resp.json()["id"]

    resp = await client.get("/api/v1/audit-logs", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    entry = next(e for e in body["items"] if e["action"] == "SALE_CREATED" and e["resource_id"] == sale_id)
    assert entry["acting_as_platform_owner"] is False
    assert entry["actor_user_id"] is not None


async def test_comparison_report_omits_percent_with_zero_baseline(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    # No prior-period data exists for this brand-new tenant, so "previous"
    # revenue is 0 — change_percent must be null, not a fabricated number.
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/v1/reports/comparison",
        headers=auth_headers(token),
        json={"start_date": now.isoformat(), "end_date": now.isoformat()},
    )
    assert resp.status_code == 200
    revenue_metric = next(m for m in resp.json()["metrics"] if m["label"] == "revenue")
    assert revenue_metric["previous"] == 0.0
    assert revenue_metric["change_percent"] is None


async def test_timeseries_fills_gap_days_with_zero(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=4)
    resp = await client.post(
        "/api/v1/reports/timeseries",
        headers=auth_headers(token),
        json={"start_date": start.isoformat(), "end_date": now.isoformat(), "metric": "revenue"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 5  # 5 consecutive calendar days, none skipped
    assert points[0]["value"] == 0.0  # no sale that far back
    assert points[-1]["value"] == 150.0


async def test_pareto_report_ranks_by_revenue_with_cumulative_percent(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product2_id), "quantity": 1}], "payments": [{"amount": 300, "method": "CASH"}]},
    )
    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )

    resp = await client.post("/api/v1/reports/pareto", headers=auth_headers(token), json={})
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert lines[0]["product_id"] == str(tenant.product2_id)  # higher revenue first
    assert lines[0]["cumulative_percent"] == 66.67
    assert lines[-1]["cumulative_percent"] == 100.0


async def test_heatmap_report_returns_cells_for_recorded_sale(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )

    resp = await client.get("/api/v1/reconciliation/inventory", headers=auth_headers(token))  # sanity: still reachable
    assert resp.status_code == 200

    heatmap = await client.get("/api/v1/reports/heatmap", headers=auth_headers(token))
    assert heatmap.status_code == 200
    cells = heatmap.json()["cells"]
    assert sum(c["transactions"] for c in cells) == 1

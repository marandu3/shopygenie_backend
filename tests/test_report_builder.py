from tests.conftest import auth_headers, login


async def test_report_builder_revenue_grouped_by_product(client, tenant):
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

    resp = await client.post(
        "/api/v1/reports/builder", headers=auth_headers(token), json={"metric": "revenue", "group_by": "product"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 450.0
    labels = {r["label"]: r["value"] for r in body["rows"]}
    assert labels["Gadget"] == 300.0
    assert labels["Widget"] == 150.0


async def test_report_builder_gross_profit_single_total(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 2}], "payments": [{"amount": 300, "method": "CASH"}]},
    )

    resp = await client.post("/api/v1/reports/builder", headers=auth_headers(token), json={"metric": "gross_profit"})
    assert resp.status_code == 200
    # 2 units x (150 selling - 100 cost) = 100 gross profit
    assert resp.json()["total"] == 100.0
    assert resp.json()["rows"][0]["label"] == "Total"


async def test_report_builder_rejects_unknown_metric(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.post("/api/v1/reports/builder", headers=auth_headers(token), json={"metric": "made_up_metric"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_METRIC"

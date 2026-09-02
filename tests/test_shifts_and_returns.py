from tests.conftest import auth_headers, login


async def _open_shift(client, token, tenant, opening_cash=10000):
    # tenant fixture doesn't expose a register id directly; fetch it.
    registers = (await client.get("/api/v1/organizations/me/registers", headers=auth_headers(token))).json()
    register_id = registers[0]["id"]
    resp = await client.post(
        "/api/v1/shifts/open", headers=auth_headers(token), json={"register_id": register_id, "opening_cash": opening_cash}
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), register_id


async def test_shift_open_close_and_expected_cash(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    shift, register_id = await _open_shift(client, token, tenant, opening_cash=10000)

    # A cash sale on this register during the shift should count toward expected cash.
    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": None,
            "register_id": register_id,
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [{"amount": 150, "method": "CASH"}],
        },
    )
    assert resp.status_code == 201, resp.text

    cash_in = await client.post(
        f"/api/v1/shifts/{shift['id']}/cash-movement",
        headers=auth_headers(token),
        json={"movement_type": "CASH_IN", "amount": 5000, "reason": "petty cash top-up"},
    )
    assert cash_in.status_code == 200

    snapshot = await client.get(f"/api/v1/shifts/{shift['id']}/snapshot", headers=auth_headers(token))
    # opening 10000 + cash sale 150 + cash_in 5000 = 15150
    assert snapshot.json()["expected_cash"] == 15150.0

    close = await client.post(
        f"/api/v1/shifts/{shift['id']}/close", headers=auth_headers(token), json={"actual_cash": 15100, "closing_note": "short by 50"}
    )
    assert close.status_code == 200
    body = close.json()
    assert body["expected_cash"] == 15150.0
    assert body["actual_cash"] == 15100.0
    assert body["variance"] == -50.0
    assert body["status"] == "CLOSED"


async def test_cannot_open_two_shifts_on_same_register(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await _open_shift(client, token, tenant)
    registers = (await client.get("/api/v1/organizations/me/registers", headers=auth_headers(token))).json()

    resp = await client.post(
        "/api/v1/shifts/open", headers=auth_headers(token), json={"register_id": registers[0]["id"], "opening_cash": 1000}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SHIFT_ALREADY_OPEN"


async def test_sale_return_restores_stock_and_reduces_debt(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    sale_resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 4}],
            "payments": [],
            "allow_credit": True,
        },
    )
    sale = sale_resp.json()
    assert sale_resp.status_code == 201

    product_before = (await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))).json()
    assert product_before["current_stock"] == 6  # 10 - 4

    return_resp = await client.post(
        f"/api/v1/sales/{sale['id']}/returns",
        headers=auth_headers(token),
        json={"reason": "customer changed mind", "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 1}]},
    )
    assert return_resp.status_code == 201, return_resp.text
    body = return_resp.json()
    assert body["refund_amount"] == 150.0  # 1 unit at 150
    assert body["debt_reduction"] == 150.0  # fully absorbed by the open credit debt
    assert body["cash_refund_due"] == 0.0

    product_after = (await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))).json()
    assert product_after["current_stock"] == 7  # restored by 1

    customer_after = (await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token))).json()
    assert customer_after["outstanding_balance"] == 450.0  # original 600 - 150 refund


async def test_sale_return_cannot_exceed_sold_quantity(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    sale_resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 2}],
            "payments": [{"amount": 300, "method": "CASH"}],
        },
    )
    sale = sale_resp.json()

    resp = await client.post(
        f"/api/v1/sales/{sale['id']}/returns",
        headers=auth_headers(token),
        json={"reason": "too many", "items": [{"sale_item_id": sale["items"][0]["id"], "quantity": 99}]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "RETURN_EXCEEDS_SOLD_QUANTITY"


async def test_purchase_return_reduces_stock(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    purchase_resp = await client.post(
        "/api/v1/purchases",
        headers=auth_headers(token),
        json={"items": [{"product_id": str(tenant.product_id), "quantity": 5, "unit_cost_price": 90}]},
    )
    purchase = purchase_resp.json()
    assert purchase_resp.status_code == 201

    product_before = (await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))).json()
    assert product_before["current_stock"] == 15  # 10 + 5

    return_resp = await client.post(
        f"/api/v1/purchases/{purchase['id']}/returns",
        headers=auth_headers(token),
        json={"reason": "damaged goods", "items": [{"purchase_item_id": purchase["items"][0]["id"], "quantity": 2}]},
    )
    assert return_resp.status_code == 201, return_resp.text
    assert return_resp.json()["refund_amount"] == 180.0  # 2 x 90

    product_after = (await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))).json()
    assert product_after["current_stock"] == 13  # 15 - 2


async def test_debt_aging_report_buckets_open_debts(client, tenant):
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

    resp = await client.post("/api/v1/reports/debts/aging", headers=auth_headers(token), json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_outstanding"] == 150.0
    current_bucket = next(b for b in body["buckets"] if b["label"] == "0-30 days")
    assert current_bucket["count"] == 1
    assert current_bucket["amount"] == 150.0


async def test_inventory_reconciliation_matches_ledger(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 2}],
            "payments": [{"amount": 300, "method": "CASH"}],
        },
    )

    resp = await client.get("/api/v1/reconciliation/inventory", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["discrepancy_count"] == 0
    line = next(l for l in body["lines"] if l["product_id"] == str(tenant.product_id))
    assert line["cached_current_stock"] == line["ledger_computed_stock"]

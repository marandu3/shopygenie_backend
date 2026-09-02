from tests.conftest import auth_headers, login


async def test_sale_decrements_stock_and_computes_line_total(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 2, "discount_amount": 10}],
            "payments": [{"amount": 290, "method": "CASH"}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # (150 - 10) * 2 = 280 line total... but discount_amount is PER LINE not per unit here:
    # subtotal = 150*2 = 300, discount_total = 10, total = 290
    assert body["subtotal"] == 300.0
    assert body["discount_total"] == 10.0
    assert body["total_amount"] == 290.0

    product_resp = await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))
    assert product_resp.json()["current_stock"] == 8  # 10 - 2


async def test_oversell_is_rejected_and_stock_unchanged(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 999}],
            "payments": [{"amount": 1, "method": "CASH"}],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    product_resp = await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))
    assert product_resp.json()["current_stock"] == 10  # unchanged


async def test_discount_cannot_exceed_line_subtotal(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1, "discount_amount": 999}],
            "payments": [{"amount": 1, "method": "CASH"}],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_DISCOUNT"


async def test_multi_debt_aggregate_balance_never_overwritten(client, tenant):
    """Regression test for the old system's bug: paying one debt used to
    overwrite the customer's whole balance instead of reducing just that
    debt. Two credit sales -> two debts -> partial payment on one -> the
    customer's total outstanding balance must reflect BOTH debts correctly.
    """
    token = await login(client, tenant.owner_email, tenant.owner_password)

    async def credit_sale(product_id, qty):
        resp = await client.post(
            "/api/v1/sales",
            headers=auth_headers(token),
            json={
                "customer_id": str(tenant.customer_id),
                "items": [{"product_id": str(product_id), "quantity": qty}],
                "payments": [],
                "allow_credit": True,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    sale1 = await credit_sale(tenant.product_id, 1)  # 150
    sale2 = await credit_sale(tenant.product2_id, 1)  # 300

    customer_resp = await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token))
    assert customer_resp.json()["outstanding_balance"] == 450.0  # 150 + 300

    debts_resp = await client.get(f"/api/v1/debts?customer_id={tenant.customer_id}", headers=auth_headers(token))
    debts = debts_resp.json()
    assert len(debts) == 2

    debt_for_sale1 = next(d for d in debts if d["sale_id"] == sale1["id"])

    pay_resp = await client.post(
        f"/api/v1/debts/{debt_for_sale1['id']}/pay", headers=auth_headers(token), json={"amount": 100, "method": "CASH"}
    )
    assert pay_resp.status_code == 200
    assert pay_resp.json()["balance"] == 50.0  # 150 - 100
    assert pay_resp.json()["cleared"] is False

    customer_resp = await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token))
    # 450 - 100 = 350, NOT overwritten to just one debt's remaining balance.
    assert customer_resp.json()["outstanding_balance"] == 350.0


async def test_debt_overpayment_rejected(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [],
            "allow_credit": True,
        },
    )
    debt_id = (
        await client.get(f"/api/v1/debts?customer_id={tenant.customer_id}", headers=auth_headers(token))
    ).json()[0]["id"]

    resp = await client.post(f"/api/v1/debts/{debt_id}/pay", headers=auth_headers(token), json={"amount": 999, "method": "CASH"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "OVERPAYMENT"


async def test_void_sale_restores_stock_and_clears_debt(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    sale = (
        await client.post(
            "/api/v1/sales",
            headers=auth_headers(token),
            json={
                "customer_id": str(tenant.customer_id),
                "items": [{"product_id": str(tenant.product_id), "quantity": 3}],
                "payments": [],
                "allow_credit": True,
            },
        )
    ).json()

    product_resp = await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))
    assert product_resp.json()["current_stock"] == 7  # 10 - 3

    void_resp = await client.post(
        f"/api/v1/sales/{sale['id']}/void", headers=auth_headers(token), json={"reason": "customer changed mind"}
    )
    assert void_resp.status_code == 200
    assert void_resp.json()["status"] == "VOIDED"

    product_resp = await client.get(f"/api/v1/products/{tenant.product_id}", headers=auth_headers(token))
    assert product_resp.json()["current_stock"] == 10  # restored

    customer_resp = await client.get(f"/api/v1/customers/{tenant.customer_id}", headers=auth_headers(token))
    assert customer_resp.json()["outstanding_balance"] == 0.0  # debt cleared, not left dangling

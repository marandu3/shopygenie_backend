from tests.conftest import auth_headers, login


async def test_fifo_blends_cost_across_purchase_batches(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    # A fresh product with no stock, so both units it ever holds come from
    # purchases we control — makes the expected FIFO math exact.
    product_resp = await client.post(
        "/api/v1/products",
        headers=auth_headers(token),
        json={"name": "Rice 25kg", "unit": "bag", "cost_price": 0, "selling_price": 5000, "current_stock": 0},
    )
    product_id = product_resp.json()["id"]

    # Batch 1: 10 units @ 1000. Batch 2: 10 units @ 1300.
    await client.post(
        "/api/v1/purchases",
        headers=auth_headers(token),
        json={"items": [{"product_id": product_id, "quantity": 10, "unit_cost_price": 1000}]},
    )
    await client.post(
        "/api/v1/purchases",
        headers=auth_headers(token),
        json={"items": [{"product_id": product_id, "quantity": 10, "unit_cost_price": 1300}]},
    )

    # Sell 15 -> FIFO draws all 10 @1000 + 5 @1300 = 10000 + 6500 = 16500 total cost.
    sale_resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": None,
            "items": [{"product_id": product_id, "quantity": 15}],
            "payments": [{"amount": 75000, "method": "CASH"}],
        },
    )
    assert sale_resp.status_code == 201, sale_resp.text
    line = sale_resp.json()["items"][0]
    assert line["unit_cost_price"] == 1100.0  # 16500 / 15

    # Remaining 5 units still in stock all came from the second (1300) batch —
    # selling them now must cost 1300/unit, not blend with the exhausted batch.
    sale2 = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": None,
            "items": [{"product_id": product_id, "quantity": 5}],
            "payments": [{"amount": 25000, "method": "CASH"}],
        },
    )
    assert sale2.json()["items"][0]["unit_cost_price"] == 1300.0


async def test_fifo_falls_back_to_product_cost_price_when_no_layers_exist(client, tenant):
    """Products/customers built directly in the DB (like the `tenant` fixture
    itself) never got a cost layer — FIFO must degrade to product.cost_price
    rather than erroring, so pre-existing data keeps working."""
    token = await login(client, tenant.owner_email, tenant.owner_password)
    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={"customer_id": None, "items": [{"product_id": str(tenant.product_id), "quantity": 1}], "payments": [{"amount": 150, "method": "CASH"}]},
    )
    assert resp.status_code == 201
    assert resp.json()["items"][0]["unit_cost_price"] == 100.0  # tenant.product's cost_price


async def test_discount_above_threshold_requires_approver(client, tenant):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)

    settings_resp = await client.put(
        "/api/v1/organizations/me",
        headers=auth_headers(owner_token),
        json={"discount_auto_approve_threshold_percent": 10},
    )
    assert settings_resp.status_code == 200

    # 100/150 = 66.7% discount, well above the 10% threshold, no approver -> blocked.
    blocked = await client.post(
        "/api/v1/sales",
        headers=auth_headers(owner_token),
        json={
            "customer_id": None,
            "items": [{"product_id": str(tenant.product_id), "quantity": 1, "discount_amount": 100}],
            "payments": [{"amount": 50, "method": "CASH"}],
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "DISCOUNT_APPROVAL_REQUIRED"

    owner_me = await client.get("/api/v1/auth/me", headers=auth_headers(owner_token))
    owner_id = owner_me.json()["id"]

    approved = await client.post(
        "/api/v1/sales",
        headers=auth_headers(owner_token),
        json={
            "customer_id": None,
            "items": [{"product_id": str(tenant.product_id), "quantity": 1, "discount_amount": 100}],
            "payments": [{"amount": 50, "method": "CASH"}],
            "discount_approved_by": owner_id,
        },
    )
    assert approved.status_code == 201, approved.text


async def test_discount_approver_without_permission_is_rejected(client, tenant):
    owner_token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.put(
        "/api/v1/organizations/me", headers=auth_headers(owner_token), json={"discount_auto_approve_threshold_percent": 10}
    )

    cashier_token = await login(client, tenant.cashier_email, tenant.cashier_password)
    cashier_me = await client.get("/api/v1/auth/me", headers=auth_headers(cashier_token))
    cashier_id = cashier_me.json()["id"]

    # The Cashier role doesn't hold discounts.approve — naming them as the
    # approver must be rejected, not silently accepted.
    resp = await client.post(
        "/api/v1/sales",
        headers=auth_headers(owner_token),
        json={
            "customer_id": None,
            "items": [{"product_id": str(tenant.product_id), "quantity": 1, "discount_amount": 100}],
            "payments": [{"amount": 50, "method": "CASH"}],
            "discount_approved_by": cashier_id,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "APPROVER_LACKS_PERMISSION"


async def test_credit_sale_within_limit_succeeds_without_override(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.put(
        "/api/v1/customers/" + str(tenant.customer_id), headers=auth_headers(token), json={"credit_limit": 1000}
    )

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
    assert resp.status_code == 201, resp.text


async def test_credit_sale_exceeding_limit_requires_override(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)
    await client.put(
        "/api/v1/customers/" + str(tenant.customer_id), headers=auth_headers(token), json={"credit_limit": 100}
    )

    # The sale (150) alone exceeds the 100 limit -> blocked without an override.
    blocked = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [],
            "allow_credit": True,
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "CREDIT_LIMIT_EXCEEDED"

    owner_me = await client.get("/api/v1/auth/me", headers=auth_headers(token))
    owner_id = owner_me.json()["id"]

    approved = await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [],
            "allow_credit": True,
            "credit_override_by": owner_id,
        },
    )
    assert approved.status_code == 201, approved.text

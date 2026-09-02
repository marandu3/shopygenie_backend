from tests.conftest import auth_headers, login


async def test_debts_and_purchases_are_not_counted_as_operating_expenses(client, tenant):
    """Regression test for the old system's report bug: it folded purchases
    and outstanding debt into "total_expenditures" and subtracted that from
    revenue. Here, a credit sale (creates a debt) must NOT reduce net_profit
    beyond the product's real cost — receivables are reported separately.
    """
    token = await login(client, tenant.owner_email, tenant.owner_password)

    # Sell 1 unit of product (cost=100, sell=150) fully on credit.
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

    report_resp = await client.post("/api/v1/reports/summary", headers=auth_headers(token), json={})
    assert report_resp.status_code == 200
    report = report_resp.json()

    assert report["revenue"] == 150.0
    assert report["cogs"] == 100.0
    assert report["gross_profit"] == 50.0
    # The debt is fully outstanding — it must be reported as a receivable,
    # never subtracted from profit as if it were an expense.
    assert report["outstanding_receivables"] == 150.0
    assert report["operating_expenses"] == 0.0
    assert report["net_profit"] == 50.0  # NOT (150 - 150) = 0, and NOT negative


async def test_expense_reduces_net_profit_but_not_gross_profit(client, tenant):
    token = await login(client, tenant.owner_email, tenant.owner_password)

    await client.post(
        "/api/v1/sales",
        headers=auth_headers(token),
        json={
            "customer_id": str(tenant.customer_id),
            "items": [{"product_id": str(tenant.product_id), "quantity": 1}],
            "payments": [{"amount": 150, "method": "CASH"}],
        },
    )
    await client.post(
        "/api/v1/expenses",
        headers=auth_headers(token),
        json={"description": "Electricity", "amount": 20, "expense_date": "2026-01-01"},
    )

    report = (await client.post("/api/v1/reports/summary", headers=auth_headers(token), json={})).json()
    assert report["gross_profit"] == 50.0  # unaffected by the expense
    assert report["operating_expenses"] == 20.0
    assert report["net_profit"] == 30.0  # 50 - 20

"""Central registry of permission codes and the system role -> permission map.

Adding a new permission = add the constant + attach it to whichever system
roles should have it in SYSTEM_ROLE_PERMISSIONS. Nothing else in the codebase
should hard-code a role name to decide access — always check a permission.
"""

# --- Sales / POS ---
SALES_VIEW = "sales.view"
SALES_CREATE = "sales.create"
SALES_VOID = "sales.void"
SALES_REFUND = "sales.refund"

# --- Products ---
PRODUCTS_VIEW = "products.view"
PRODUCTS_CREATE = "products.create"
PRODUCTS_UPDATE = "products.update"
PRODUCTS_DELETE = "products.delete"

# --- Inventory ---
INVENTORY_VIEW = "inventory.view"
INVENTORY_ADJUST = "inventory.adjust"

# --- Purchases / Suppliers ---
PURCHASES_VIEW = "purchases.view"
PURCHASES_CREATE = "purchases.create"
PURCHASES_VOID = "purchases.void"
PURCHASES_RETURN = "purchases.return"
SUPPLIERS_MANAGE = "suppliers.manage"

# --- Shifts / cash management ---
SHIFTS_OPEN = "shifts.open"
SHIFTS_VIEW = "shifts.view"

# --- Reconciliation ---
RECONCILIATION_VIEW = "reconciliation.view"

# --- Audit ---
AUDIT_VIEW = "audit.view"

# --- Customers / Debts ---
CUSTOMERS_VIEW = "customers.view"
CUSTOMERS_CREATE = "customers.create"
CUSTOMERS_UPDATE = "customers.update"
DEBTS_VIEW = "debts.view"
DEBTS_COLLECT = "debts.collect"

# --- Expenses ---
EXPENSES_VIEW = "expenses.view"
EXPENSES_CREATE = "expenses.create"
EXPENSES_APPROVE = "expenses.approve"

# --- Reports ---
REPORTS_VIEW = "reports.view"
REPORTS_EXPORT = "reports.export"

# --- Workers / org administration ---
WORKERS_INVITE = "workers.invite"
WORKERS_UPDATE = "workers.update"
WORKERS_SUSPEND = "workers.suspend"
ROLES_MANAGE = "roles.manage"

# --- Settings / billing ---
SETTINGS_MANAGE = "settings.manage"
BILLING_VIEW = "billing.view"
BILLING_MANAGE = "billing.manage"

# --- Approvals (discount thresholds, credit-limit overrides) ---
DISCOUNTS_APPROVE = "discounts.approve"
DEBTS_OVERRIDE_LIMIT = "debts.override_limit"

# --- Inventory transfers ---
TRANSFERS_VIEW = "transfers.view"
TRANSFERS_REQUEST = "transfers.request"
TRANSFERS_APPROVE = "transfers.approve"
TRANSFERS_RECEIVE = "transfers.receive"

# --- Held sales ---
HELD_SALES_VIEW = "held_sales.view"

ALL_PERMISSIONS: list[str] = [
    SALES_VIEW, SALES_CREATE, SALES_VOID, SALES_REFUND,
    PRODUCTS_VIEW, PRODUCTS_CREATE, PRODUCTS_UPDATE, PRODUCTS_DELETE,
    INVENTORY_VIEW, INVENTORY_ADJUST,
    PURCHASES_VIEW, PURCHASES_CREATE, PURCHASES_VOID, PURCHASES_RETURN, SUPPLIERS_MANAGE,
    SHIFTS_OPEN, SHIFTS_VIEW,
    RECONCILIATION_VIEW,
    CUSTOMERS_VIEW, CUSTOMERS_CREATE, CUSTOMERS_UPDATE, DEBTS_VIEW, DEBTS_COLLECT,
    EXPENSES_VIEW, EXPENSES_CREATE, EXPENSES_APPROVE,
    REPORTS_VIEW, REPORTS_EXPORT,
    WORKERS_INVITE, WORKERS_UPDATE, WORKERS_SUSPEND, ROLES_MANAGE,
    SETTINGS_MANAGE, BILLING_VIEW, BILLING_MANAGE,
    DISCOUNTS_APPROVE, DEBTS_OVERRIDE_LIMIT,
    TRANSFERS_VIEW, TRANSFERS_REQUEST, TRANSFERS_APPROVE, TRANSFERS_RECEIVE,
    HELD_SALES_VIEW,
    AUDIT_VIEW,
]

# System (built-in) roles. Tenant owners can later define custom roles with
# their own permission subsets — this map only seeds the built-ins.
SYSTEM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Tenant Owner": ALL_PERMISSIONS,
    "Manager": [
        SALES_VIEW, SALES_CREATE, SALES_VOID, SALES_REFUND,
        PRODUCTS_VIEW, PRODUCTS_CREATE, PRODUCTS_UPDATE,
        INVENTORY_VIEW, INVENTORY_ADJUST,
        PURCHASES_VIEW, PURCHASES_CREATE, PURCHASES_VOID, PURCHASES_RETURN, SUPPLIERS_MANAGE,
        SHIFTS_OPEN, SHIFTS_VIEW, RECONCILIATION_VIEW,
        CUSTOMERS_VIEW, CUSTOMERS_CREATE, CUSTOMERS_UPDATE, DEBTS_VIEW, DEBTS_COLLECT,
        EXPENSES_VIEW, EXPENSES_CREATE, EXPENSES_APPROVE,
        REPORTS_VIEW, REPORTS_EXPORT,
        WORKERS_INVITE, WORKERS_UPDATE, WORKERS_SUSPEND,
        AUDIT_VIEW,
        DISCOUNTS_APPROVE, DEBTS_OVERRIDE_LIMIT,
        TRANSFERS_VIEW, TRANSFERS_REQUEST, TRANSFERS_APPROVE, TRANSFERS_RECEIVE,
        HELD_SALES_VIEW,
    ],
    "Cashier": [
        SALES_VIEW, SALES_CREATE, SALES_REFUND,
        PRODUCTS_VIEW,
        SHIFTS_OPEN,
        CUSTOMERS_VIEW, CUSTOMERS_CREATE,
        DEBTS_VIEW, DEBTS_COLLECT,
        HELD_SALES_VIEW,
    ],
    "Inventory Manager": [
        PRODUCTS_VIEW, PRODUCTS_CREATE, PRODUCTS_UPDATE,
        INVENTORY_VIEW, INVENTORY_ADJUST,
        PURCHASES_VIEW, PURCHASES_CREATE, PURCHASES_RETURN, SUPPLIERS_MANAGE,
        RECONCILIATION_VIEW,
        REPORTS_VIEW,
        TRANSFERS_VIEW, TRANSFERS_REQUEST, TRANSFERS_RECEIVE,
    ],
    "Accountant": [
        SALES_VIEW, PURCHASES_VIEW,
        SHIFTS_VIEW, RECONCILIATION_VIEW,
        CUSTOMERS_VIEW, DEBTS_VIEW, DEBTS_COLLECT,
        EXPENSES_VIEW, EXPENSES_CREATE, EXPENSES_APPROVE,
        REPORTS_VIEW, REPORTS_EXPORT,
        BILLING_VIEW,
    ],
    "Viewer": [
        SALES_VIEW, PRODUCTS_VIEW, INVENTORY_VIEW, PURCHASES_VIEW,
        CUSTOMERS_VIEW, DEBTS_VIEW, EXPENSES_VIEW, REPORTS_VIEW,
    ],
}

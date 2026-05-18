"""
Single source of truth for user roles.
Change access rules here — no need to grep the whole codebase.
"""

ROLE_OWNER   = "owner"
ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLE_STAFF   = "staff"

ALL_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER, ROLE_STAFF}

ROLE_LEVELS = {
    ROLE_STAFF:   0,
    ROLE_CASHIER: 1,
    ROLE_MANAGER: 2,
    ROLE_ADMIN:   3,
    ROLE_OWNER:   4,
}

# ── Ready-made tuples for require_role() ──────────────────────
OWNER_ONLY          = (ROLE_OWNER,)
ANALYTICS_ROLES     = (ROLE_OWNER, ROLE_ADMIN)
CLIENT_ACCESS_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER)
TRANSACTION_ROLES   = (ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER)

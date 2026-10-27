# Manual cashback and refunds

## Settings and purchases

An owner selects `earning_mode` (`automatic` or `manual`) in the existing
settings page. It belongs to the network's loyalty settings, not all tenants.
Existing organizations stay in automatic mode. In manual mode both purchase
forms require a percentage, including zero. `manual_percent` accepts 0 to 100
with up to two decimal places. Automatic mode rejects a manual override.

`GET /api/transactions/earning-options` exposes only this mode to transaction
roles; it does not expose the owner's settings API to cashiers.

For backward compatibility, `paid_amount` retains its historical meaning:
the discounted purchase amount BEFORE bonus redemption, defaulting to `amount`.
It must not exceed `amount`. It is NOT cash received. The earning base is
`paid_amount - redeem_points`. This contract must be preserved by the future
Apps Script adapter. Example: 250000 before bonuses, 10000 redeemed, 5% selected
means 12000 earned. Monetary amounts and points remain integer KZT/points;
earnings round down. The chosen rate, mode, base and operator are persisted.

Optional UUID `request_id` makes a purchase retry safe. Reuse it with exactly
the same payload after a timeout. A changed payload with that ID returns 409.
The browser retains it for retries until success or the payload changes.
Requests without this field remain backward compatible but cannot deduplicate.

## Refund policy

Only owner/admin/manager can refund. Purchases remain scoped to authorized
branches and the customer network. Purchase, reward cancellation, restored
redemption and cached balance are committed together or rolled back together.
PostgreSQL wallet and purchase row locks serialize concurrent operations.

Refund amount uses the original `paid_amount` basis. It is a loyalty correction,
not a bank/payment-provider money transfer. Over-refunds are rejected, never
silently reduced. Cumulative proportions use the original earned/redeemed totals;
the last refund cancels/restores the entire remaining rounding residue. Current
settings or the currently selected percentage do not recalculate original earnings.

Unspent pending and available purchase rewards are cancelled first. Spent rewards
can be recovered from other available points, including redemption restored by
this refund. If that is insufficient the entire operation returns 409 without
changes. No implicit debt or negative wallet is introduced. A reward that has
already expired is not charged a second time against unrelated points.
Restored redemptions activate immediately and use the current configured TTL,
as in the existing policy; original redemption-to-grant history is not available.

Optional UUID `request_id` deduplicates retries within a purchase, including
after a full refund. Different data with the same ID returns 409. New requests
against a fully refunded purchase are rejected. Each successful refund has an
immutable `transaction_refunds` row with operator, amount, cancelled/restored
points, comment and timestamp. Authorized staff can read it at
`GET /api/transactions/{id}/refunds`.

## Deployment and historical data

Startup creates the refund journal table and adds missing columns through
`run_startup_migrations`. Existing purchase snapshots remain NULL: no historical
percentage is invented. Existing refunded transactions get a proportional
baseline for the new counters. Old per-event rounding cannot be reconstructed
without a journal; past discrepancies are NOT retroactively repaired. Back up
the database before deployment and reconcile old refunds separately.

New refunds reduce revenue aggregates and cumulative tier spend. Reporting
assigns net revenue to the original purchase date; it is not a cashflow report
of refunds grouped by their refund date.

## Checks

Run `python -m pytest test/`. Tests cover manual and automatic modes, zero and
fractional rates, net bases, repeated requests, full/partial/oversized refunds,
pending/expired/spent rewards, rollback, tenant isolation, tiers and migrations.
Production concurrency must additionally be verified on PostgreSQL; SQLite
does not implement `SELECT FOR UPDATE` semantics.

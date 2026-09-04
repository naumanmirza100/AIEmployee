# Stripe integration

Everything billing-related: local setup, the webhook endpoint, and the move to a
live account.

The integration is hand-rolled against the `stripe` Python SDK (pinned to `8.0.0`
in `requirements.txt`). There is no `dj-stripe` or similar helper — every customer,
checkout, webhook and catalogue sync is explicit code in this repo.

---

## Who owns what

This matters more than any individual setting, because getting it backwards causes
the confusing bugs.

| Data | Source of truth | Direction |
|---|---|---|
| Plans / prices (the catalogue) | **Our database** (`AgentPlan`) | pushed to Stripe by `core/stripe_sync.py` |
| Subscriptions, invoices, payment methods | **Stripe** | pulled in via webhooks + read live in the Billing tab |

A dashboard-made price edit is adopted back into `AgentPlan` when its intent is
unambiguous (see [Catalogue drift](#catalogue-drift)), but the catalogue is still
ours — Stripe is not a place to author plans.

---

## Environment variables

```
STRIPE_SECRET_KEY=sk_test_...       # or sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_test_...  # served to the frontend by /modules/billing-overview
STRIPE_WEBHOOK_SECRET=whsec_...     # see below — NOT interchangeable
FRONTEND_URL=http://localhost:3000  # checkout success/cancel + portal return
BACKEND_URL=http://localhost:8000
```

Two traps:

- **`FRONTEND_URL` must have no trailing whitespace.** `settings.py` does
  `.rstrip('/')`, which strips slashes but *not* spaces, and a stray space produces
  a malformed `success_url` that Stripe rejects.
- **`STRIPE_WEBHOOK_SECRET` is per-destination *and* per-mode.** The value from
  `stripe listen` is not the value from a registered endpoint, and test is not live.
  Mixing them up gives 400s and silently unsynced subscriptions.

---

## Webhooks

Endpoint: `POST <BACKEND_URL>/api/modules/stripe-webhook`
(`api/views/module_purchase.py` → `stripe_webhook`). Unauthenticated and
`@csrf_exempt` by design — Stripe authenticates by signature, not session.

### Events to subscribe to

```
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.paid
invoice.payment_failed
invoice.payment_action_required
price.created
price.updated
product.updated
```

Anything else is acknowledged with 200 and ignored without writing a dedup row.

### Local development

```bash
stripe listen --forward-to localhost:8000/api/modules/stripe-webhook
```

This is an **ephemeral CLI tunnel**. It does not appear under Workbench → Webhooks →
Destinations, and it will never show up there — an empty Destinations page while
webhooks are arriving is expected during local dev, not a misconfiguration.

Take the `whsec_...` the CLI prints into `STRIPE_WEBHOOK_SECRET` and restart Django.
It changes each time you start the CLI unless you pass `--api-key`.

### Deployed environments — including sandbox

`stripe listen` only reaches `localhost`. **The moment the backend runs anywhere
else, a registered destination is required — this is not only a live-mode task.**

1. Dashboard → Developers → Webhooks → Add destination
2. URL: `https://<your-backend-host>/api/modules/stripe-webhook` (public HTTPS)
3. Select the events listed above
4. Copy that destination's `whsec_...` into the environment and redeploy

Registered destinations are also the only way Stripe retries a failed delivery
(exponential backoff, ~3 days). The CLI does not retry, so a handler bug during
local dev loses the event.

### Reliability

- Every event is claimed in `StripeWebhookEvent` (unique `event_id`) *before* the
  handler runs, so a redelivery cannot process twice.
- The handler runs inside one transaction. On failure the claim is released and a
  500 returned, so Stripe retries and no partial writes survive.
- `python manage.py prune_stripe_events --commit` bounds that table (30-day default;
  it refuses a window under 7 days, which would let a retry re-process).

---

## Failed payments (Smart Retries)

Configured in the **Dashboard**, not in code: Billing → Subscriptions and emails →
Manage failed payments. Turn on Smart Retries, pick the retry window and customer
emails, and choose what happens after the final failure.

Set the final-failure behaviour to **cancel the subscription** — that is what the app
assumes. `customer.subscription.deleted` marks the purchase cancelled and, when it
arrives from `past_due`, records `cancelled_reason='payment_failed'` and tells the
customer their access ended.

The app already handles the rest of the cycle:

| Event | Effect |
|---|---|
| `invoice.payment_failed` | purchase → `past_due`, critical notification |
| `invoice.payment_action_required` | notification with the hosted invoice link so the customer can complete 3DS |
| `invoice.paid` | `past_due` → `active`, period extended — a successful retry restores access on its own |
| `customer.subscription.deleted` | → `cancelled` (+ notification if dunning gave up) |

---

## Catalogue drift

An admin editing a price in the Stripe dashboard is adopted back into `AgentPlan`
via `price.created` / `price.updated` → `core/stripe_sync.adopt_stripe_price`.

- Prices this app mints carry `metadata.plan_id`; hand-made ones do not. That is how
  our own writes echoing back are recognised and ignored.
- Adoption requires exactly one active plan for that agent+interval, an active USD
  recurring price, and a Product carrying `metadata.agent_name`.
- Anything ambiguous is refused and logged, never guessed.

Webhooks can be missed, so reconcile periodically:

```bash
python manage.py reconcile_stripe_catalog            # report
python manage.py reconcile_stripe_catalog --commit   # adopt unambiguous drift
```

It also reports plans with no Stripe Price, broken links, and agents with more than
one active Price (which must be resolved by archiving the wrong ones in Stripe).

---

## Changing a price

Edit the plan in Admin → Agent Plans. On save:

1. A new Stripe Price is minted (Prices are immutable, so there is no other way).
2. **Existing subscribers are moved onto it**, effective at their next renewal —
   next month for monthly, next year for yearly. `proration_behavior='none'` means
   nobody is charged mid-cycle.
3. Each affected company is notified, with their own renewal date.
4. The old Price is archived — which stops new checkouts but does *not* stop billing
   for anyone still on it, hence step 2.

An agent may have at most one active monthly and one active yearly plan, enforced by
a database constraint. Superseded plans are deactivated, never deleted: a switched-off
row can still own the Price a live subscription bills against.

---

## Going live

Test and live are entirely separate object spaces. A `cus_`, `sub_` or `price_`
created with test keys does not exist under live keys.

```bash
# 1. swap all three keys in .env to their live values, then:
python manage.py clear_test_stripe_ids            # dry run
python manage.py clear_test_stripe_ids --commit   # null out test-mode ids
python manage.py sync_stripe_plans                # recreate Products + Prices live
```

Then, in the live dashboard:

- register the webhook destination (above) and take its **live** `whsec_`
- configure the Customer Portal (Settings → Billing → Customer portal) — per-mode
  config; without it the "billing address, tax ID and receipts" link returns 503
- configure Smart Retries (above)
- confirm the account is activated (business details + bank account), or live
  charges fail

**Known caveat:** `clear_test_stripe_ids` identifies test data by a `_test_` infix,
which current Stripe IDs do not carry (e.g. `cus_V94yZeHdvv1i1n`). The default run
will report 0 rows. Use `--all`, having confirmed the dataset really is all test.

The sandbox indicator badge and any "sandbox" wording in the card form come from
Stripe.js and disappear on their own under live keys.

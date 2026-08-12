# Billing architecture

How Agora Origin takes money, what happens when it can't, and what is
deliberately delegated to Stripe.

Related: `docs/KNOWN_LIMITATIONS.md` (what has and has not been exercised
against real Stripe), `app/billing/`, `app/routers/billing.py`.

---

## 1. The four plans

| Plan | Price | How you get it | Trial |
|---|---|---|---|
| Starter | €499/mo | Sign up | **14 days, no card** |
| Growth | €999/mo | Stripe Checkout | none |
| Business | €1,999/mo | Stripe Checkout | none |
| Enterprise | from €3,500/mo | Sales contract, set by staff | none |

Only Growth and Business are self-serve purchases (`SELF_SERVE_PAID_PLANS`
in `app/billing/service.py`). Starter is the trial and Enterprise requires
a signed agreement, so neither has a Stripe Price id.

Prices live in `apps/web/lib/pricing-config.ts` for display and in Stripe
for charging. **These are two separate sources of truth** — changing one
does not change the other. That is a deliberate trade (Stripe owns money,
the repo owns copy) but it means a price change is a two-place edit.

## 2. Entitlements vs. billing state

Two different questions, deliberately kept apart:

- **`Organization.plan_key`** — what the org is entitled to. Every feature
  check in the product resolves through `app.billing.service`, never by
  branching on the plan key inline (spec §64).
- **`Subscription`** — what is true about the money: trialing, paid,
  lapsed, or cancelled, plus the Stripe ids.

`plan_key` is written **only** by the billing service, and only in
response to a verified Stripe event or a real downgrade.

## 3. How locking actually works

When a trial lapses or a subscription is cancelled, two things happen.

**1. Entitlements resolve to `LOCKED_ENTITLEMENTS`** — every numeric limit
`0`, every feature flag `False`. This is what the UI reads to grey the
right things out.

**2. Mutating requests are refused centrally**, in
`app.dependencies._enforce_subscription_lock`.

The second mechanism exists because the first is not sufficient, and it
is worth being blunt about why: **only two call sites in the entire
codebase consult entitlements** — invitation creation
(`app/core/invitations.py`) and SSO login (`app/identity/sso.py`).
Zeroing entitlement values therefore locks exactly those two things. An
organization "locked" by entitlements alone could still create documents,
workflows, tasks, and everything else.

So the real lock is a single check in `get_org_context`, the one place
every org-scoped request already passes through. `POST`/`PUT`/`PATCH`/
`DELETE` return **402** when the org is locked. `GET` is untouched.

Two path prefixes stay writable while locked:

- `/api/v1/billing` — otherwise there is no way back
- `/api/v1/organizations/current/deletion-request` — a data right, not
  something to hold behind a payment

Reads, and the `GET /organizations/current/data-export` download, keep
working. That is what makes "your organization and its data are
preserved" true rather than a slogan. Locking a customer out of their own
records over a lapsed invoice would be a data-hostage pattern, and for EU
customers it would also sit badly against their right to their own data.

**Trial expiry is evaluated lazily**, from `trial_ends_at`, in
`resolve_access_state` — not by a scheduled job flipping statuses. A cron
that fails to fire must not silently hand out free access, and this way
there is no cron to fail.

`past_due` deliberately does **not** lock. Stripe retries a failed
payment for days; killing access on the first decline punishes a customer
for an expiring card.

## 4. The purchase flow

```
POST /api/v1/billing/checkout {plan_key}
  -> create Stripe Customer (once, committed before Checkout)
  -> create Checkout Session
  -> { checkout_url }          <- browser redirects here
                                  ** plan is NOT changed **

Stripe hosted payment page
  -> POST /api/v1/billing/webhook  (checkout.session.completed)
     -> verify signature
     -> record event id (idempotency)
     -> set Subscription.status = active, Organization.plan_key = <plan>
```

**The webhook is the only path that grants a paid plan.** Reaching the
success URL by typing it, or abandoning the payment form, grants nothing.
This is the single most important property of the design: the browser is
never trusted to report that money moved.

`PUT /billing/current` still exists but now only accepts a downgrade to
Starter. It used to accept any plan key, which meant an org_admin could
assign themselves Enterprise for free.

## 5. Webhook security

`verify_webhook_signature` implements Stripe's scheme directly:

- HMAC-SHA256 over `"{timestamp}.{raw_body}"` with `STRIPE_WEBHOOK_SECRET`
- **raw body** — re-serialized JSON will not verify, which is why the
  route reads `await request.body()` before any parsing
- `hmac.compare_digest`, so a mismatch cannot be found a byte at a time
  by timing the response
- 5-minute timestamp tolerance, so a captured signature is not replayable
  indefinitely
- unverifiable events are **400 and never retried into**, not 500

Idempotency is a uniquely-indexed `billing_webhook_events.stripe_event_id`.
Stripe delivers at-least-once and retries on any non-2xx, so a replay must
not extend a period or re-grant a plan twice.

## 6. Configuration

```bash
STRIPE_SECRET_KEY=sk_test_...        # absent -> checkout returns 409, honestly
STRIPE_WEBHOOK_SECRET=whsec_...      # absent -> webhooks cannot be verified
STRIPE_PRICE_GROWTH=price_...        # recurring EUR price, 999.00/month
STRIPE_PRICE_BUSINESS=price_...      # recurring EUR price, 1999.00/month
TRIAL_PERIOD_DAYS=14                 # optional
```

With no keys set, the Starter trial still works completely (it takes no
card) and checkout refuses with a 409 that says payments are not
configured — it never fakes a successful purchase. The billing page reads
`payments_configured` and disables its upgrade buttons rather than
offering a dead end.

**Before enabling in production**, run one real test-mode purchase:

```bash
stripe listen --forward-to localhost:8001/api/v1/billing/webhook
# then buy Growth with card 4242 4242 4242 4242
```

This is the part no test in this repo covers — see
`docs/KNOWN_LIMITATIONS.md`.

## 7. VAT and reverse charge

Handled by Stripe Tax, enabled per Checkout Session:

- `automatic_tax[enabled]=true` — Stripe computes the VAT rate for the
  customer's location
- `tax_id_collection[enabled]=true` — Checkout prompts business buyers for
  a VAT number, which is what lets Stripe apply **B2B reverse charge**
  instead of adding VAT
- `billing_address_collection=required` — both of the above need an
  address to work

The collected VAT number is stored on `Subscription.tax_id` **for display
only**. Stripe remains the authority on whether reverse charge actually
applied to any given invoice; this code never computes tax.

Stripe Tax must be enabled and the origin address registered in the Stripe
Dashboard. That is dashboard configuration, not code.

## 8. What is delegated to Stripe on purpose

Card updates, invoice history, and cancellation all go through the
**Stripe-hosted billing portal** (`POST /billing/portal`).

Checkout + portal was chosen over Stripe Elements specifically so that
**card data never touches this system** — which keeps the PCI scope at
SAQ-A rather than SAQ-A-EP. Building those screens here would have meant
handling card fields for a worse outcome.

Dunning beyond Stripe's retry schedule, and proration on mid-cycle plan
changes, are left to Stripe's defaults.

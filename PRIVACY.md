# Data handling (GDPR)

This service captures inbound marketing leads, so it processes personal data.
This note describes what is held, why, and how to action a data-subject request.
It is engineering documentation, not legal advice.

## What personal data is stored

Captured by the lead webhook (`POST /leads/webhook`) and held in the `leads`
table:

- name, company, email
- service interest (derived from the submission)
- the full original form payload, kept verbatim as JSON (`raw_data`) for audit
- a marketing-consent flag (`consent`)
- staff notes added later in the inbox

No payment data, no special-category data, no third-party tracking.

## Lawful basis and consent

- The webhook records a `consent` flag from the form (`consent` truthy:
  `true`/`on`/`yes`/`1`). Send it from your form's consent checkbox.
- `consent` is surfaced on every lead in the inbox so staff can see the basis
  for contact before reaching out.
- Leads without consent are still scored and stored (so nothing is silently
  dropped) but the missing consent is visible; do not market to them without a
  separate lawful basis.

## Retention

- Demo mode seeds illustrative leads and stores them in a local SQLite file
  (`data/marketing.db`); nothing leaves the machine.
- In production, set a retention period appropriate to your basis and delete
  leads past it (the erasure endpoint below is the mechanism). There is no
  automatic expiry job in this demo.

## Right to erasure (right to be forgotten)

`DELETE /leads/{id}` (admin-authenticated when `DEMO_MODE=false`) hard-deletes
the lead row, including the verbatim `raw_data` payload. Nothing is retained
after the call; it returns `204 No Content`.

To erase by person rather than id: look the lead up in the inbox
(`GET /leads`), then issue the delete with its id.

## Access control

- The lead inbox, notes, and erasure endpoints require the `X-API-Key` admin
  header when `DEMO_MODE=false` (see `.env.example`).
- The webhook itself is unauthenticated by design but rate-limited, size-capped,
  and supports an optional shared secret (`WEBHOOK_SECRET`).

## Data location and transfers

- All data stays in the configured database (`DATABASE_URL`). No data is sent to
  any third party in demo mode.
- In production, lead routing emails personal data to the configured contacts;
  ensure those recipients and any swapped-in database are in scope of your own
  processing records.

# Weekly test — marketing repo half (segment sync, abandoned-cart, birthday)

Companion to `weekly_smoke_test.py` (which covers hotboat-whatsapp only).
This half lives in `hotboat-email-marketing-spec` and needs a logged-in
session, so it isn't part of the automated script — walk through it by hand,
roughly weekly, alongside running the script.

**Why not automated:** the admin endpoints below require a real login
(`require_admin`/`require_editor`, JWT-based), and I don't have — and
shouldn't be given — your password to script around that. If you'd rather
this be fully automated later, the options are: (a) add a service-account/API-key
auth path to that backend, or (b) accept a browser-driven weekly run where you
log in once and I click through it. Neither is set up yet.

---

## 1. Segment sync — "signed T&C → counted as an experience"

This is the check for your original question: does someone who signs the
T&C actually get added to the right segment, with their reservation
associated?

**Setup (once, in hotboat-whatsapp):**
```bash
python -c "
import requests
r = requests.post('https://kia-ai.hotboatchile.com/api/booking/create', json={
  'customer_name':'Sync Test','customer_phone':'+56900005555',
  'customer_email':'tomasdamjanic+syncsmoke@gmail.com',
  'num_adultos':2,'num_ninos':0,'num_people':2,
  'booking_date':'2026-12-15','booking_time':'11:00',
  'extras':[],'has_flex':False,'skip_payment':True,
})
print(r.json())
ref = r.json()['booking_ref']
r2 = requests.post(f'https://kia-ai.hotboatchile.com/api/firma/{ref}', json={
  'passenger_name':'Sync Test Passenger',
  'passenger_email':'tomasdamjanic+syncsmoke@gmail.com',
  'passenger_phone':'+56900005555',
  'passenger_birthday':'1990-01-01','accepted_tc':True,
})
print(r2.json())
"
```

**Trigger the sync** (log into the marketing dashboard first):
```
POST /api/sync/run   (require_admin)
```
Whatever base URL the frontend's `NEXT_PUBLIC_API_URL` points at — as of
this writing that's the staging Railway deployment
(`hotboat-email-marketing-spec-staging.up.railway.app`), not localhost,
confirmed via `frontend/.env`. Check that hasn't changed before assuming
staging vs. production. Returns `{"status": "done", "created": N, "updated": N, "skipped": N}`.

**Verify:**
```
GET /api/contacts?search=tomasdamjanic+syncsmoke@gmail.com
```
The returned contact should have `veces_hotboat >= 1` and
`ultima_reserva_hotboat` pointing at the booking you just created
(booking_ref, fecha, servicio, etc. should match).

**Cleanup:** delete the test `all_appointments`/`hotboat_signatures` rows
(same pattern as `weekly_smoke_test.py`'s `cleanup()`) and the test
`Contact` row via the dashboard or `DELETE /api/contacts/{id}`.

**Known gap (from the 2026-07-23 investigation, worth re-checking
periodically):** there's no single pre-built segment named "vivieron la
experiencia" — it's split across two seeded segments ("Primera
experiencia" = veces_hotboat==1, "Clientes recurrentes" = veces_hotboat>=2).
If you want one combined segment, that's a dashboard config change, not a
code fix.

---

## 2. Abandoned-cart and birthday emails — template-only check (safe)

These automations tick against the real database every ~60 seconds with
**no dry-run mode** — inserting real-looking test data to exercise the
actual matching logic will send a real email via the real Resend key
within about a minute. You chose NOT to run that as a routine weekly
check (too easy to fire accidentally), so this section only covers the
safe path: confirming the email **template** still renders and sends,
without touching real matching logic.

**Prerequisite:** `NOTIFY_EMAIL` must be set in that backend's environment
(as of the 2026-07-23 investigation it was **not set** in
`backend/.env`, which makes `/test` 400 — check the actual deployed
environment's variables, since local `.env` and the deployed one can differ).

**Safe test-send** (per automation, from the Automations page or directly):
```
POST /api/automations/{automation_id}/test
```
Find the two automation IDs (`trigger_type = "abandoned_booking"` and
`trigger_type = "birthday"`) from the Automations list in the dashboard.
This sends the template with fake sample data to `NOTIFY_EMAIL` only —
no real customer data is touched, no `all_appointments`/`Contact` rows
are read. Confirm the email arrives and looks right (correct branding,
links, discount-code placeholder rendering, etc).

**What this does NOT verify:** whether the automation actually detects a
real abandoned booking or a real birthday when one occurs. That requires
the real-data test described above (in the AskUserQuestion you answered
"solo prueba de plantilla, no de lógica real") — do that deliberately,
not as a routine weekly habit, if you ever want to verify the matching
logic itself. If you do: use a test email address you control, confirm
the send in Resend's dashboard or the inbox, and delete the test
`all_appointments` row (or reset the test `Contact`'s birthday)
immediately after so it doesn't fire again next week.

---

## Suggested cadence

Run `python weekly_smoke_test.py` (fully automated, safe) whenever you like —
weekly, or wire it into a scheduled task. Walk through this document's
Section 1 (segment sync) roughly as often; it's cheap and safe. Only do
Section 2's real-logic variant occasionally, deliberately, when you
actually want to verify abandoned-cart/birthday detection still works.

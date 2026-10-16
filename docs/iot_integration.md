# IoT shift-data integration

The IoT vendor POSTs one reporting window per vessel (12 hours). InsiteFuel turns each window into a
MORNING or EVENING shift, fills it, and closes it automatically 11 hours after the data arrived
unless a person closes it first.

## Endpoint

`POST /api/iot/shift-data`  — header `X-API-Key: <shared secret>`, JSON body = one object **or an array** of objects
(the format of `smaplextrl.json`).

| Result | HTTP | Meaning |
|---|---|---|
| all items `PROCESSED` / `DUPLICATE` / `AWAITING_MAPPING` | 200 | applied, already known, or safely stored until an administrator maps it |
| any item `REJECTED` | 422 | body lists the reason per item (`results[].errors`); payload is stored and can be re-processed |
| unexpected server error | 500 | payload is still stored as REJECTED |
| bad / missing key | 401 | |
| `INSITEFUEL_IOT_API_KEY` not set | 503 | endpoint disabled |

Array items are processed oldest window first, each in its own transaction.

## What happens to a payload

1. Validated (`services/iot_parser.py`). Rejected: bad structure/times, run outside the window, stop <= start,
   negative numbers, window crossing midnight or both halves, **overlapping runs of the same engine**.
   Warnings only: vendor duration vs start/stop mismatch, `totals` not matching the runs.
2. Identical payload already processed -> a stored `DUPLICATE` inbox entry; no ledger or shift changes. Same
   vessel + window with different content -> rejected (correct it with the admin editing tools, do not re-send).
3. `vesselId` -> `vessels.iot_vessel_id`; engine name -> `equipment.iot_engine_name`.
4. The reporting window determines the shift: a window starting from 00:00 through 11:59 maps to MORNING on its
   start date; one starting from 12:00 through 23:59 maps to EVENING on its start date. Times are read as IST.
   Normal shift-chain rules still apply: all earlier shifts must be closed and the latest earlier shift supplies
   opening fuel. Windows must arrive oldest first; an older or repeated-but-different window is rejected, a large gap only warns.
5. Shift created through `FuelService.get_or_create_shift` (normal chain rules, opening fuel from the previous
   shift), `source = IOT`, `advancement_m = 0`, `dredging_hours = 0`, `auto_close_at = arrival + 11 h`.
   If the previous shift is still open: closed automatically when it is IoT-created, otherwise the payload is rejected
   (close it manually, then re-process).
6. Each `engineRunDetails[].fuelConsumed` value is consumed as **litres** for that specific engine run and is
   written unchanged (to 0.001 L precision) to the engine event and fuel ledger; no millilitre conversion occurs.
   Runs with `"N/A"`/0 fuel are skipped (warning). `totals[]` remains informational and is not posted as another
   consumption entry, which would double-count the individual runs.
   `refill` -> RECEIPT, `drain` -> ADJUSTMENT OUT (switch off with `INSITEFUEL_IOT_POST_REFILLS_TO_LEDGER=false`).
7. Sensor `rob` total is compared with the ledger closing fuel; a difference is reported, never auto-adjusted.
8. All of it is one transaction; on any failure nothing is applied and the payload is kept as REJECTED.

## Auto-close

A background task (every `INSITEFUEL_IOT_AUTO_CLOSE_CHECK_SECONDS`, default 300) closes IoT shifts past `auto_close_at`.
It waives only the sounding and the Dredger advancement/dredging-hours requirement (recorded in the audit log, and
`close_source = AUTO_IOT`). A person closing the shift manually still goes through the normal rules.
A shift an admin reopens is no longer auto-closed. `POST /api/iot/auto-close/run` (admin) runs the sweep on demand.
The deadline is set to 11 hours after the payload arrives by default (`INSITEFUEL_IOT_SHIFT_AUTO_CLOSE_HOURS` can
change it). A later IoT window can close a superseded open IoT shift earlier. Auto-close still requires a valid,
nonnegative calculated closing fuel balance and any required transfer notes; it does not wait for a second payload.

## Setup

1. `alembic upgrade head`
2. Environment: `INSITEFUEL_IOT_API_KEY=<long random secret>` (also optional: `INSITEFUEL_IOT_SHIFT_AUTO_CLOSE_HOURS`,
   `INSITEFUEL_IOT_SERVICE_USERNAME`).
3. Map vessels and engines (admin token):
   - `PUT /api/iot/vessels/{vessel_id}/mapping`   `{"iot_vessel_id": "133719"}`
   - `PUT /api/iot/equipment/{equipment_id}/mapping`   `{"iot_engine_name": "Port"}` (one per engine name used by the vendor: Port, Starboard, Port DG, Starboard DG)
4. Create each vessel's **first shift manually** (initial-opening-fuel workflow). IoT only continues the chain from the
   next shift onwards; a vessel with no shift yet is rejected until one exists.

## Admin inbox

The **IoT Inbox** page is admin-only. It lists the real payload inbox with status filters and paging, shows raw
JSON plus validation errors and warnings, and lets an administrator map the external vessel ID and measured vendor
engine names to an existing vessel and its equipment. Mapping selections are stored on the existing vessel and
equipment records. Valid queued rows move from `AWAITING_MAPPING` to `READY` and are automatically applied in
reporting-window order as soon as the required mappings are saved. Later payloads with those mappings are validated
and processed automatically after receipt. `READY` is a brief staging status; opening or refreshing the inbox also
drains any rows left in READY. Processing stops at the first row that needs correction so later shifts cannot inherit
an incorrect balance.

`GET /api/iot/payloads?status=AWAITING_MAPPING`, `GET /api/iot/payloads/{id}` (raw JSON, errors, warnings, result),
`GET /api/iot/mapping-options` (admin; real active vessels and equipment), and
`POST /api/iot/payloads/process-ready` (admin) to drain queued valid rows in order. Use
`POST /api/iot/payloads/{id}/reprocess` (admin) after resolving another correctable cause.

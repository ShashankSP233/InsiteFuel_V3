# Sending IoT Data to InsiteFuel

Use this guide to submit vessel shift data to InsiteFuel V3.

## API endpoint

Send an HTTP `POST` request to:

```text
https://insitefuel.dhartidredging.com/api/iot/shift-data
```

This is the endpoint for the current local test server. The InsiteFuel page at `/ui/` is for people; the IoT
system sends data to `/api/iot/shift-data`. For production or access from another network, ask InsiteFuel for the
server address that the IoT system can reach.

## Authentication and headers

InsiteFuel will provide the API key separately. Send it in the `X-API-Key` header:

```http
Content-Type: application/json
X-API-Key: <API key provided by InsiteFuel>
```

Do not include the API key in the URL or JSON body.

## Request body

Send one JSON object per vessel reporting window. The endpoint also accepts an array of objects. Send windows in
date/time order, oldest first. Times without a timezone offset are interpreted as India Standard Time (IST).

```json
{
  "vesselId": "<external-vessel-id>",
  "vesselName": "<vessel-name>",
  "startTime": "2026-10-05 00:00",
  "endTime": "2026-10-05 11:59",
  "fuelStock": [
    {"engine": "Port", "rob": 993.920, "refill": 0, "drain": 0},
    {"engine": "Starboard", "rob": 1087.130, "refill": 0, "drain": 0},
    {"engine": "Port DG", "rob": 0, "refill": 0, "drain": 0},
    {"engine": "Starboard DG", "rob": 0, "refill": 0, "drain": 0}
  ],
  "engineRunDetails": [
    {
      "engine": "Port",
      "startTime": "01:00",
      "stopTime": "02:00",
      "durationInSeconds": 3600,
      "fuelConsumed": 17.300
    },
    {
      "engine": "Port DG",
      "startTime": "03:00",
      "stopTime": "03:30",
      "durationInSeconds": 1800,
      "fuelConsumed": "N/A"
    }
  ]
}
```

Use the actual external vessel ID mapped with InsiteFuel. Engine names are `Port`, `Starboard`, `Port DG`, and
`Starboard DG`; InsiteFuel maps these names to the vessel's equipment.

Each `engineRunDetails` item represents one engine run. `fuelConsumed` is the consumption for that run, in
**litres**. Use a number for measured consumption and `"N/A"` or `null` when the run has no measured consumption.
`startTime` and `stopTime` use `HH:MM`; `durationInSeconds` is optional. `fuelStock` values (`rob`, `refill`, and
`drain`) are in litres. For each vessel and JSON date, the earliest-starting report is MORNING and the next later-starting report is EVENING. The labels follow start-time order, with no noon cutoff. Send reports chronologically; only two reports per vessel per date are supported.

## Example command

Replace the API key and JSON file path with the values for your integration:

```bash
curl -X POST "https://insitefuel.dhartidredging.com/api/iot/shift-data" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API key provided by InsiteFuel>" \
  --data-binary @shift-data.json
```

## Response

Read the response body and check `results[].status`, `results[].errors`, and `results[].warnings`.

- `PROCESSED`: data was accepted and applied.
- `DUPLICATE`: the identical payload was already received and was not applied again.
- `AWAITING_MAPPING`: InsiteFuel saved the payload while an administrator completes vessel or engine mapping.
- `REJECTED`: the payload could not be applied; the response includes the reason.

HTTP `200` indicates successful processing, a duplicate, or a payload awaiting mapping. HTTP `422` means one or
more payloads were rejected. HTTP `401` indicates a missing or invalid API key; `503` means the endpoint is not
enabled on the server. If a request times out, retry the identical JSON so duplicate detection prevents repeated
fuel entries.

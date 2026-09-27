# Sungrow international OAuth V2

Official sources reviewed 2026-09-27:
- https://developer-api.isolarcloud.com.hk/#/quick-start
- https://developer-api.isolarcloud.com.hk/#/document/md?id=14083
- OAuth V2: Obtain token via authorization code; Refresh Token; Query Plant List; Query plant real-time measuring point data; Common Plant Measuring Points.

Secret Key is the x-access-key header. Appkey is the appkey JSON field.
Only https://gateway.isolarcloud.com.hk is accepted by this installation.
Authorization: https://web3.isolarcloud.com.hk/#/authorized-app with cloudId=2,
applicationId from configuration, redirectUrl set to the app callback.
Endpoints: POST /openapi/apiManage/token, /openapi/apiManage/refreshToken,
/openapi/platform/queryPowerStationList, /openapi/platform/getPowerStationRealTimeData.
No control endpoints, account passwords, or undocumented endpoint probes.
The documented plaintext JSON protocol travels over verified HTTPS; RSA application-level encryption is optional.

## Security

Sungrow's guide does not document state echo or PKCE. The callback therefore
requires a short-lived browser cookie, a stored single-use nonce and an explicit
owner-authenticated, same-origin confirmation POST before exchanging the code.
Opening a supplied authorization link directly will not work: start at Connect
Sungrow on the dashboard. Authorization codes and rotating refresh requests are
not retried automatically. Access and refresh tokens are encrypted in Postgres.
The token request uses documented authorization_bound scope mode.

## Readings and limits

Plant points: 83033 power (W), 83022 daily generation (Wh -> kWh), 83102 daily
purchased energy (Wh -> kWh), 83072 daily feed-in energy (Wh -> kWh), 83129 battery
SOC, 83238 storage active power (W). Unsupported, nonnumeric or absent readings
remain null. Battery power keeps the provider sign; no charging/discharging label
is inferred. Grid power direction is not established in the reviewed definitions,
so instantaneous import/export remain null; daily totals are available when reported.
Available-generation capability is not defined and remains null. Telemetry permission
and availability must be validated against the actual authorized installation.
Provider device_time is shown separately in plant-local time; database timestamp
records retrieval time. Existing daily summaries group samples in UTC, while the
provider daily counters reset on the plant's local day; use daily readings directly
until plant-local daily aggregation is implemented.
The API guide mixes legacy and OAuth examples; OAuth V2 header specification is
used (Authorization: Bearer token), not the legacy login/token-body example.
Sungrow polling uses at least 300 seconds independently from Nest polling.

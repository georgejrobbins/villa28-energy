# Google Home presence bridge

The Playground proof of concept passed both manually selected Home/Away transitions on 29 September 2026. Playground cannot send events to this app. This release implements a separate cloud-to-cloud virtual switch named **Villa28 Away Indicator**, served by Railway. It has no connection to physical device controls.

## Configuration

Google Home Developer Console project: `villa28-presence` (Villa28 Presence).
Railway variables:
- `HOME_PROJECT_ID=villa28-presence`
- `HOME_CLIENT_SECRET`: a new random secret, at least 32 characters, shared only with the Google Home integration's Client secret field. Do not reuse Nest/Sungrow credentials.

Google Home integration fields:
- Name: Villa28 Presence
- Device type: Switch
- Client ID: `villa28-google-home`
- Authorization URL: `https://villa28-energy-production.up.railway.app/home/oauth/authorize`
- Token URL: `https://villa28-energy-production.up.railway.app/home/oauth/token`
- Fulfillment URL: `https://villa28-energy-production.up.railway.app/home/fulfillment`
- Leave HTTP Basic client authentication unchecked (credentials in form body).
- Redirect allowlist is limited to Google's production/sandbox OAuth redirect hosts, exact project ID, no arbitrary redirect URLs.

Enable the test integration in Google's console and link it from Works with Google Home using the project owner's account. Sign in with the existing dashboard owner credentials on the Railway linking page. Assign the indicator to a room. Update the tested HomePresence script to use this indicator's exact name/room, with AWAY -> on:true and HOME -> on:false. Disable the Playground test once the replacement passes.

## Data and limits

`presence_events` retains timestamped received indicator updates; `presence_state` holds the latest value. Migration 005 starts UNKNOWN. No existing thermostat history is reclassified. `/api/presence?day=YYYY-MM-DD` returns Dubai-day segments and raw events. The dashboard aligns the day selector with AC activity and refreshes the last signal every 30 seconds.

OAuth codes expire after five minutes and are single-use; access tokens expire after one hour. Issued refresh tokens are stored only as SHA-256 hashes (stronger than reversible encryption for tokens we only validate), and are revoked when Google disconnects. Existing Nest/Sungrow tokens remain encrypted. Linking has cookie-bound consent, origin checks, exact redirect validation and a shared failed-login limit. Duplicate EXECUTE requests are replayed from a receipt without creating another event. A PostgreSQL row lock serializes deliveries across workers.

Only the virtual switch ID and the boolean OnOff command are accepted. SYNC exposes only this switch, never thermostats or solar devices. The switch starts off for Google's binary protocol, but the dashboard remains UNKNOWN until an actual command arrives. The last event is held across time, explicitly marked as last received, not continuously verified occupancy. Outages can miss events; no historical backfill or automatic repair is claimed.

Google EXECUTE does not identify whether the switch was changed by HomePresence, a user tapping it, or a voice command. Reserve it for the two presence automations. Manual Home/Away testing validates delivery; automatic occupancy detection needs a real departure/return test. Unlinking invalidates this single household's links and records UNKNOWN. Nest's manual Eco flag is shown separately and is never used to infer Home/Away.

Official references:
- https://developers.home.google.com/cloud-to-cloud/project/authorization
- https://developers.home.google.com/cloud-to-cloud/guides/switch
- https://developers.home.google.com/automations/schema/reference/entity/sht_structure/home_presence_state

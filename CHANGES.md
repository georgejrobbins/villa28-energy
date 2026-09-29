# Changes from the supplied monolithic source

This is the deployment revision. The original conversion ZIP remains a separate artifact.

- Removed unverified Sungrow endpoints; left explicit deferred routes and provider requirements.
- Corrected Google authorization to the documented Nest Partner Connections Manager flow and added browser-bound, expiring, single-use state.
- Added expiry-based token refresh and encrypted both access and refresh tokens.
- Corrected thermostat names and heat/cool setpoint mappings; store timestamps as datetime values.
- Started a Pub/Sub consumer with durable deduplication and partial-event merging; retained periodic polling.
- Added owner-only dashboard/data access, safe DOM rendering, missing-value handling and canvas history graphs.
- Added tracked, transactional migrations and indexes safe on repeated startup.
- Corrected health-check HTTP status, multi-installation daily summaries, session cleanup and worker shutdown.
- Removed the duplicate root handler, permissive CORS, placeholder deployment workflow and obsolete dependency imports.
- Updated and pinned directly used dependencies to the versions tested for this release. Added tests and GitHub CI.
- Preserved read-only operation. No device control commands or invented provider endpoints were added.

## Google Home presence bridge

- Added OAuth account linking and a single virtual Away indicator. No physical controls are exposed.
- Persisted received Home/Away events, deduplicated Google deliveries, and added a dashboard day timeline.
- Corrected manual Eco labels: automatic Eco cannot be inferred from SDM OFF. Existing readings are unchanged.
- Requires separate Google Home project/linking and Railway HOME_PROJECT_ID/HOME_CLIENT_SECRET variables.

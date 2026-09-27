# Historical monitoring

Every successful poll appends readings to PostgreSQL. POLLING_INTERVAL_SECONDS defaults to 300; Sungrow has a 300-second minimum. No retention deletion or daily replacement is configured. Collection needs a running service and working provider API; outages are gaps. Historical readings before connection are not backfilled.

The dashboard offers 7- and 30-day views plus raw CSV exports (30 days from the UI, 1–90 days via the protected export endpoint). A normal week contains about 2,016 readings per thermostat and installation. Nest source and timestamps are retained; event records can add readings between polls.

Eco is labelled Away from property as a user-selected proxy, not measured presence. HVAC OFF is labelled Idle, which does not establish whether a room is in use. User-supplied room-use schedules are separate. Nest does not expose cooling stages or saved schedules.

Solar interval energy is calculated from consecutive daily counters. Duplicate provider times, counter resets and long gaps are not treated as zero consumption. Provider timestamps use this installation’s Dubai timezone. Raw CSV retains both collection and provider timestamps. Grid interval values are energy (kWh), not instantaneous power.

After a week, compare cooling runtime and targets with supplied schedules, temperatures, Eco periods and solar/import/export intervals. Runtime does not directly measure room-level electricity. Weather, room use and comfort requirements should inform any proposed schedule changes; this app remains read-only.

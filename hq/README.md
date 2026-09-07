# Personal office viewer

A plain HTML/SVG office at `/hq/` alongside the existing trading homepage. No application installation, external scripts, paid service, or game changes.

Tap a desk to inspect a team's task. Mobile bottom sheets, keyboard access, pan/zoom, and lighting controls are implemented in the page. Avatar animation is decoration, not execution evidence.

## Data and privacy

`status.enc.json` contains an AES-256-GCM encrypted snapshot. Its 256-bit random key is provided separately in the private viewing link fragment (`#k=...`), never in this repository. Possession of the complete link grants access: this is not account-based authentication. Do not commit keys, plaintext snapshots, personal tokens, or raw worker logs. Do not replace the envelope with plaintext.

The page retrieves the latest **published snapshot**, not live runner telemetry. GitHub claim label intervals are distinct from active work time; without a verified worker heartbeat, execution and Studio ownership remain unconfirmed. Missing times are not fabricated. Snapshot timers stop at the recorded observation or end time.

The site does not submit work, merge branches, control Studio, or publish Roblox. This change does not install an automatic snapshot publisher.

## Deployment

`HQ Office Pages` verifies changed HQ files on pull requests and deploys on main changes. The original trading homepage is copied unchanged. Both existing scheduled Pages workflows also copy `/hq/`, so later scheduled trading deployments retain the office.

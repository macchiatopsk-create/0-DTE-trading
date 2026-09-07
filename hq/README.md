# Last Wall HQ — reference office edition

The owner requested the office artwork in their uploaded `last-wall-hq-office-3.html`, not another flat plan or a simplified WebGL scene. This version uses that supplied office scene with real interactive HTML controls and the existing private snapshot reader at the same `/hq/` URL.

## Appearance and interactions

`office-art.avif` is the central office crop of the supplied artwork: original 1672x941; crop (143,179)-(1255,774), resulting in 1112x595. It retains the warm lighting, glass offices, desks, characters, monitors and lounge. It is artwork, not real-time video or a 3D engine.

The original picture's top KPI/date bar and right detail panel are excluded. Persistent opaque HTML overlays cover baked example names/status/task IDs/timers in the desk areas. Real counters and details are outside the bitmap. The image and room hit regions share one 1112x595 coordinate space during pan and zoom; no object-fit cover mismatch. Eight room buttons, one-finger pan, two-finger pinch, zoom/fit/light controls, team shortcuts, detail tabs, issue/PR links and mobile bottom sheets are implemented.

Phones start at a readable office zoom. Drag to other rooms, use the team rail, or choose `전체` to fit the entire office. Desktop retains a right detail panel. Missing artwork produces an explicit message while team navigation stays available.

## Data and privacy

The existing `status.enc.json` is unchanged. The AES-256-GCM viewing key is delivered separately in the private link fragment, never committed in this public repository. Anyone with the full private link can view the snapshot; this is not account-based authentication. Do not share that link or commit plaintext private tasks, tokens or raw worker logs.

This is a published GitHub **snapshot**, not live runner telemetry. Claim intervals stop at their recorded end or observation time, not the current wall clock. Claims do not imply a worker is executing. Actual execution time, heartbeat and Studio ownership remain unconfirmed. No fabricated percentages or example task values are used as current data. Refresh checks for a newer published envelope; automatic snapshot collection is not installed.

Schema validation and AES integrity checks precede rendering, task text is escaped, issue/PR links use validated positive numeric identifiers, and removing a key invalidates in-flight requests and clears private state. No token entry, localStorage, sessionStorage, cookies, external code or tracking.

## Validation performed

`node hq/test-office.cjs`: 52/52 core assertions passed locally, including real generated-key AES-GCM roundtrip, wrong-key/tamper rejection, timing semantics, schema safety, image SHA-256 and room coordinate bounds. The core tests run in CI.

Offline Chromium DOM/interaction checks: 90/90 passed at 1440x900, 390x844, 360x740 and 705x338, with generated non-production fixtures injected through the production schema/render functions. The provided AVIF actually decoded. Room clicks, pan/pinch, tabs, mobile sheet, zoom, light, keyboard, image-failure handling, source-data escaping and no horizontal viewport overflow were checked. Actual screenshots were visually inspected against the reference. Browser tests were offline and did not test native network fetching/decryption or a physical phone; cryptographic execution was separately tested in Node. No owner viewing key or production plaintext was used in browser fixtures.

## Deployment boundaries

The HQ Pages workflow and the two existing trading Pages workflows all copy `index.html`, `status.enc.json` and `office-art.avif` into `/hq/`. Outside HQ, the only scheduled-workflow edits add the asset to the existing copy operation, so future trading deployments retain the background. Root trading HTML, financial scripts/config/data/schedules, LastWall game and runners are untouched. The page cannot start/stop workers, merge code, modify Studio or publish Roblox.

# Last Wall HQ — personal 3D office

The owner's existing `/hq/` webpage now renders an actual, authored WebGL2 office. It is not a background photograph, a screenshot with hotspots, or a dashboard-card grid.

## Interaction and rendering

Eight selectable staff workspaces contain volumetric walls, glass partitions, wooden desks, multi-monitor workstations, swivel chairs, characters, plants and lamps. The desktop layout adds a lounge and meeting area; portrait phones use a two-column arrangement of the same team. Tap a desk, character, nameplate or team shortcut to open the detail panel. Mobile uses a bottom sheet. Pan, pinch/wheel zoom, viewpoint change, lighting, reset and detail tabs operate on the actual scene.

The self-contained HTML has no external scripts, libraries, fonts, tracking or image assets. Texture atlas content is authored with Canvas2D. WebGL2 renders geometry, light and shadows. Reduced-motion and hidden-page pauses are respected. Unsupported or lost WebGL contexts show an explicit message with usable task-detail navigation; the page does not pretend that 3D loaded.

This is a stylized, low-poly real-time implementation, not pixel-identical photorealism from the original concept image. Character motion and desk lights are cosmetic, never proof of worker execution.

## Private data and timing

The existing `status.enc.json` and existing viewing key are unchanged by this visual update. It contains an AES-256-GCM encrypted **snapshot**. The key is delivered separately in the private viewing link fragment (`#k=...`), not committed here. Possession of the full link grants access; this is not account authentication. Never commit the key, plaintext task snapshots, GitHub tokens, or raw private worker logs.

Claim labels mean only that a task was claimed. Claim intervals end at the recorded release/review time or snapshot observation, not at an invented live timer. Missing work start, actual execution time, heartbeat, model and Studio ownership remain unconfirmed. The periodic same-origin read checks for a newly published snapshot; **automatic GitHub/runner collection is not installed**.

AES-GCM integrity and snapshot field validation precede rendering. Task text is escaped, links are constrained to numeric issue/PR identifiers, and key removal cancels/invalidates older requests. No localStorage, sessionStorage, cookies, external requests or tokens are required.

## Tests

Run `node hq/test-office.cjs` (Node 22 in CI). There are 45 core assertions covering status/timing truth, schema, escaped content, real AES-GCM roundtrip and wrong-key/tamper rejection using generated test keys, finite bounded geometry, matrix inverse, and security/unsupported-rendering contracts.

Additional local verification used Chromium 144 under Xvfb with SwiftShader WebGL2 and offline generated test fixtures at 390x844, 360x740, 705x338 and 1440x900. All 56 interaction checks passed, including real desk picking, nameplates, sheets/tabs, zoom, lighting, safe text, no horizontal document overflow, and explicit unsupported-WebGL fallback. These are browser-emulated viewports, not physical phone or production-network tests.

## Deployment boundaries

`HQ Office Pages` validates the HTML/encrypted envelope and runs the core tests before deployment. It copies only the office HTML and encrypted snapshot into `/hq/`. Existing scheduled trading deployments already retain those files. Root trading HTML, financial code, financial schedules, LastWall gameplay, Studio and runners are untouched. The page is read-only and cannot publish Roblox, merge code, start jobs or stop workers.

# HQ v8 — separate office and five-seat boardroom

The existing /hq/ page now has two actual spaces under its existing top tabs. The office retains owner, lead, Codex, Claude, Opus and Studio/Fable workstations. The separate long-table boardroom has exactly five symbolic avatar seats: owner, lead, Codex, Fable and Astra. No likeness of the owner or any real person is used.

## Visual and interaction changes

- Big office info cards are removed. Compact name plaques sit over the clickable symbolic avatars; all task details appear only after tapping.
- Both spaces stay portrait-first. No bottom dashboard, orientation hack, new repository or separate installer.
- The existing office illustration's baked blank status-card patches were repaired with nearby scene textures. A crop of the empty architectural wall from the owner's supplied meeting mockup is combined into the same lightweight local AVIF sprite. The five-seat long table, laptops and avatars are authored CSS/SVG components, not a photograph of a live meeting or a photorealistic scene.
- Native task dialogs show role, current task, recorded state, actual work time availability, recorded claim interval, progress availability, summary and issue/PR links. Astra has its own explicit unconnected/review-role entry; adding a seat does not launch a model.
- Meeting records are collapsed by default, then expose Agenda / Decisions / Records. No input, send action, simulated agent response or online indicator.

## Data truth and privacy

status.enc.json is byte-for-byte unchanged from v7. The private fragment key and existing /hq/ address are retained. No tokens, plaintext private task records or owner viewing key are committed.

Claim intervals are frozen at recorded end/observation and are not execution hours. Progress requires an explicit sourced percent or a sourced completed/total checklist. Missing progress displays unrecorded; raw demo percentages and review/running labels do not generate fake progress. Checklist-derived percentages are labelled as such. Actual runtime, heartbeat, Studio ownership and independent Astra invocation remain unconfirmed.

The encrypted meeting records are still read-only. Fable, Astra and Codex messages require the agent-evidence record kind; missing speech stays explicitly absent. This schema validates provenance fields, not real-world truth by itself. There is no continuous ChatGPT session, model API, runner command channel or automatic snapshot publisher behind these seats.

## Actual tests on uploaded source

- Node 22: 72/72 core assertions passed, including actual generated-key AES-GCM roundtrip and wrong-key/tamper rejection, task/meeting schemas, sourced progress and unknown values, fixed five-role membership, source escaping and asset hash.
- Offline Chromium: 438 DOM/interaction checks passed across 320x640, 360x740, 390x844, 430x932, 768x1024 and 1280x900. All office and boardroom actions, >=44px hit regions, compact name labels, fully in-bounds meeting seats, native dialog close/Escape, tabs, generated checklist rendering, private-state clearing and no horizontal overflow were exercised. Screenshots were visually reviewed.
- Browser checks used set_content, a data-URI copy of the exact production AVIF with test-only CSP allowance, and generated fixtures through the production validator. File/HTTP browser navigation is restricted in this environment. These are not physical-phone, Safari, production-network or native fetch/decryption acceptance. Crypto execution was separately verified in Node.
- Tested and uploaded blobs: HTML b8a4855e73384ec9fbb3057ea8b24364d1593a7b; artwork 90bd7713963205d332738e1157b7298dbfbcb9b3. Unchanged encrypted snapshot 6a047e2d43157c946bea30d463d4cd28393ce894.

The Pages workflow executes core tests before deployment. Existing scheduled trading workflows already copy these same three HQ filenames and need no changes. Trading source/homepage/schedules, LastWall gameplay, runner queues and Studio are untouched. Deployment success is verified separately from local tests.

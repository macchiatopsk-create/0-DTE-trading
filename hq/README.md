# HQ v7 — portrait office and phase-one meeting records

Owner requested a readable portrait-only office, a central owner station overlooking the team, no separate bottom dashboard/navigation, and a first-phase meeting space. The existing /hq/ URL and private viewing key still work.

## Implemented

- Phone-width portrait office with seven staff/owner stations and a clickable central meeting table. The owner's empty executive chair faces the team workspace; it is not a likeness of the owner.
- The warm office artwork was newly generated for the approved portrait direction, cropped to the office only and rescaled for the tall scene. Generated example status/name panels were physically blanked in the image before encoding; actual visible labels are HTML controls. It is illustration, not live video or real-time 3D.
- No KPI ribbon, bottom dashboard sections, team rail, pan/zoom toolbar, or forced landscape mode. Old wide=1 links are normalized without removing the private fragment.
- Top office/meeting tabs, normal vertical scrolling, room buttons, native modal task details and accessible keyboard tab controls. The scene fills the portrait width; there is no fixed-width landscape canvas.
- The read-only meeting room has three role badges (owner, lead, Fable) and Agenda / Decisions / Records views. No input box, sending, simulated AI reply, online indicator or worker invocation.

## Sources and privacy

The encrypted snapshot now also contains one meeting record from the owner's requests and approval in this conversation, with an explicitly labelled implementation note. Owner text is marked as paraphrase or original quote. No Fable speech was invented. This is not a real multi-agent chat transcript.

The original task values and task observedAt were preserved at the data level when adding meetings. Re-encryption uses a fresh AES-GCM nonce and the existing key. Do not mistake the new deployment/envelope date for a fresh GitHub observation. Old task snapshots are visibly labelled as past snapshots. Actual execution time, heartbeat and Studio ownership remain unknown.

The viewing key is not in this repository. Whoever has the full private-fragment link can read the data; this is not account authentication. Do not commit keys, plaintext project records, private screenshots or raw worker logs. Source text is escaped, numeric GitHub links are constrained, meeting payloads are bounded/validated, and fragment removal cancels old requests and clears private DOM state. There is no localStorage, sessionStorage, cookie or external API requirement.

Refresh reads a newer published encrypted snapshot only. Automatic data collection, cross-device message writing, model responses and runner commands are NOT installed.

## Actual validation

- Node 22 core tests: 58/58 PASS locally. Real generated-key AES-GCM roundtrip, wrong-key/tamper rejection, old snapshot compatibility, time semantics, meeting provenance/schema checks, safe text and image hash.
- Offline Chromium DOM/interaction tests: 288/288 checks PASS over 320x640, 360x740, 390x844, 430x932, 768x1024 and 1280x900. All eight spatial actions, target sizes >=44 CSS px, native dialog close/Escape, meeting tabs, lack of fake composer/Fable speech, keyboard navigation, XSS escaping, image-error fallback, private-state clearing and no horizontal overflow were exercised. Actual screenshots were inspected.
- Browser tests used set_content, a data-URI copy of the exact encoded artwork with a test-only CSP allowance, and generated fixtures through the production validator. Browser navigation to the local HTTP server was denied by this environment. Therefore these are offline interaction checks, NOT production-network, native browser fetch/decrypt, physical-phone or Safari acceptance.
- Original-versus-updated decrypted task objects were compared locally and equal; only meetings were added. The production envelope was authenticated/decrypted locally for verification without publishing the key or plaintext.
- Tested HTML blob: d72d31c77166320eec14db79eacac09dc0c93f26. Art blob: 3a61d72281f2c82750cda59880c19c02b0335913. Encrypted envelope blob: 6a047e2d43157c946bea30d463d4cd28393ce894.

CI executes the core checks before Pages deployment. Deploy success is verified separately; local screenshots are not evidence of a successful cloud deployment.

## Boundaries

Only HQ assets, schema/records UI, tests, documentation and the HQ Pages verification step are changed. The two existing scheduled trading workflows already copy the same filenames, so no financial workflow/code/data changes are needed. LastWall gameplay, runner queues, Studio and Roblox publishing are untouched.

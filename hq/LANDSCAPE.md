# Phone landscape update (v6)

The same `/hq/` office now starts fitted to the available viewport instead of opening pre-zoomed and clipped on a portrait phone. The existing artwork and encrypted task snapshot are unchanged.

Use the header's `가로 보기` button, or add `wide=1` to the URL query while retaining the original private fragment. In a portrait viewport this rotates the complete page 90 degrees and swaps its logical width/height. Hold the phone sideways. In a naturally landscape viewport it uses the wide layout without a second rotation. `기본 보기` restores the normal layout. This is page rotation, NOT an operating-system orientation lock or browser fullscreen request.

Wide layout removes the summary bar and bottom strips, reserves a narrow control rail, and fits the complete office. Staff details are an on-demand right overlay, not a permanently open sidebar. All gestures use inverse-rotated viewport coordinates; room hit targets, pan, pinch, zoom, modal focus/close and resize remain aligned. The private URL fragment is preserved when toggling the query. No key is stored, logged or committed. Existing read-only snapshot and unknown execution/heartbeat semantics remain unchanged.

## Validation in this change

- The reconstructed base HTML was byte-verified against live blob `92527ca85eea4686643e6fdb66900a2980768fed` before patching.
- New `node hq/test-landscape.cjs`: 37/37 local assertions passed (logical sizing, rotation, pointer mapping and integration contracts). The existing 52-assertion core test is retained unchanged and both commands run in CI.
- Local offline Chromium: 232 DOM/interaction checks passed over 390x844 normal/wide, 360x740 wide, 338x705 wide, 705x338 auto, 844x390 wide, 1024x768 and 1440x900. Each exercised all eight room targets, accessible close controls, details/tabs, fit, zoom and toggle.
- Eleven additional offline checks passed for actual pointer drag and two-touch pinch under rotation, natural orientation changes without double rotation, preserved selected team/data, detail close after resize and keyboard toggle. Screenshots were inspected.
- Browser tests used `set_content`, an inline re-encoding of the identical supplied artwork crop, generated non-production data via the production validator, and blocked all external requests. Local HTTP navigation was unavailable in this environment. These tests do not assert production reachability, native browser snapshot decryption or physical-phone acceptance.

Only the HQ HTML, this note, the new layout test and an additive CI test command are changed. No artwork/encrypted snapshot/trading source or schedules/LastWall game/runner/Studio changes.

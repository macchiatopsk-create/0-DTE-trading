# HQ live transport v9 — deployed relay; local activation still gated

The approved v8 office and five-seat boardroom source, art, encrypted fallback and original 72 tests remain unchanged. `python hq/build.py _site` adds live.js to the deployed page and grants script-self plus the exact relay origin in CSP. All three existing Pages workflows use this HQ build so later trading deployments retain the extension.

## What is implemented

- Actual encrypted request/response transport, a meeting chat dialog with four selectable responders, idempotent send IDs, cancellation, bounded history and safe text rendering. This is not a demo responder.
- Browser polls the authenticated relay every 10 seconds while visible. Local bridge is designed to collect the latest 35 GitHub issue/PR-list entries (PRs excluded from the issue display) and allowlisted V3 state files every 30 seconds. This is a bounded recent feed, not the whole repository or full PR reviews.
- Separate server connectivity, local bridge lease/heartbeat, development process PID/start-time evidence, and selected model verification. No fresh heartbeat or verified model capability means sending stays disabled. Claims, checklist completion and measured process intervals are not CPU work time or overall game completion.
- A local Node bridge candidate with fixed CLI arguments, no shell interpolation, no MCP/built-in tools, no inherited API-billing variables, read-only Codex sandbox, bounded outputs/timeouts and single responder at a time. Exact model IDs and native executable versions require local validation; no silent Fable/Astra substitutions.
- Replies use separate subscription-authenticated local CLI sessions. They do not move the current ChatGPT session into the website. Recent messages and a bounded status snapshot provide context. This chat cannot intentionally edit files, publish Roblox, merge PRs or control Studio/runners. Existing subscription limits still apply.

## Activation status and remaining blocker

The Supabase `hq-relay` Edge Function was deployed ACTIVE with explicit custom bearer authentication, not an open unauthenticated endpoint. Isolated tables hq9_rooms/hq9_jobs have RLS and no public/anon/authenticated table grants; only the scoped service RPC is used. Existing unrelated application tables remain untouched.

The Windows pairing preflight in LastWall issue #212 stopped before worker execution with git HTTPS `Recv failure: Connection was reset`. A single requeue also returned BLOCKED. No public pairing key/report has been received. **No local bridge process or real model reply has been validated. This release must not be described as end-to-end live chat complete.** The relay can be online while all responders remain disabled.

After that network blocker is resolved, the local integration owner must finish #212, seal the bootstrap with its RSA-OAEP-SHA256 public key, and install the protected configuration under `%LOCALAPPDATA%\\LastWallHQ`, outside all repositories and worker worktrees. Do not put the private viewing key or worker token into an issue, PR, Git file, command line or log. Do not substitute a public encrypted file decryptable by the client for the independent worker credential.

A separate local acceptance is required before setting any `models.<target>.enabled=true`: confirm the actual CLI supports every supplied isolation flag; verify subscription login without extracting it; run a bounded text-only canary and prove tools/MCP/file writes are unavailable; record exact model ID, executable, verifiedAt and noToolsVerified. Keep unsupported models disabled. Do not disable isolation flags to make a canary pass. No autostart/runner migration is installed here. Node bridge expects native `.exe` files on Windows and fails closed on `.cmd` shims.

## Private configuration contract (not included)

Config fields: endpoint, room, key, workerToken, scratch, gh, states:[{lane,path}], models:{chief,codex,fable,astra}, pauseChatWhileCoding. Each enabled model requires provider codex/claude, native absolute executable, exact model, verifiedAt, noToolsVerified=true. All models default to disabled. Endpoint and room are fixed in bridge source. Protect the whole directory and config with current-user-only Windows ACLs. Scratch must be outside game/repos/credentials. The bridge does not modify global CLI config or existing runner processes. Its normal stop/timeout kills only its own subprocess tree; hard parent termination still needs empirical Windows acceptance (no claim of a fully audited Windows Job-object supervisor).

## Protocol and security

Client token is a domain-separated SHA256 derivation of the existing private-fragment key; only its SHA256 hash is stored in the relay. Worker token is independently random and independently hashed. The key is never sent to the relay. Message contents and snapshots are AES-256-GCM ciphertext; per-message authenticated data binds room, UUID, target and request/response direction. Link possession still grants client access; this is not account login. Metadata (target, timestamps, state) is visible to the relay operator.

Custom Edge authentication is backed by public.hq9_gateway, SECURITY INVOKER, empty search_path, execute revoked from public/anon/authenticated. Role whitelists, room-scoped row locks, idempotency, exclusive bridge leases and job leases prevent cross-role actions and duplicate claims. Lost job leases are terminal rather than rerunning a possibly-consumed model request. Bounds: 6 sends/minute, 100/day, 4 outstanding, 1000 stored jobs; 15-minute queue expiry, 10-minute absolute job ceiling. No automatic deletion of user messages or paid fallback.

Applied migration names: hq9_isolated_encrypted_relay; hq9_bound_payload_without_postgres_repeat_limit. The second corrects PostgreSQL regex repetition limits by combining base64url checks with explicit length checks. Retrieve exact applied SQL from project migrations before future DB changes; do not replace tables or modify unrelated policies.

## Validation actually performed

- Node: 32/32 live-core checks passed. Actual generated-key browser-WebCrypto/Node-AES interoperability, wrong key/target/direction/job and tamper rejection; CLI contracts, real response parsing, read-only collection semantics, Edge origin/auth/role checks with a mocked transport.
- Actual deployed database transaction, rolled back: bad auth, role isolation, 1000-byte envelope enqueue, duplicate send, conflicting id, atomic claim, exclusive bridge, start, read, complete and duplicate completion. RLS and no anon/authenticated read grants verified. No synthetic jobs left in the owner room.
- Offline Chromium DOM: 51 checks passed at 320x740, 390x844, 768x1024. Existing seats, dialog, offline/stale/unsupported send gates, explicit errors, safe message text, old detail UI and key-removal clearing. Test state only; not real model output.
- Browser navigation and external HTTP are blocked by this execution environment, so there is no native production HTTP/WebCrypto or physical-phone end-to-end acceptance claim. CI and Pages deployment must be checked separately.

No model API key provisioned, provider billing changed, live model invoked, game source modified or Studio touched. Public repository contains only code, endpoint identifiers and documentation, never active credentials or private plaintext.

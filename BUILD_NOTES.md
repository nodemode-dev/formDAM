# DAM build notes

## zip v1.21.2 (2026-09-18) · app reports v1.13.9

Round 69: the fix for "The DAM engine failed to start". The owner ran the bundled engine in Terminal & it showed the cause: init_db died w/ sqlite3.OperationalError: no such column: live_of. The catalog setup script created the Live Photos index before migration 4 adds the live_of column, so every catalog older than Live Photos crashed the engine before it could announce its port. The owner's catalog is that old because their installed DAMp predated Live Photos (their later builds had been failing on the Rust error fixed in v1.17.0), so the fixed build was the first to meet it; my round-68 replays had used a library created by v1.16.0, already current, which is why they did not reproduce it. Fixed in backend/app/db.py: the index is created only by its migration, after the column exists, & a catalog w/o a version row now starts at version 1 so every migration runs (it used to be stamped current w/o migrating). Verified here: a real library made by the owner's original v1.16.0 engine (photos, a screenshot, vault passkey, hidden & deleted items, one past the 30-day window) downgraded to schemas 3, 2, 1 & no version row; the old code reproduces the owner's exact error on schema 3; the fixed code migrates all four to schema 4 w/ every column, the index & all rows; the engine from source & freshly frozen starts on a schema-3 library in the old DAMp folder, adopts it as DAM/library/dam.db & prints its URL w/ 0 errors, & engine.log records the start. Also: the face-model download in setup/build_macos_app & backend/oc_install retries transient network & DNS failures (the owner's rebuild hit Could not resolve host: media.githubusercontent.com), removes a partial file & says what to do; verified models are never re-downloaded. ruff clean; pytest 38 passed, 1 failing by design (test_trash, unchanged). Nothing in the owner's library was lost: the failed launches only renamed Application Support/DAMp to DAM & damp.db to dam.db, which is where the fixed engine expects them; do not open the old DAMp.app, which would start an empty library.

## zip v1.21.1 (2026-09-18) · app reports v1.13.9

Round 68: the desktop app shows "The DAM engine failed to start". What that dialog means: the shell spawns Resources/dam-backend/dam-backend & waits, w/o a timeout, for the engine to print http://127.0.0.1:<port>; the dialog appears only when the engine's output streams close first, i.e. the engine process exited during startup, & the shell discards whatever it printed. Replays here, none of which reproduced it: the owner's original v1.16.0 engine built a real legacy DAMp library (photos & a screenshot, vault passkey, 2 hidden, 2 deleted w/ one past the 30-day window, a private album w/ its own passkey), then the new engine started through desktop_entry exactly as the shell starts it (DAM_PORT=0) & adopted the DAMp folder & damp.db, sealed the protected items & purged the expired one; the same from a PyInstaller-frozen engine built w/ the Mac build's flags; the same w/ the packages an unpinned Mac build installs today (FastAPI 0.141.1, Starlette 1.6.0, uvicorn 0.53.0, NumPy 2.5.3, OpenCV 5.0, OCR stack); the Mac worker-thread server path; the old DAMp engine still running on the same library. Every one printed its URL. The build & signing scripts differ from v1.16.0 only in names. What remains is Mac-native & unobservable here (the PyObjC iPhone bridge on the main thread, privacy & code-signing enforcement for the new bundle id, dyld). Shipped: (1) frozen engines now write all output plus a start marker per launch to ~/Library/Logs/DAM/engine.log, & faulthandler dumps native crash stacks there; verified in a frozen build that a normal start still reaches the shell's pipes & that a startup exception lands in the log w/ its full traceback. (2) requirements_macos.txt now carries requirements.txt's pins for every shared package, so a rebuild cannot silently jump majors; the set resolves w/o conflict. Tests: ruff clean; pytest 38 passed, 1 failing by design (test_trash, unchanged; the previously skipped test now runs & passes in this environment). Needed from the owner: the output of the bundled engine run in Terminal (DAM_PORT=0 "/Applications/DAM.app/Contents/Resources/dam-backend/dam-backend"), or engine.log after rebuilding.

## zip v1.21.0 (2026-09-18) · app reports v1.13.9

Round 67, three asks: the npm vulnerabilities, the banner wired in, & the setup layout of formcut w/ a master shebang. (1) npm audit had 3 findings, all dev tooling that never ships: vitest & its bundled @vitest/mocker 4.1.10 (moderate, GHSA-82fw-gwwq-j7x9, path traversal through mock redirects) & nanoid 3.3.16 pulled in by vite's PostCSS (high, GHSA-2v37-7h3g-55p8, infinite loop w/ zero-size custom generators). The vitest floor was raised by hand to ^4.1.11 & npm regenerated the lockfile: vitest & mocker 4.1.11, nanoid 3.3.19, while vite 8.1.5, typescript 5.9.3, jsdom 29.1.1 & postcss 8.5.23 did not move; npm audit now finds 0. npm 10.9.7 crashed on the version change (Cannot read properties of null, reading edgesOut: an npm resolver bug), npm 11.19.1 resolved it, & npm 10.9.7 then installs the new lockfile from scratch cleanly w/ 0 vulnerabilities. Licenses unchanged (MIT). (2) Layout as in formcut: the root holds only the master shebang ./DAM (banner, idempotent install, boot of the local browser build; it only sequences setup/) & its Windows twin DAM.bat; setup/ holds DAM_banner & a new DAM_banner.bat, DAM_oc_install(.bat), DAM_boot(.bat), build_macos_app, package_dmg & apply_icon, each resolving the repo root itself. Moved: DAM to setup/DAM_boot, DAM.bat to setup/DAM_boot.bat, both installers, dam_banner to setup/DAM_banner, the three build scripts. The boot passes backend/.env through as environment, opens http://127.0.0.1:5173 once it answers (DAM_OPEN=0 skips that) & stops both halves on Ctrl+C; the Windows installer now reuses an existing venv, skips models already present & stops the launch on failure. (3) Wired: ./DAM paints the banner first, & a banner failure can never block the launch. Found by the end-to-end run: backend/requirements.txt (Linux & Windows) lacked python-multipart, so the engine could not start there at all (macOS installs from requirements_macos.txt, which has it); added. rapidocr-onnxruntime is still macOS-only, so OCR elsewhere keeps its tesseract fallback. Verified here: shellcheck clean on every bash script, bash -n & sh -n; DAM_banner.bat identical to its generated form; a fresh ./DAM (banner, new venv, pip, checksum-verified face models, npm, boot); install re-run in 3 s w/ nothing re-fetched; ./DAM ready in 6 s w/ UI 200, proxied API 200 & engine 200; in a real pty the banner paints in colour & typing Ctrl+C stops launcher, engine & dev server w/ 0 processes left; SIGTERM clears strays; frontend tsc clean, 10 vitest, build clean. Not verified: the .bat files (no Windows here), the new layout on your Mac, the browser auto-open (no browser here). Deferred to next turn: FEEDBACK_CHECKLIST round 67 & the per-side HASHOUT lines; the sidecar root log carries the full entry.

## zip v1.20.0 (2026-09-18) · app reports v1.13.9

Round 66, terminal banner of the DAM icon. New root script `dam_banner`, in the same shape as the owner's formcut_banner & nodemode_banner (self-contained bash + printf, NO_COLOR, DAM_BANNER=0, DAM_BANNER_COLOR, DAM_BANNER_CLEAR, DAM_VERSION, centred art, dim rule, subtitle w/ the version from frontend/package.json), but the art is the icon itself, not the word: the rounded play-triangle plate as a dim outline, the m mark w/ both arch openings & the arm flowing into the tip, & the ball under the first stem, painted per character in the icon's own diagonal gradient (#FFE758 yellow at the arm's top edge to #FF292C red on the ball; 256-colour & 8-colour fallbacks, one RGB via DAM_BANNER_COLOR). Three sizes, 40x22, 28x15 & 20x12, chosen by terminal width & height; under 20 columns it prints the bare name, as the reference banners do. The art was traced from frontend/public/DAM-icon.png (glyph shapes matched per cell, figlet-style 8/d/b/Y/P for the mark), then hand-finished for a clean outline, a rounded tip & the gap between stem & ball. Verified here: bash -n & shellcheck clean; each art block byte-identical to the previewed art; every size & fallback path; truecolor spans all 8 gradient steps at 40 & 28 columns, 256-colour uses 196 to 226, 8-colour 31/33; NO_COLOR, non-terminal output & DAM_BANNER=0 print no colour; every painted line closes its colour; 18 ms per run; the captured terminal output rendered & inspected. Not wired into ./DAM or ./DAM_oc_install (the request was the banner); that is a two-line change when wanted. Bash 3.2 syntax only; running it under macOS's own /bin/bash is a Mac check.

## zip v1.19.0 (2026-09-18) · app reports v1.13.9

Round 65, liquid glass parity w/ nodemode_dev v8.70.6 (DEV_PLAN phase 4). Reference studied: nodemode_dev's liquid-glass Create UI (frontend/src/styles/simplicity-overlay.css) & its app glass (frontend/src/styles/nodes.css). DAM's glass.css already had the identical three-layer primitive, so parity is values: at the default slider positions the glass is now NodeMode's (36px blur, 190% saturation, 1.08 brightness, 0.38 smoke fill, 1px rim from 0.32 at the top to a faint white 0.02 at the bottom, 0.075 specular sheen, NodeMode's shadow stack w/ its inner top highlight & bottom depth). Changed: theme.ts defaults & slider mapping (brightness 0.9 + frost * 0.095; rim & sheen coefficients; the bottom rim is white instead of accent-tinted), a glass recipe version so saved glass sliders from the old recipe reset once (accent, background, window, panel & top-bar settings are untouched; later tuning persists), tokens.css first-paint values equal to the runtime ones, the Standard preset equal to the new defaults, & popovers on the glass saturation, brightness & shadow. Kept: DAM's amber-tinted smoke (the tint slider at 0 is close to NodeMode's neutral), the 9px panel radius, the side-panel & top-bar sliders. Not ported: NodeMode's lens distortion (needs backdrop-filter url(), which WebKit does not render) & the bar ring + top glow (a ring along the window edge is the artifact class of rounds 22 to 58). Verified here: tsc clean, 10 vitest, build clean; headless Chromium at 4x CPU & a slow network, seeded w/ an old-recipe saved pref: first paint already 36px, live tokens exactly NodeMode's values, cumulative layout shift 0, no console errors, a screenshot of the library view rendered cleanly. DOM: token & CSS values only, verified under throttling. Mac check: the glass over your real desktop (the headless run has nothing behind the window), & whether you want the old look back (every replaced value is in frontend/HASHOUT_LOG.md). FEEDBACK_CHECKLIST now carries rounds 61 to 65.

## zip v1.18.2 (2026-09-18) · app reports v1.13.9

Round 64, rename DAMp to DAM, part 3 of 3 (copy, ids, docs): the rename is complete. Renamed: Settings copy (Keychain status, menu bar toggle & hint), People banner (installer name), Collections shared-albums copy, Search hint, iPhone-engine & folder-picker messages (macOS, Windows, zenity, kdialog), idevice temp prefixes, internal names renamed at definition & every use (dam-people-picked event, text/dam-section drag type, dam-vib style id, dam-spin & dam-shimmer keyframes, theme pack headers, the 10 ids inside DAM-icon.svg), README macOS paragraph (dam-backend, DAM.app, the target.nosync output folder, the DAM library folder & its automatic adoption) & licensing line, LICENSES title/intro/icon row/control-line tag, LICENSE holder, build & packager text, apply_icon (defaults to /Applications/DAM.app). What still says DAMp on purpose: the five migration constants (LEGACY_DATA_DIR, LEGACY_CATALOG, LEGACY_ENV_PREFIX, the second WebKit cache id, KC_LEGACY), the two README sentences that explain those migrations, & the append-only history in this file, FEEDBACK_CHECKLIST & the HASHOUT logs. Verified here: ruff clean; pytest 37 passed, 1 skipped, 1 failing by design (test_trash, unchanged); DAM-icon.svg parses w/ 10 ids & 10 references, none unresolved; built CSS carries the renamed keyframes; frontend tsc clean, 10 vitest, build clean; every shell script parses; a repo-wide audit finds no other mention. Pending: FEEDBACK_CHECKLIST rounds 61 to 64, then DEV_PLAN phase 4, liquid glass parity w/ nodemode_dev v8.70.6.

## zip v1.18.1 (2026-09-18) · app reports v1.13.9

Round 63, rename DAMp to DAM, part 2 of 3 (internal contracts). Every name that crosses a component boundary moved on all sides in this one round: request headers x-dam-local & x-dam-vault (engine security.py, page api.ts/main.ts/importer.ts, shell engine_post/engine_get, both test suites), the control-line tag DAM-CTRL (engine importer.py & trash.py prints, shell filter), DAM_PORT (shell sets, desktop_entry reads), DAM_DIST/DAM_MODELS/DAM_LIBRARY (desktop_entry sets, config reads) plus DAM_FACE_THRESHOLD & DAM_TRASH_DAYS. config.env() prefers the DAM_* name & still honors a DAMP_* value when the new one is unset, so a dev shell or old .env keeps working (README & .env.example updated). Also renamed: API title, loopback rejection message, selfcheck key (the build log now prints "dam"), engine/exit/job thread names, the upload temp prefix, the iPhone-import & Touch ID shell messages, the ImageCaptureCore delegate class, the engine's Keychain service constant. Verified here: ruff clean; pytest 37 passed, 1 skipped, 1 failing by design (test_trash, unchanged); live engine: POST w/ x-dam-local 200, w/ the old x-damp-local 403, the menubar toggle prints DAM-CTRL TRAYSET 1 which the shell's starts_with("DAM-CTRL ") matches, the shell sends x-dam-local & sets DAM_PORT which desktop_entry reads; frontend tsc clean, 10 vitest, build clean. Rust compile untested here (Mac check). Remaining for part 3: 79 cosmetic mentions (23 SVG ids in DAM-icon.svg, UI copy in settings/people/collections/search, CSS keyframes & the vibrancy style id, theme pack headers, iccsvc/idevicesvc/native_picker copy & temp prefixes, README remainder, LICENSES, LICENSE, build & packager echo lines, apply_icon), then liquid glass parity. The five legacy names left on purpose are the migration constants (LEGACY_DATA_DIR, LEGACY_CATALOG, LEGACY_ENV_PREFIX, KC_LEGACY, the second WebKit cache id).

## zip v1.18.0 (2026-09-18) · app reports v1.13.9

Round 62, rename DAMp to DAM, part 1 of 2 (visible identity & data). Renamed: the repo folder, launchers (DAM, DAM.bat, DAM_oc_install, DAM_oc_install.bat), icon files (frontend/public/DAM-icon.png & .svg) & every reference, page title, splash, sidebar brand, app menu, About, window title, tray menu & id, Touch ID prompt, engine error dialogs, productName DAM, bundle id ai.nodemode.dam, crate dam-desktop (Cargo.lock root renamed w/ every pin kept), frontend package dam-frontend, engine binary & bundle resource dam-backend, the Info.plist usage string, the optional Icon Composer document name (DAM.icon), & the DMG (DAM_v*.dmg, volume DAM, DAM.app inside); the Settings menu event is dam-menu on the page & in the shell together. Migrations, automatic on first launch: ~/Library/Application Support/DAMp becomes .../DAM by atomic rename (only when DAM does not exist yet); damp.db w/ its -wal & -shm becomes dam.db before the first connection; the Keychain passkey is read from the old service once, copied to ai.nodemode.dam.vault & the old item deleted (expect one macOS Keychain prompt on the first Touch ID unlock, bc the app identity changed); the WebKit caches of both bundle ids are purged. Kept on purpose: the legacy names inside those migration constants (desktop_entry LEGACY_DATA_DIR, db LEGACY_CATALOG, main.rs KC_LEGACY, vaultcrypt WEBKIT_CACHE_IDS) until every install has migrated; historical entries in this file, FEEDBACK_CHECKLIST & the HASHOUT logs stay as written bc those logs are append-only & name artifacts that really were DAMp.

Verified here: ruff clean; pytest 37 passed, 1 skipped, 1 failing by design (test_trash, unchanged since v1.17.0); library-folder adoption w/ a fake home (DAMp renamed to DAM, contents intact); catalog adoption on the previous round's real encrypted test library (damp.db + WAL + SHM adopted as dam.db, 4 library items, the old passkey unlocks, the hidden item & its encrypted thumbnail still open, zero engine errors); frontend tsc clean, 10 vitest, build clean; every shell script parses. Mac checks: ./build_macos_app should end w/ src-tauri/target.nosync/release/bundle/macos/DAM.app & DAM_v1.13.9.dmg; first launch should show your library, Hidden, Recently Deleted & Touch ID unchanged; after DAM opens your library, delete the old DAMp.app from /Applications (launching it again would start a new, empty DAMp library). Rust compile untested here. Pending next round: part 2 of the rename (x-damp-* headers, DAMP-CTRL control lines, DAMP_* env vars w/ a legacy fallback, thread names, temp prefixes, the iccsvc delegate class, CSS keyframes & element ids, SVG ids, theme pack headers, UI & engine copy, .env.example, LICENSE, LICENSES, the rest of README, build & packager echo lines, apply_icon: 142 mentions in 39 files), the DEV_PLAN phase 3 split & the sidecar root HASHOUT entry for this round, then liquid glass parity w/ nodemode_dev v8.70.6.

## zip v1.17.0 (2026-09-18) · app reports v1.13.9

Round 61, privacy first. Root cause of the reported leak: Hidden, Recently Deleted & private albums were database flags only. Originals stayed in plain form under library/originals w/ their real names, every thumbnail sat in plain form in cache/thumbs, face crops in cache/faces, OCR text in the catalog, the /media/{id}/file & /thumb endpoints never checked the passkey for hidden or deleted items (only private ones), & WebKit cached thumbs for 7 days & originals for 1 day. Fix, encryption at rest (new backend/app/vaultcrypt.py): an X25519 vault key pair whose public half seals, so hiding or deleting needs no unlock, & whose private half is wrapped by scrypt(passkey) + AES-256-GCM (Touch ID unchanged: the shell already hands the engine the passkey). Albums w/ their own passkey get their own key pair, also sealed to the vault key so the vault passkey stays the master. Each protected item (hidden, trashed, private, & the Live Photo companion of any of those) gets a random content key; original + thumbnails are written to library/vault as random-named AES-256-GCM blobs in 64 KiB authenticated chunks (range reads, so protected video still seeks), & the plain original, plain thumbnails & face crops are deleted. OCR text & face-scan state move inside the encrypted envelope (scans skip vaulted items). Unhide, Restore & leaving a private album decrypt back to the same path, byte-identical; if the key is not open the flag reverts w/ a 401. A background sweeper encrypts everything already hidden/deleted/private at first launch (no unlock needed) & catches flags set outside the endpoints (duplicate resolve). Access: hidden & deleted items now need the vault token on every media endpoint; img & video tags cannot send headers, so unlock also sets an HttpOnly, SameSite=Strict cookie scoped to /api/media that the engine honors only on /thumb & /file (this also fixes private-album thumbnails, which could never load before); protected responses are no-store; the WebKit disk cache (~/Library/Caches/ai.nodemode.damp/WebKit) is purged once after this update & again at the next launch after anything gets protected; unlock tokens now die w/ the engine; hidden items no longer list inside albums; imports skip filenames still owned by an encrypted item. New dependency: cryptography 50.0.1 (Apache-2.0 OR BSD-3-Clause, flagged in LICENSES.md).

Install & build: backend/oc_install compared model hashes w/ `sha256sum -c --status`; macOS 27 ships a BSD sha256sum w/o --status, so the check failed, set -e aborted the root installer before the frontend install, & ./DAMp then said "vite: command not found". Hashes are now compared as strings via shasum (python fallback), & boot_frontend installs its own deps when vite is missing. Rust E0463 (can't find crate for zerofrom_derive): not reproducible here (that exact crate set compiles on Linux w/ Rust 1.98.1 & this release profile), so the build is hardened on every plausible cause: src-tauri/Cargo.lock is now committed & builds run --locked (zerofrom-derive 0.1.7, yoke-derive 0.8.2, synstructure 0.13.2, serde_with 3.14.0, displaydoc 0.2.5 pinned back from releases days old; tauri 2.11.5), [profile.release.build-override] stops stripping proc macros, build_macos_app builds into src-tauri/target.nosync (iCloud skips .nosync; the repo lives on ~/Desktop), neutralizes inherited RUSTFLAGS & rustc wrappers, retries once after a clean, & prints toolchain details on a second failure. The .app now lands in src-tauri/target.nosync/release/bundle/macos/.

Verified here: ruff clean; pytest 37 passed, 1 skipped, 1 failing by design (tests/test_trash.py asserts a trashed original stays in plain form in originals, which is the leak itself; not edited, awaiting your OK); live engine run: hide/trash moved originals out of originals/, zero plain thumbs left, no-token thumb & file 401, cookie thumb 200 no-store & decodes, hidden file bytes & a video byte-range (70000-200000) match the source exactly, unhide/restore/private-album removal restore byte-identical files, album cookie opens its item & the vault cookie opens it too, same-name import while protected lands as p3-1.jpg, token dies on engine restart, wrong passkey 401, delete-forever removes the blobs, the provisional key is gone after setup, zero engine errors; frontend tsc clean, 10 vitest, production build clean. Not run here (Mac checks): the Rust compile, the PyInstaller freeze + selfcheck (now reports cryptography), Touch ID unlock opening the vault key, the WebKit cache purge path, & first-launch migration of your real hidden/deleted items (expect their files to leave originals/ within about 15 s of launch). Limits that remain: earlier plain copies in Time Machine or APFS snapshots, filenames & dates still readable in damp.db, the Keychain copy of the passkey (readable by anyone w/ the Mac login password), & a forgotten passkey now means those items are unrecoverable (the setup dialog says so). Deferred to the next rounds: the DAMp to DAM rename w/ data migration, liquid glass parity w/ nodemode_dev v8.70.6, an optional one-time recovery key, the README line that still says trash is not a file move, the backend HASHOUT map & TOC line for vaultcrypt.py, & FEEDBACK_CHECKLIST round 61.

## zip v1.16.0 (2026-07-31) · app reports v1.13.9

Round 60 follow-through: every recorded next step of the iPhone thread, completed. (1) Photos-style device browsing: clicking a ready device opens an in-page grid of the camera roll (ICC requestThumbnail -> Quartz ImageIO JPEG, cached, 4-wide fetch pump, kind-glyph fallback, video durations) w/ Select All/None, per-tile selection, & Import Selected (n) / Import All; the ICC session stays open while browsing (idempotent open, /idevice/session/close on leave, deferred while a job runs) & every catalog snapshot carries a generation that downloads/thumbs/deletes validate, so stale grids error w/ guidance instead of importing wrong indexes. (2) Delete-after-import shipped as an opt-in checkbox: runs once at job end, only over items whose every file imported or was already in the library, reports deleted counts & deletion errors w/o failing the job; the never-delete default stands. (3) Live Photos merged into one asset on the ICC path: the sidecar download signal (ICSavedAncillaryFiles) links pairs at import (libraryfs.link_live, schema v4: media.live_video_id + media.live_of + index), companions leave all 15 general-query sites (media/search/summary/people/dedup/counts/faces/ocr), inherit the photo's private visibility at read time via guard.ensure_visible, & purge cascades both directions; grid tiles & the viewer show LIVE, the viewer plays the companion in place (stacked layer, no img-machinery rebuild), info panel says Live Photo. Fixed in review: v1.15.0's tmp-name key prefix would have leaked into imported filenames; downloads now use per-key subdirs w/ the camera's own names. Folder-import pair heuristics deliberately not built (sidecar signal is exact; stem-matching guesses) · recorded boundary. Build: pyobjc-framework-Quartz joins requirements_macos + collect flags + selfcheck. Verified here: 38 pytest + 1 skip (7 icc tests: roundtrip, contents/thumb/selective+stale-gen, delete-after-success-only, live pairing end-to-end, purge cascade, locked guidance, status detail), ruff, tsc strict, 10 vitest, production build. Mac checks: full ./build_macos_app, browse feel on a real roll (thumb latency, catalog time on thousands), Trust/Wired Accessories prompts, a real Live Photo pair (badge + playback), & a delete-after run on expendable shots first.

## zip v1.15.0 (2026-07-31) · app reports v1.13.9

Round 60: iPhone connect/sync rebuilt native. Root cause of the dead device path: unpinned pymobiledevice3 went async-only at 8.0.0 (2026-03-05), so the frozen engine's sync usbmux/lockdown/AFC calls returned un-awaited coroutines & listing raised on every poll; the package was also GPL-3.0-or-later inside the MIT app, unledgered. Replaced w/ Apple's ImageCaptureCore via pyobjc-framework-ImageCaptureCore (MIT), the Photos.app device-import framework: new services/iccsvc.py (browser registry, locked/untrusted from isAccessRestrictedAppleDevice, session -> full catalog -> per-file download w/ Live Photo sidecars -> import_one(move=True) pipeline), idevicesvc became the routing facade (icc primary, AFC optional dev fallback that self-disables w/ a reason on 8+), /idevice/status now returns full diagnostics. desktop_entry restructured on macOS bc ICC callbacks land on the main thread: CFRunLoop pumps on the real main thread (AppHelper.runConsoleEventLoop), uvicorn serves from a worker thread w/ a join-then-exit watcher. Import page: 3s auto-poll while open (roster-fingerprint gated, zero re-render when unchanged) so the device appears on its own; persistent status line; unsupported-on-macOS shows the reason instead of hiding the section; hints teach Trust This Computer + iOS 26 Wired Accessories. Build: requirements_macos swaps pymobiledevice3 -> pyobjc-framework-ImageCaptureCore; collect flags updated; Info.plist gains NSRemovableVolumesUsageDescription (merge, not overwrite, incl. the icon branch); Entitlements.plist (photos-library) wired for signed builds; LICENSES.md ledgered (pyobjc added, GPL removal recorded). Verified here: 34 pytest + 1 skip (3 new fake-bridge tests: roundtrip, locked guidance, status detail), ruff, tsc strict, 10 vitest, production build. Mac checks: ./build_macos_app (fresh .venv-package so the old GPL wheel leaves the freeze), plug in over USB w/ the phone unlocked, expect the device row within ~3s, Trust + Wired Accessories prompts on first connect, then Import Photos & Videos end-to-end; selfcheck JSON now reports imagecapture.

## zip v1.14.26 (2026-07-27) · app reports v1.13.9

Round 59, surgical privacy fix: trash & hidden pages gated BEFORE any render (Locked card; cached state discarded at mount), vaultGate fast-path on an existing token (no double prompts within a visit), clearVaultToken + cache clear on unmount so every entry re-locks. hasVaultToken added to api.ts. Nothing else altered. tsc clean, 10 vitest green, build clean.

## zip v1.14.25 (2026-07-27) · app reports v1.13.9

Round 58: ghost corner confirmed by user test = square CGS blur region. set_window_blur rebuilt on the radius-masked effect view (UnderWindowBackground, Active, radius 12, set_effects(None) at 0, clear_webview_backdrop after per round-32 ordering); CGS/SkyLight path deleted. Slider = on/off + shaped mechanism (system-defined strength, ledgered). Frontend untouched; build clean. Mac checks: compile, corner clean at blur>0, no material wash/edge (UnderWindowBackground, not HudWindow).

## zip v1.14.24 (2026-07-27) · app reports v1.13.9

Round 57: overlay titlebar reverted wholesale (native drag restored; drag-region IPC impossible on the engine-served page · logged). Ghost-corner titlebar theory disproven by field result; remaining candidate = square CGS blur region at the corner cutouts. Discriminator requested (Fade blur -> 0) before any further chrome surgery; shaped-effect-view blur is the scoped fix if confirmed. tsc/build clean.

## zip v1.14.23 (2026-07-27) · app reports v1.13.9

Round 56: ghost square corner = native titlebar backing drawn square on the unclipped transparent window (user screenshot). Fix: TitleBarStyle::Overlay + hidden_title (titlebar material gone, page owns full surface), #app rounds all four corners, sidebar padding-top 44px clears traffic lights, 30px data-tauri-drag-region strip + start-dragging capability. tsc/build clean; Mac checks: compile, light inset, drag feel.

## zip v1.14.22 (2026-07-27) · app reports v1.13.9

Round 55: border root-caused via ghostty discussion 9611 + Apple NSWindow.hasShadow docs · the Tahoe styled edge IS the shadow (one property, inseparable). setHasShadow(false) in clear_webview_backdrop; invalidateShadow + 10s pulse removed. Trade: drop shadow gone w/ the edge (documented as inseparable). Frontend untouched; Rust compile is the Mac check.

## zip v1.14.21 (2026-07-27) · app reports v1.13.9

Round 54: continuous shadow re-invalidation (10s main-thread pulse) · the round-45 one-shot invalidateShadow only held until content changed, so the stale-shadow rim recurred mid-session; round-53 files verified untouched on chrome (no clip-path, #app radius intact). tsc/build clean; Rust compile is the Mac check.

## zip v1.14.20 (2026-07-27) · app reports v1.13.9

Round 53: rollback to the user-endorsed v1.14.13 grid (copied from their uploaded zip) + two scalpel fixes: markWaiting/thumb-wait shimmer hooks (compositor ::after from round 49 retained in CSS) & decode-gate removal (reveal on load). Rounds 47-52 grid machinery deleted (window, skeleton, spacer, slide); skeleton/spacer CSS stripped. All non-grid improvements retained (WebP, splash launch, border fixes, panel/topbar glass, presets, HUD). tsc clean, 10 vitest green, build clean. 260/1300 window specs shelved pending user call.

## zip v1.14.19 (2026-07-26) · app reports v1.13.9

Round 52, single surgical fix: the img.decode() reveal gate (round 45) starved visibility during scroll at round-51 window scale (WebKit deprioritizes decode while scrolling; ~1300 queued decode promises) -> loaded images stayed invisible behind the shimmer. readyAfterDecode now reveals directly on load (decoding=async attribute retained). tsc clean, 10 vitest green, build clean. Mac check: thumbs appear WHILE scrolling.

## zip v1.14.18 (2026-07-26) · app reports v1.13.9

Round 51. User-specified resident window implemented: WINDOW_MAX 1300 / ADVANCE 1000 / 300 overlap; slideWindow() advances (dropRange + spacer grows by measured height) & retreats (reverse prepend via ensureDayFront, spacer shrinks, residual scrollTop compensation, tail trim to bound residency); topSpacer conserves geometry px-for-px. content-visibility REMOVED (it re-rasterized returning sections = the scroll-up flash; correction logged); bounded DOM is the scroll-cost mechanism now. Pager keeps 1300 items fetched ahead of winStart; lanes feed every resident pending thumb nearest-first (window filter dropped). Verified: tsc clean, 10 vitest green, build clean, window arithmetic simulated. Mac checks: scroll-back flash gone, retreat geometry, memory w/ 1300 decoded tiles.

## zip v1.14.17 (2026-07-26) · app reports v1.13.9

Round 50, /verified. Launch: reveal moved to the splash's PageLoadEvent::Finished (splash animation restored, perceived-instant launch, engine boots visibly behind it; app-ready keeps backdrop/focus polish; failsafe 6s -> 2s) · the 7s stall was the round-45 reveal spanning the engine cold start, not an auth failure (guard checked, hypothesis corrected in the ledger). Scroll: .view-pad section gets content-visibility auto + contain-intrinsic-size auto 640px (web.dev + MDN cross-sourced, Safari 18+), offscreen day sections cost zero render/paint/composite & shimmer layers collapse to visible tiles; :has selectors deleted (thumb-wait class is authoritative). Verified here: tsc clean, 10 vitest green, build clean. Mac checks: on_page_load closure compiles, launch shows splash instantly, flick-scroll smooth, HUD ahead near full.

## zip v1.14.16 (2026-07-26) · app reports v1.13.9

Round 49, run under /verified. Root cause sourced (web.dev animation guides + independent corroboration): round 48's background-position shimmer was a paint-property animation -> main-thread paint storms across 96 cells + waiting tiles -> worse loading AND a stalled (invisible) animation, one mechanism for both symptoms. Fix: shimmer as ::after gradient overlay animated w/ transform: translateX (compositor-only), applied to thumb-wait/skel-tile/:has fallbacks; reduced-motion static fill; skeleton 96 -> 30 cells. Pager measures distance to gridWrap's real bottom (skeleton height decoupled; honest note: arithmetic shows the old distortion never fired later than v1.14.14, secondary fix). Verified here: tsc clean, 10 vitest green, build clean, pager math simulated. Mac check: shimmer visibly sweeping during a hard flick w/ loading unaffected.

## zip v1.14.15 (2026-07-26) · app reports v1.13.9

Round 48. Blank-page-while-scrolling: translateZ(0) removed from the global .view (async raster of the giant composited layer was the 1-2s blank; kept Collections-only), & the pagination seam is covered by a permanent 96-cell shimmer skeleton (same grid geometry) shown whenever more items exist or a fetch is in flight; pager prefetches at max(2400, 2x window) on scroll AND a 400ms beat. Shimmer rebuilt visible: layered 0.16 white sweep over tile base, JS thumb-wait class (set at load start, cleared at decoded reveal) + :has fallback, reduced-motion static fill, skeleton cells share it. Verified: tsc clean, 10 vitest green, build clean. Mac check: fast-flick scroll · expect shimmer, never blank.

## zip v1.14.14 (2026-07-26) · app reports v1.13.9

Round 47. Preload window switched to item count: PRELOAD_ITEMS 130 each direction, px derived from live cols (proof: 6c/22r, 12c/11r, 3c/44r); pager uses same. Shimmer skeleton on .tile/.strip-cover via :has(img:not(.ready)), reduced-motion aware. Top bar glass: own prefs.top {opacity 16, blur 22 = today's look}, tokens --glass-bg-top/--glass-blur-top, sliders in the Side panel tab (global scope; sidebar stays Collections-scoped), reset covered. Theme presets: named snapshots of full ThemePrefs in prefstore (save/apply/delete; apply closes the modal for clean rebuild). Verified: tsc clean, 10 vitest green, build clean, window math simulated. Mac checks: shimmer feel, 260-window scroll feel, preset roundtrip.

## zip v1.14.13 (2026-07-26) · app reports v1.13.9

Round 46. Thumbnails to WebP v4 (same 192/384/768 resolutions, q80): generation, video posters & placeholders all WebP; endpoint serves by suffix; legacy _v3.jpg converts lazily on first request. New standalone app/upgrade_thumbs.py (separate script per request): first-launch background sweep (niced, 3s grace, atomic replaces, purges pre-v3 + jpeg placeholders, .v4_done marker, resumable), also runnable as python3 -m app.upgrade_thumbs. Sandbox proof: 3 converted + 1 purged, rerun no-op, 89 percent smaller on synthetic frames (expect 30-50 percent on real photos). Suite 31+1 green (mime test updated), ruff clean. Frontend untouched.

## zip v1.14.12 (2026-07-26) · app reports v1.13.9

Round 45, guided by the user's research doc. Border fix: invalidateShadow on every backdrop clear & reveal (stale transparent-window shadow rim), html clip-path deleted (perimeter AA ring) & bottom corners moved to border-radius on #app + sidebar bottom-left. Launch: hidden-until-painted (visible false; page double-rAF ready -> WINSHOW ctrl -> clear + show + focus; 6s shell failsafe). Gallery: img.decode() before the ready fade (zero mid-decode snap) in loadThumb & loadImage. Backend /system/window gains ready -> WINSHOW (test added, 31+1 green, ruff clean). Frontend tsc clean, 10 vitest green, build clean. Mac checks: Rust compile (invalidateShadow call), launch reveal feel, border gone on-device, DMG transparency per the doc's known bug.

## zip v1.14.11 (2026-07-26) · app reports v1.13.9

Round 44. Preload hardening + instrumentation: 300ms heartbeat sweeps all lanes (2s offset re-measure pulse) making the runway independent of every event hook; 12s once-only watchdog per request so a swallowed load/error can never wedge the in-flight cap; live diagnostics HUD (Settings > App, persisted) showing pend/q/fly/ahead/behind/load-ms fed from each sweep. Verified here: tsc clean, 10 vitest green, vite build clean. The HUD is the contract for the next report: a mid-scroll screenshot replaces theorizing.

## zip v1.14.10 (2026-07-26) · app reports v1.13.9

Round 43. Preload root cause finally structural: assignment was fixed by round 40 but WKWebView's ~6 loopback connections served the 13-row burst FIFO, putting viewport-entering images behind stale lookahead traffic. New bounded scheduler in grid.ts: MAX_FLIGHT 14, queue holds only in-window images nearest-first, rebuilt from live distances each sweep; scrolled-away items dequeue; homeless fallback & new loadImage (face covers, strips) ride the same pipeline. Pagination also scroll-driven (loadMore under max(1600, lookahead) remaining; sentinel kept as backstop). Side-panel glass scoped to Collections via route-collections root class (base sidebar back on app tokens); settings note updated. Collections strips uncapped (people 12-cap & recent-days 10-cap removed; albums already full). Verified here: tsc clean, 10 vitest green, vite build clean, scheduler priority proven by simulation (post-scroll next-started = the ten nearest). Mac checks: scroll feel at speed, strip drain on big libraries.

## zip v1.14.9 (2026-07-26) · app reports v1.13.9

Round 42. Side panel made a first-class system: new side prefs (opacity default 58, blur default 28), dedicated Settings tab (Side panel, panel icon) w/ live Panel opacity & Panel blur sliders, tokens fed only from those prefs (1.26x derivation deleted), reset covered. Backdrop-blur escalation, four layers: fade paint moved body -> #app (real painted parent per upstream 12804; hex canvas relocated inside #app via #bg-holder first child, visually unchanged), #app isolation: isolate (pinned backdrop root), .view translateZ(0) (composited content backing), -webkit-font-smoothing: antialiased app-wide (subpixel AA vs transparent backings is the text-punch-through culprit). Verified here: tsc clean, 10 vitest green, vite build clean. Mac check: whether Tahoe WebKit samples at all in transparent windows; fallback documented as the opacity slider.

## zip v1.14.8 (2026-07-26) · app reports v1.13.9

Round 41. Sidebar backdrop blur over text fixed per upstream tauri 12804 (WebKit defect in transparent windows, worst over text): the documented parent-background workaround applied (#app & .content at 2 percent alpha smoke, imperceptible) + translateZ(0) on .sidebar for its own compositing layer. Sidebar glass now fully separate: --glass-blur-side = max(18, app glass blur x 1.26) joins the 1.26x density token; default 22px app -> 28px sidebar. Verified here: tsc clean, 10 vitest green, vite build clean, blur derivation simulated across slider range. Mac check: WebKit behaviour on Tahoe (the defect is upstream); escalation path scoped in the checklist if text still reads crisp.

## zip v1.14.7 (2026-07-26) · app reports v1.13.9

Round 40. Preload rebuilt deterministic: the thumb IntersectionObserver is retired after its third on-device failure; per-.view lanes w/ cached offsets load exactly viewport +/- 13 rows on each scroll frame (rAF-throttled, dirty-marked re-measures on adoption/zoom/resize/media events, homeless adoption & never-blank fallback kept). Sidebar glass: new --glass-bg-side token = glass alpha x 1.26 (cap 0.92), sidebar-only, sliders still consequential; backdrop blur of content beneath stays by design. Shell: unused mut removed (main.rs builder). Verified here: tsc clean, 10 vitest green, vite build clean, lane membership simulation exact (zoom 184 -> +/-2548px); backend untouched (suite unchanged). Mac checks: Rust compile, scroll feel at speed, the 1.26 density taste.

## zip v1.14.6 (2026-07-26) · app reports v1.13.9

Round 39. Window fade rebuilt background-only on the mechanism the round-34 screenshot proved (kvc_bg=1): window transparent(true), shell clears the WKWebView backdrop (NSWindow non-opaque + clear, KVC drawsBackground=false w/ read-back, guarded underPageBackgroundColor clear, alpha pinned 1.0), re-asserted 50/250/700/1500/3000ms after navigation & on every /system/window post (WINCLEAR). NSWindow-alpha fade (WINALPHA) deleted; page paints the background at 1-fade alpha (fade 0 solid default, 100 bare desktop; tint/frost colour the paint), plain-rgba in JS, html forced transparent, bottom corners page-clipped via --win-radius (user's macOS 26 draws no rounded clip on transparent windows). Fade blur unblocked by construction (CGS blur needs translucent pixels; the old window was opaque). 13-row preload veto found: tiles carried loading="lazy", so WebKit re-deferred fetches the observer had already triggered · loadThumb now forces eager. Sidebar/topbar liquid glass restored: removed the appended opaque --bg-elev background in .sidebar, the late html.vibrancy opaque overrides, & the injected !important paints · glass tokens (& their sliders) rule those surfaces again, independent of fade. Diag line (win_opaque/webviews/kvc_bg/underpage) posted to the engine & shown under the fade note. Verified here: tsc clean, 10 vitest green, vite build clean, backend 31 passed + 1 skipped, ruff clean (fixed a pre-existing E401 in test_idevice.py), fade paint proven by simulation (0 -> a=1.0, 54 -> 0.46, 100 -> 0.0, frost 80 -> rgba(185,184,184), tint -100 -> light wash). Mac checks: Rust compile, actual transparency/blur/corners on-device, --win-radius taste.

## zip v1.14.5 (2026-07-26) · app reports v1.13.9

Round 38. macOS transparency mode REMOVED from the shell entirely: no transparent(true), no WindowEffectsConfig/Effect, no material switching, no force_transparency/strip_view_opacity/reassert loops, no glass diagnostics, no leftover statics or imports. The window is an ordinary opaque macOS window (native rounded corners, no border, no square edges) · transparent mode w/o an effect view was the cause of both. Window fade restored as macOS window opacity (Fade amount, 30-100, default 100/off, persisted). Fade blur = desktop blur behind the window; Fade tint & Fade frost recolour the app background opaquely (crisp, independent of fade). Frontend + shell; full ./build_macos_app.


## zip v1.14.4 (2026-07-26) · app reports v1.13.9

Round 37. Collapsed to ONE feature: Window fade, background-only, w/ Fade amount + Fade tint + Fade frost + Fade blur under a single heading. No translucency checkbox, no system material, & macOS window opacity is never used (pinned 100 at boot & on every push, clearing stored fades from v1.13.997-v1.14.3). Fade amount 0% = fully solid app, so nothing is forced on. Frontend-only; run ./build_macos_app.


## zip v1.14.3 (2026-07-26) · app reports v1.13.9

Round 36. Whole-window fade RESTORED (macOS window opacity, 30-100%, default 100/off, persisted, re-applied at boot, drives WINALPHA again) alongside the background-only group. Removing it in v1.14.1 was a mistake: a working control should not be deleted for a cleaner model. Section is now: Window fade (background) + Tint + Frost + Blur, then Whole-window fade w/ its own note. Translucency checkbox stays removed, but nothing is forced: fade 100% + Window fade 0% = the old solid look. Frontend-only; run ./build_macos_app.


## zip v1.14.2 (2026-07-26) · app reports v1.13.9

Round 35. Preload repaired (it was present, but defective): observeThumb resolved the scroller after ONE rAF & fell back to a NULL root when the tile was still detached, giving a viewport-rooted observer whose rootMargin is inert against an inner scroller · & that null root was cached, so one early tile disabled preloading for the session. Now: null roots are never used, unattached tiles are queued & retried per frame (40 frames, then loaded outright), observers are kept per scroll container in a Map, & the pagination sentinel rebuilds against the real scroller if its host was detached at creation. 13-row math verified across zooms. Frontend-only; run ./build_macos_app to refresh dist.


## zip v1.14.1 (2026-07-26) · app reports v1.13.9

Round 34 · Window section restructured per instruction. Native window translucency checkbox REMOVED (glass always on, no system material ever installed, saved themes migrated). The native whole-window opacity control is retired & pinned to 100 at boot (it composites the finished window, so it could never be background-only). New single Window glass group: Window fade (0 = solid background, 100 = pure blurred desktop) owns opacity, w/ Tint (colour, negative = light), Frost (whitens) & Blur (desktop blur strength) tied to it. Old winAlpha migrates to bgFade = 100 - winAlpha. Simulation-verified across the range. Full ./build_macos_app.


## zip v1.14.0 (2026-07-26) · app reports v1.13.9

Round 33 · the diagnostic paid off. User's Mac reported draws_bg_sel=0: WebKit exposes no setDrawsBackground: method, so the respondsToSelector guard skipped the one call that stops WKWebView painting its own background. Now set via KVC (setValue:forKey:"drawsBackground"), unconditionally, after set_effects; diagnostic gained kvc_bg. Match Terminal glass preset removed (built on the broken assumption). Whole-window fade demoted to a labeled fallback (NSWindow opacity cannot be scoped to the background); the four background controls are primary. Full ./build_macos_app.


## zip v1.13.999 (2026-07-26) · app reports v1.13.9

Round 32 · THE ordering bug. set_window_material ran force_transparency BEFORE set_effects; set_effects rebuilds the view tree & WebKit then re-establishes its opaque backdrop, so every launch ended by re-opaquing the web view (defeating every fix since round 25). Now: effects -> force_transparency -> re-assert at 120/250/500/1000ms; blur handler re-asserts too; post-navigate schedule extended to ~12s. hud_config removed (dead-code warning). Diagnostic line retained in Settings. Full ./build_macos_app.


## zip v1.13.998 (2026-07-26) · app reports v1.13.9

Round 31. (1) No effect view under translucency (the HudWindow inset WAS the border frame; Terminal ships no material either). (2) Page-side opacity closed off for good: an injected !important rule set covers html/body/#app/main/.content/.view/.view-pad, beating any stylesheet. (3) The shell now measures & reports native state to the engine (/internal/shell/glass -> GET /system/glass), surfaced in Settings: window_opaque / views_cleared / webviews / draws_bg_sel / underpage_sel. (4) Whole-window fade retained. Full ./build_macos_app.


## zip v1.13.997 (2026-07-26) · app reports v1.13.9

Round 30. (1) Whole-window fade restored as its own control (the v1.13.991 NSWindow-opacity mechanism, 30-100%, default 100/off, persisted + re-applied at boot, labeled as fading all content). (2) Transparency forcing widened from the web view alone to the ENTIRE native content tree: every layer switched non-opaque w/ its background cleared, plus setDrawsBackground / _setDrawsBackground / underPageBackgroundColor on the web view, all selector-guarded; runs post-build, on a 0/400/600/1000/2000ms schedule after the engine navigation, & on every window-mode assert. Material still swapped (HudWindow) not removed, so corners stay. Full ./build_macos_app.


## zip v1.13.996 (2026-07-26) · app reports v1.13.9

Round 29 · ROOT CAUSE of the whole transparency saga. Tauri sets WKWebView transparency at window CREATION only; DAMp builds the window on splash.html then navigates to the loopback engine URL, which re-establishes an opaque webview backdrop (hence: invisible page translucency, unseeable material, & square opaque corners when the effect view was removed). New force_transparency() re-asserts NSWindow setOpaque(false)+clear background, WKWebView drawsBackground=false, & underPageBackgroundColor=clear at three moments: post-build, post-navigate, & on every window-mode assert from the page. All via raw objc msg_send (no typed-API signature risk, respondsToSelector guard, no unnecessary-unsafe warnings). Plus a Match Terminal glass preset decoded from the user's real .terminal profile (black alpha 0.486, blur 0.261 -> tint 49 / transparency 100 / frost 0 / blur 13). Material still swapped (HudWindow) rather than removed, so corners stay. Full ./build_macos_app.


## zip v1.13.995 (2026-07-26) · app reports v1.13.9

Round 28 (one-line shell fix): set_effects(None) on macOS removes the effect view that carries the clear webview background AND the rounded-corner clip (square corners + opaque window = the .994 report). The material now swaps to HudWindow (most translucent blur material) under vibrancy instead of being removed; standard material returns when vibrancy is off. Full ./build_macos_app.


## zip v1.13.994 (2026-07-26) · app reports v1.13.9

Round 27: the Terminal model. Under translucency the shell removes the NSVisualEffect material entirely (new WINMAT control; vibrancy toggle + boot send it) & CGS blur owns softness: desktop -> adjustable blur (default 28; stored 0 migrates, use 1 for none) -> page tint/frost paint -> solid content. Transparency slider is dramatic again (0% = raw blurred desktop) w/o touching photos/text (NSWindow alpha stays retired). Engine /system/window gains material (33 pytest). Full ./build_macos_app; Mac check: CGS radius visibly softening the desktop w/ the material gone.


## zip v1.13.993 (2026-07-26) · app reports v1.13.9

Round 26. Transparency regression fixed at the root: the nested color-mix w/ a percent-times-number calc was invalid CSS, so the whole background declaration was dropped & nothing painted; vibrancy paint is now plain rgba computed in applyTheme (--vib-body/--vib-side/--vib-top), simulation-proven across the slider ranges. macOS-26 icon notes condensed to one line per script. DMG launch diagnosis pending the four-way answer (no-mount / no-window / drag-fails / Gatekeeper). Frontend + script text only; run ./build_macos_app to refresh the bundled dist.


## zip v1.13.992 (2026-07-26) · app reports v1.13.9

Round 25. Window transparency re-pointed from NSWindow alpha (which faded the whole tree incl images) to a background-only page-space multiplier; NSWindow-alpha UI retired, boot sends alpha 100 to clear prior fades. New Window frost slider (0-100) whitens the painted background. Blur handover: shell removes the NSVisualEffect material while radius>0 so CGS blur is unmasked, restores it at 0. Four Window sliders now act on the background alone. Full ./build_macos_app; Mac checks: blur visibility w/ material removed, frost/transparency feel.


## zip v1.13.991 (2026-07-26) · app reports v1.13.9

Round 24 (fixes). Removed 2 unnecessary unsafe blocks (setAlphaValue/windowNumber). Packager: sign AFTER xattr strip so the seal is coherent; verify matched to signature type (plain --verify for ad-hoc, --deep --strict only for Developer ID) · kills the false "does not verify". DMG auto-open restored: the arranged Finder window is LEFT OPEN (closing it persisted a closed state into .DS_Store, the real cause), flushed w/ update+sync before detach, volume name read from the live mount. Full ./build_macos_app then ./package_dmg (or just the build, which calls it).


## zip v1.13.99 (2026-07-26) · app reports v1.13.9

Round 23: the Window trio. Tint now signed (-100..100; negative paints translucent light bc zero page-paint cannot get brighter w/o counter-painting the material's inherent tint). Window transparency = real NSWindow alpha (30-100) & Window blur = compositor background blur radius (0-64, SkyLight private symbol, runtime-resolved, no-op fallback), both over the DAMP-CTRL channel, persisted, re-applied at boot. Deps: objc2-app-kit (NSWindow), libloading. Engine clamps (32 pytest). Full ./build_macos_app; Mac checks: new deps compile, alpha & blur feel, private-symbol resolution on macOS 26.


## zip v1.13.98 (2026-07-26) · app reports v1.13.9

Round 22. Icon forensics: the provided icns is pixel-verified transparent at every size; the macOS 26 squircle is system-drawn everywhere incl Get Info (earlier Get Info claim corrected). Signature order fixed: icns lands BEFORE the build, post-build is verify-only, packager modifies+re-signs only on diff · tauri's signature ships untouched. Developer ID auto-detected & used by build+packager+apply_icon (verify + signer reported; ad-hoc messaging only when true). Icon Composer pipeline gated in: src-tauri/icons/DAMp.icon -> actool -> Assets.car + CFBundleIconName, automatic once the file exists. bash -n on all three scripts.


## zip v1.13.97 (2026-07-26) · app reports v1.13.9

Round 21.

- Observers re-rooted: thumbnails & the pagination sentinel now watch the .view scroller (rootMargin vs the window viewport was inert against inner-scroller clipping); 13-row bidirectional preload is real now.
- Window tint 0-140: 0-100 = full paint range of the theme background; 100-140 deepens the tint color itself toward solid black.
- Packaging: build_macos_app ends w/ the DMG again (delegates to package_dmg); NEW ./apply_icon stamps the provided icns onto an installed /Applications/DAMp.app, re-signs, & nudges Finder/Dock (deep cache-flush command printed).

Verified here: 31 pytest, ruff, tsc strict, 10 vitest, production build, bash -n on all three scripts. Full ./build_macos_app.


## v1.13.9 (2026-07-26) · zip DAMp_v1.13.96

Round 20. Version split per instruction: manifests & all displayed surfaces 1.13.9; zip numbered v1.13.96.

- Lookahead: thumbs & pagination preload 13 rows of the CURRENT tile size, both directions, rebuilt on zoom changes.
- Vibrancy: canvas transparency made explicit (alpha:true ctx, transparent layer/canvas backgrounds; vendored-kit note) + a Window tint slider (0-80%) that doubles as the isolation diagnostic: tint 0 = the page paints nothing.
- OCR lifecycle: sessions released after every scan, threads capped (2/1), per-item yield, & availability probes no longer instantiate the model.

Verified here: 31 pytest, ruff, tsc strict, 10 vitest, production build, & an in-container proof that engine_name spawns no session. Full ./build_macos_app.


## v0.13.95 (2026-07-26)

Round 19: packaging split out of the build. ./package_dmg is the standalone release step: icns enforced byte-for-byte into any DAMp.app (icon name & VERSION read from the app's Info.plist), quarantine cleared, ad-hoc re-sign, race-hardened DMG build w/ volume icon, bless --openfolder (the missing auto-open that made the previous DMG feel dead on double-click), & a guarded Finder window arrangement (icon view, app left, Applications right). build_macos_app now ends at the patched .app. Public-release commands (Developer ID + notarytool + stapler) printed by the packager. Scripts bash -n verified; the hdiutil/bless/osascript trio is a Mac check by nature.


## v0.13.94 (2026-07-26)

Round 18: Glow & Bloom split into independent 0-200 controls. Glow = lit hex strokes (0 = never lights; >100 overdrives stroke width to 2.4x via a documented vendored-kit glowWidth extension, lit pass only). Bloom = pointer light wash (0 = off; 200 = 2x the old max). Old coupled setting migrates to equivalent positions. Frontend-only; re-run ./build_macos_app to refresh the bundled dist.


## v0.13.9 (2026-07-26)

Round 17 of FEEDBACK_CHECKLIST.md.

- Text scan: engine-aware card, always visible under the Text in image scope; Scan pending / Rescan all (force clears stored text & re-reads w/ the bundled model); plain-language state when no engine loads.
- Vibrancy: effect state pinned Active w/ material fallback (UnderWindowBackground, Sidebar); page side re-verified. Residual suspect named in the checklist if macOS still refuses.
- Settings: 3-column aligned slider grid, 560px measure, section rhythm, readable checks, wider nav.

Verified here: 31 pytest, ruff, tsc strict, 10 vitest, production build. Full ./build_macos_app (shell changed).


## v0.13.8 (2026-07-26)

Round 16 (patch): the DMG race. .metadata_never_index in staging, attach -nobrowse -noverify -noautoopen, device-node detach w/ retries + force fallback, sync/settle barriers, convert retries, stale /Volumes/DAMp pre-detach, & an automatic direct-UDZO fallback so a DMG always ships. Re-run ./build_macos_app; no app-code changes.


## v0.13.7 (2026-07-26)

Round 15 of FEEDBACK_CHECKLIST.md.

- Persistence: ephemeral loopback ports gave every launch a fresh localStorage origin; ALL UI prefs (theme, zoom, sort, grouping, search scopes, album collapse & per-album sort, settings tab) moved into the engine settings table via /prefs/ui, fetched once before first paint (top-level await + hydrate). Settings now genuinely survive quit/reopen.
- The provided cog replaces the gear glyph kit-wide.
- Icon pipeline: build app only -> overwrite bundled icon.icns w/ the provided file -> ad-hoc re-sign -> hand-build the DMG from the patched app w/ the same icns as volume icon. macOS 26 note printed by the script: the Dock backing behind legacy icns is system-drawn; full removal needs Icon Composer's .icon format (Xcode).

Verified here: 31 pytest, ruff, tsc strict, 10 vitest, production build, bash -n on the build script. Full ./build_macos_app required. Mac checks: hdiutil DMG flow & SetFile volume-icon flag.


## v0.13.3 (2026-07-26)

Round 14 of FEEDBACK_CHECKLIST.md: 7 items.

- Viewer: stage images re-centered (inset+margin auto), crosshair scoped to the image only, Reset View always present (disabled at 1x).
- Settings: 780px wide, tabbed w/ a left rail (Appearance/Background/App/Library/Vault & Keychain), last tab remembered.
- Real translucency: w/ Native window translucency on, the page paints at 46% (sidebar 34%, topbar 30%) so the macOS material shows through like the Terminal reference.
- Menu-bar tray agent from the provided SVG (template icon): Import Photos & Videos..., Import Folder..., Open, Quit; imports post as ONE multi-root engine job; closing the window hides the app while the tray is on. Toggle in Settings > App.
- Hide/delete: no grid rebuild; removed tile shrinks out & siblings FLIP-slide into place; day counts patch in place.
- Text-in-image: RapidOCR (ONNX, offline) bundled as the primary engine, tesseract fallback; smoke test reads the exact previously-failing query at 0.98. Run the text scan once after updating.
- Scroll smoothness: thumbnails are viewport-driven via a shared IntersectionObserver (1100px lookahead, async decode, fade-in), ending the 400-requests-per-page storms.

Verified here: 31 pytest (multi-root import, menubar pref), ruff, tsc strict, 10 vitest, production build. Full ./build_macos_app REQUIRED (requirements, Cargo features, icons changed). Mac checks: tray compile/dialogs/close-to-hide, vibrancy tint percentages, zoom & FLIP feel. Both freeze collects (rapidocr + pymobiledevice3) are now verifiably present; the earlier pymobiledevice3 wiring claim was false & is corrected.


## v0.13.1 (2026-07-26)

Round 13 of FEEDBACK_CHECKLIST.md (patch release).

- Drop-to-import on the Import page: multipart /import/upload through the full pipeline (dedup, HEIC, posters, OCR autostart), dashed accent dropzone w/ depth-tracked highlight, window drop-navigation blocked. python-multipart added to requirements.
- Assets: new public folder (icon png/svg + splash) verbatim from the upload; src-tauri icon.png replaced; the provided transparent icon.icns is kept pristine in icons/source & restored after cargo tauri icon (which regenerates & flattens it) so the bundled .app honors transparency.

Verified here: 29 pytest, ruff, tsc strict, 10 vitest, production build. Full ./build_macos_app required (requirements + icons + public changed).


## v0.13.0 (2026-07-26)

Round 12 of FEEDBACK_CHECKLIST.md: the liquid-glass finale, spec'd by two Terminal screenshots.

- pop-surface: one Terminal-grade container recipe (dark 64% tint, >=26px blur scaling w/ the glass slider, 1px light border, 14px radius, deep shadow) applied to every floating surface: context menus, the filter dropdown, sort menus, all modals incl Settings, the selection bar, the filmstrip & toasts.
- Settings Background controls: Effect radius (120-520) & Bloom/glow (0-100) drive the kit background's radius/strokeAlpha/washAlpha live (debounced remount) & persist w/ the theme; accent changes now retint the effect instantly (the kit already samples --accent; applying a theme triggers its refresh).

Verified here: 28 pytest, ruff, tsc strict, 10 vitest, production build. Frontend-only; re-run ./build_macos_app to refresh the bundled dist. Feel-checks on the Mac: tint depth vs the Terminal reference & the two new sliders' ranges.


## v0.12.0 (2026-07-26)

Round 11 of FEEDBACK_CHECKLIST.md: 8 items.

- Viewer: box-select zoom (to 8x) w/ pan, double-click & pinch reset, & a Reset View button that appears only while zoomed; the filmstrip now auto-hides, appearing on hover or for 1.3s after any step.
- People: Set as Cover on any tile of a person's page; cover_locked (schema v3, real migration) makes automatic refresh respect it permanently.
- Albums: reordering rewritten pointer-based (lift threshold, live indicators, commit on release) AND the shell's drag-drop handler is disabled on the window, the machinery that was starving HTML5 drag all along.
- Icons: the provided sortLines trigger + five sort-mode SVGs verbatim in the kit; filter menu options carry real glyphs (two crafted: screenshot, albumOff) w/ the active choice in accent currentColor.
- Navigation: per-route scroll memory + the viewer restores the exact scroll position on close. No more jumps to top.

Verified here: 28 pytest, ruff, tsc strict, 10 vitest, production build. Mac checks: drag feel, zoom/pan feel, strip fade timing, the disable_drag_drop_handler call compiling (name per tauri v2; pointer path works regardless).


## v0.11.0 (2026-07-26)

Round 10 of FEEDBACK_CHECKLIST.md: the last carousel glitch + the iPhone import feature.

- Viewer rewritten build-once/patch-forever: persistent chrome & filmstrip, double-buffered stage w/ cross-fade + in-place full-res upgrade, text/attr patching for title/counter/fav/download/arrows. The per-step replaceChildren (the flash & the strip reset) is gone.
- iPhone import over usbmuxd + AFC via pymobiledevice3 (pure python, bundled): device list w/ trust-state guidance, DCIM pull through the normal import pipeline (sha dedup, HEIC, posters, follow-on jobs), progress w/ current filename. No device deletion in v1; Live Photos arrive as photo+video pairs.

Verified here: 27 pytest (fake-device AFC roundtrip incl re-import dedup), ruff, tsc strict, 10 vitest, production build. Mac checks: real device Trust flow, large-roll pull performance, & the viewer feel.


## v0.10.0 (2026-07-26)

Round 9 of FEEDBACK_CHECKLIST.md: Touch ID & Keychain, redesigned after research (the user was right to demand it).

- Root cause: remote-origin windows get no Tauri IPC, & the loopback UI is remote-origin, so the v0.6.0 page-invoke design was dead on arrival; its silent fallback hid that.
- New shape: page -> engine over plain HTTP only; engine -> shell via DAMP-CTRL stdout lines; shell -> engine answers over loopback w/ the local header. LAContext (biometrics policy) & the Keychain item both live in the shell via objc2-local-authentication (features LAContext+block2, per docs.rs) & security-framework (set/get_generic_password; ItemSearchOptions presence probe that never prompts). The shell hellos its capabilities at startup so status is instant everywhere.
- The passkey never enters the page; the engine verifies it against the vault hash before issuing any token. IPC surface: zero page-facing commands (withGlobalTauri off; ledgered in LICENSES.md).

Verified here: 26 pytest (3 new channel roundtrips), ruff, tsc strict, 10 vitest, production build. Requires full ./build_macos_app (new Rust deps). Mac checks: cargo build of the new deps, the Touch ID sheet, silent Keychain read after DAMp-owned store, one-time Allow on pre-existing CLI-created entries.


## v0.9.1 (2026-07-25)

Round 8 of FEEDBACK_CHECKLIST.md: filmstrip stepping.

- One step per gesture, enforced by a latch that re-arms only after 160ms of wheel silence; fixed cool-downs cannot bound a momentum gesture & the old 240ms window let a single flick fire several steps.

Verified here: tsc strict, 10 vitest, production build (backend untouched; suite still 23 green). Re-run ./build_macos_app to refresh the bundled dist. The 160ms quiet window & 42-delta threshold are feel-constants: report back if a flick ever double-steps or a gentle scroll refuses to step, & they get tuned.


## v0.9.0 (2026-07-25)

Round 7 of FEEDBACK_CHECKLIST.md: the filmstrip past-the-first-screenful glitch.

- The strip no longer builds an <img> per item up front (which flooded the engine w/ thumbnail generations after the v0.8.0 cache flush & starved everything past the visible twelve). Slot buttons keep exact geometry for every index; images materialize in a window around the current item & follow panning; centering is arithmetic scrollTo on the 58px stride; the first sync snaps instead of animating.

Verified here: 23 pytest, ruff, tsc strict, 10 vitest, production build. Frontend-only change, but re-run ./build_macos_app so the bundled dist updates.


## v0.8.0 (2026-07-25)

Round 6 of FEEDBACK_CHECKLIST.md: two lingering symptoms, both mine.

- Video posters: THUMB_VER 2 -> 3 evicts every cache file incl the placeholders v0.6.0 wrote onto real paths (which the existence check kept returning forever, defeating v0.7.0's fixes). Thumbs regenerate lazily on first view; successful extraction also deletes its stale placeholder sibling.
- Selection visibility: selected-outline sync existed only inside the Library grid; bindSelectionClasses() is now exported & wired w/ teardown into the person-page, Hidden, Search & album-detail grids.

Verified here: 23 pytest, ruff, tsc strict, 10 vitest, production build. Requires the engine re-freeze (./build_macos_app). Awaits the Mac: real first frames after the one-time regeneration pass; outlines when selecting on a person page.


## v0.7.0 (2026-07-25)

Round 5 of FEEDBACK_CHECKLIST.md: 11 items, two root causes doing most of the damage.

- Launchd PATH: Finder-launched apps never saw Homebrew, so ffmpeg & tesseract were invisible to the packaged engine. Tool discovery now checks brew prefixes itself; first-frame posters & OCR work w/o PATH surgery, & failed extractions no longer poison the thumb cache (placeholders live beside, not on, the real path; imports pre-warm video posters).
- Interaction fixes: chunked fragment-based grid appends w/ early prefetch (smooth pagination); filmstrip steps one item per wheel gesture; single selection bar w/ contextual actions (person-page overlap gone); pinch-to-open & pinch-to-close the viewer; album drag un-broken (the v0.5.0 global drag suppression had disabled it: draggable tiles now opt out); vault auto-locks on leaving Trash/Hidden; the unlock dialog can save the passkey to Keychain for Touch ID; accordion chevrons follow > closed / v open, & the Albums page list collapses.

Verified here: 23 pytest, ruff, tsc strict, 10 vitest, production build. Awaits the Mac: brew discovery on a real machine, drag feel, pinch gesture thresholds, Keychain write & Touch ID chain.


## v0.6.0 (2026-07-25)

Round 4 of FEEDBACK_CHECKLIST.md: 20 items. Highlights:

- Cold start: engine frozen --onedir (no more per-launch extraction), spawned Rust-side from bundle resources; instant window w/ bundled splash that hands off to the UI on the engine's port line.
- People correctness: hidden media excluded from person pages; rebuild preserves NAMED people via exemplar anchors (named_preserved in the response); media-level reassignment moves face crops w/ the images; People search; faces strip serves 120.
- Native shell: real macOS menubar (App w/ Settings... Cmd+comma, full Edit menu enabling clipboard shortcuts, Window menu) & a single biometric_auth command (LAContext) so vault unlock prompts Touch ID before falling back to the passkey.
- Grid & layout: shared zoom (96-512) across Library/person/Hidden/Search/albums, tile corner-radius slider, static day headers, full-row empty states, left-aligned count-card labels, visible context-menu backdrop, glass presets incl Max glass, sidebar as a fixed glass overlay w/ carousels sliding beneath it.
- Albums & viewer: drag-to-arrange w/ persisted manual order + per-album sort; Library Newest/Oldest w/ bidirectional keyset pagination; persistent, draggable viewer filmstrip.
- Media: first-frame video posters w/ cache-busted names & a generated fallback poster (broken-img states hidden); /health reports ffmpeg.

Verified here: 23 pytest, ruff, tsc strict, 10 vitest, production build. Awaits the Mac: cold-start stopwatch, menubar rendering, Touch ID prompt, Rust compile of the LAContext path, splash-to-UI handoff, drag feel.

Corrections owned this turn (also in the checklist): the v0.4.0 first-frame/THUMB_VER claims were false (edits had silently no-opped); sort-param & schema edit misses were caught by the new mandatory anchor assertions before shipping; lastrowid-vs-rowcount bug fixed w/ exn().


## v0.5.0 (2026-07-25)

Desktop-native feel turn (Round 3 of FEEDBACK_CHECKLIST.md; routed through the tauri-ux-intuitive doctrine).

- Browser-chrome purge: default context menu suppressed app-wide (editable fields keep paste); autofill/autocorrect/spellcheck & search-cancel chrome stripped from every input; image/link drag-ghosts disabled; chrome is user-select none w/ correct cursor semantics while copyable content (paths, info values) stays selectable.
- Whole-window bounce killed: html/body can no longer scroll & every internal scroller contains overscroll, so gestures over non-scrolling areas move nothing.
- Under-glass layout: topbars float over their scrollers (absolute, z-20) & content passes beneath w/ real backdrop blur; day headers stick just below the bar; the viewer gained a filmstrip carousel (wheel-scrollable, current thumb centered & ringed) w/ glass caps that blur thumbnails sliding under the edges, per the Photos reference.
- In-app right-click: a glass context-menu component wired to tiles, person cards & album cards, reusing the same flows as the visible controls (incl. an extracted addToAlbumFlow).
- Honesty item: v0.4.0's Library marquee claim was false; the wiring had silently no-opped on a mismatched string. Now genuinely attached (assertion-guarded) & disposed on teardown; correction recorded in the checklist & the frontend HASHOUT log.

Verified here: 17 pytest, ruff, tsc strict, 10 vitest, production build. Awaits the Mac: the under-glass feel, bounce absence, & context menus in the shell (webview behaviors are consistent, but feel is a hardware check).


## v0.4.0 (2026-07-25)

Accountability turn. Round 2 feedback showed several v0.3.0 items were wrong or invisible in real use; FEEDBACK_CHECKLIST.md now tracks every item from both rounds & is the authoritative status list. Summary of what changed here:

- Background: the vendored kit's cells pattern always drew squares (the hexagon custom shape only curved the pointer field). Extended the module w/ a real honeycomb lattice (0.866 row offset) & pointy-top rounded-hex glyphs, hollow, accent-colored. Module-source assertions verify the lattice paths ship.
- Liquid glass made real: sidebar & topbars are now token-driven glass (backdrop blur/saturate/brightness, tinted translucency, rim gradients) over the animated background; defaults raised; the six sliders visibly transform the UI. Day headers lost the gradient bar: text + count only, w/ a legibility shadow.
- Video posters: first frame (0.5s fallback), THUMB_VER=2 cache bust regenerates stale thumbs, bottom-left video mark on tiles.
- Marquee drag-select on Library & People; People Select hardened (check dots, Select All/None, Esc, count bar).
- Faces: Reassign mode on the person page moves picked crops to an existing or new person. Matching accuracy: default threshold 0.55, exemplar verification against each person's 10 best crops, low-quality faces cannot found new people, & Rebuild groups re-clusters stored embeddings at a chosen strictness in seconds.
- Search: scope chips (Filenames / Text in image / People / Albums) persisted, backend fields param, OCR card w/ Scan text in N items + progress, & auto-OCR after every import when tesseract is present.
- Back buttons on every non-root page. Empty-state centering audited everywhere (Trash & Albums were the round 2 misses).

Verified here: 17 pytest, ruff, tsc strict, 10 vitest, production build; hex lattice source assertions; scoped-search & rebuild covered by new tests. Awaits the Mac: glass & vibrancy feel after bundling, marquee feel at scale, Keychain prompts.


## v0.3.0 (2026-07-25)

Feedback wave: every item from the first real-usage list on the Mac, mapped one-to-one.

### Delivered, per feedback item

- People hide/delete/merge: select mode on the People page (Select, then click cards) w/ a Merge / Hide / Remove action bar; Merge opens a keep-which picker & moves all faces; Remove unassigns faces & deletes the group; hidden people stay queryable w/ include_hidden.
- Double-click rename: the person title is inline-editable on dblclick (Enter saves, Esc cancels, blur saves).
- Back from person to people: back arrow in the person header.
- Click-away exits fullscreen: clicking the viewer backdrop (outside the media) closes it.
- Screenshot misclassification: PNG-w/o-EXIF alone no longer marks a screenshot; it now also requires exact screen dimensions from a curated Mac/iPhone/iPad set (rotations included), or the classic screenshot filename. A one-time startup pass reclassifies the existing library (settings key classify_ver).
- Passkey & fingerprint: the vault passkey can be stored in the macOS Keychain from Settings (security CLI: add-generic-password / find-generic-password) & unlocked from it; Keychain access control is where Touch ID prompts come from on macOS. A native in-app LAContext Touch ID sheet needs the signed desktop build & is the recorded next step, not silently claimed.
- Search & organization: topbar search (Enter routes to a results page) matching filenames, album names, people names & OCR text; Collections gained full Customize (below).
- Video thumbnails & hover play: poster thumbs come from ffmpeg (existing pipeline); tiles now play a muted looping preview on hover & stop on leave.
- Dominant-face recognition: faces under 0.4 percent of the frame are ignored; clustering centroids are quality-weighted; the person cover is the highest quality-x-size face, recomputed on every change.
- Hidden scrollbars: globally hidden (scrollbar-width none + webkit) while scrolling stays fully functional.
- OCR text search: services/ocrsvc.py shells out to tesseract when it is on PATH (tier-1 external binary, like ffmpeg); Scan fills media.ocr_text for images & video posters; search matches it. Proven end-to-end in-container: an imported sign image was found via its rendered text.
- Real liquid glass: the shell window is now transparent w/ the UnderWindowBackground material on macOS (macOSPrivateApi + macos-private-api feature pair), & Settings gained a Native window translucency toggle that lets the vibrancy show through the UI. Untestable in this container; the known field bug (transparency lost in some bundled DMG installs) is recorded as an on-device check.
- Hidden photos behind the passkey: first-class hidden tier w/ hide from the viewer & selection bar, a vault-gated Hidden page (Utilities, w/ lock) w/ per-tile Unhide, & hidden items excluded from Library, search, People, Collections & Duplicates everywhere.
- Import system picker: exactly the deduplakit pair, vendored: Choose Folder... opens the REAL OS dialog (osascript on macOS w/ package contents shown, PowerShell on Windows, zenity/kdialog on Linux) via the backend, & Browse opens the in-app server-side folder browser (roots incl. Photos Library originals, package-aware, Full Disk Access guidance on EPERM).
- Full deduplakit scan capabilities: kind filter chips (All / Exact / Visual), include-videos toggle, auto-resolve-exact-during-scan toggle, per-member Keep this one (keeper override) & per-member Trash, per-set & total reclaimable bytes.
- Import copy/move honesty: the page states plainly that files are COPIED by default & originals stay untouched (Move relocates); the completion toast says Copied/Moved & originals left in place accordingly. The prior behavior was always copy-by-default; the text now says so unambiguously.
- Library location & database visibility: Settings shows the live Library / Database / Models paths from /health (the desktop app resolves to ~/Library/Application Support/DAMp/library w/ damp.db inside; dev mode shows the repo library). The SQL db has always been real; now the path is one click away.
- Collections reorder & customize: Customize mode w/ drag-handle reordering & per-section show/hide, persisted server-side (/prefs/collections) so it follows the library, not the browser.
- Centered empty states: every empty card now centers in its container (empty-center wrapper) instead of hugging the top-left.
- People multi-select: covered above; marquee drag-select specifically is not in this build (click multi-select shipped) & stays on the list.
- Face-crop training database: every face keeps its embedding & quality; centroids are quality-weighted so good crops steer matching; the person page shows the best-crops strip where any wrong face can be unassigned (empty people auto-remove, covers recompute) · corrections directly improve future scans, & accuracy grows w/ the library.
- Settings & theming: gear in the sidebar foot opens Settings: 6 accent swatches + a custom color picker driving --accent & derived glow/soft/accent-2 (icons & the background follow via currentColor/--accent), six liquid-glass sliders (Strength / Blur / Frost / Tint / Gradient / Opacity) mapped to the glass tokens, & the interactive background restored from the deduplakit kit configured as hollow hexagons w/ slightly rounded corners in the accent color (orange by default), pointer-reactive, toggleable.

### Verified here

- Backend: 15 pytest green (incl. new hidden/search/screenshot-dims/people-ops/dedup-member/fs-prefs tests), ruff clean.
- Frontend: tsc strict clean, 10 vitest green, production build clean.
- Full-stack smoke (single-cell, real server): screenshot dims gate, search, hide -> vault 401 -> unlock -> unhide, fs roots/browse, prefs roundtrip, dedup scan w/ options + reclaimable + member trash resolving the set, & OCR proven by finding an image via its rendered text.

### Awaits your Mac

- Vibrancy look after bundling (incl. the DMG transparency field bug), Keychain enable/unlock prompts, the native folder dialog feel, hover previews at library scale, & everything from the v0.2.0 desktop list (freeze, cargo build, quit-kills-engine).


## v0.2.1 (2026-07-25)

Security patch: npm audit reported 5 vulnerabilities in the frontend toolchain (all devDependencies; nothing DAMp ships at runtime uses npm packages). Root causes: vitest 2.1.x CRITICAL (UI server allows arbitrary file read & execute), vite 5.4.x HIGH (path traversal in optimized-deps .map handling + launch-editor NTLMv2 hash disclosure), & three moderates chained through esbuild <=0.24.2 / vite-node / @vitest/mocker.

Fix: major-bumped the toolchain to current stable · vite ^8.1.5, vitest ^4.1.10, jsdom ^29.1.1 (typescript stays on its clean ^5 line) · regenerated package-lock.json from scratch so installs resolve the patched tree deterministically. `npm audit`: 0 vulnerabilities.

Verified here: tsc strict clean, 10 vitest green, production build clean on the new majors (no API breakage in configs or tests). Versions locked at 0.2.1 across config.py, package.json, Cargo.toml, tauri.conf.json, & the zip.


## v0.2.0 (2026-07-25)

Desktopization turn: the macOS shell, the frozen-engine pipeline, & the canonical app icon.

### Delivered

- Canonical icon: the user-provided 1024 RGBA mark adopted verbatim as `src-tauri/icons/icon.png` (macOS icon source for `cargo tauri icon`), web favicon, & sidebar brand; the v0.1.0 Claude-composed diamond SVG/PNG removed (composition preserved in the frontend HASHOUT log).
- `src-tauri/` shell (deduplakit-proven shape): schema-2 config w/ no declarative windows, sidecar `binaries/damp-backend`, identifier `ai.nodemode.damp`, min macOS 12; Rust main spawns the engine w/ `DAMP_PORT=0`, parses the bind line from stdout+stderr, opens the webview at the loopback URL sized to 90 percent of the primary monitor, shows a native failure dialog if no port appears, & kills the child on exit; capabilities are exactly core, dialog, & the scoped sidecar execute.
- `backend/desktop_entry.py`: PyInstaller entry w/ `--selfcheck` JSON (Pillow/numpy/cv2/pillow_heif, app version, bundled dist & models), env defaults pointing DAMP_DIST/DAMP_MODELS into the frozen bundle, & DAMP_LIBRARY defaulting to the platform app-data dir; `app/main.py` now honors DAMP_DIST.
- `build_macos_app` one-command pipeline: prereq checks, sha256-verified model fetch, frontend build, PyInstaller onefile freeze (`--collect-all` uvicorn/PIL/pillow_heif/cv2/numpy, dist + models embedded) gated on selfcheck, triple-suffixed sidecar placement, `cargo tauri icon`, `cargo tauri build`, unsigned-launch instructions.
- `requirements_macos.txt` (unpinned freeze set) + darwin branch in `backend/oc_install`; `.gitignore` covers target/, binaries/, freeze artifacts, generated icon sets.
- Version foot in the sidebar fed by /api/health; versions locked at 0.2.0 across config.py, package.json, Cargo.toml, tauri.conf.json, & the zip.
- LICENSES.md ledger: bundle vs build-time vs tier-1 external classes, PyInstaller bootloader-exception note, pillow-heif LGPL separability decision, ffmpeg kept a user-supplied PATH binary, capability-to-feature map.

### Verified here

- Backend: 9 pytest green, ruff clean (desktop_entry + main.py edits covered); `python3 desktop_entry.py --selfcheck` prints the full JSON w/ every dependency importable & models_bundled true against the repo layout.
- Frontend: tsc strict clean, 10 vitest green, production build clean w/ the PNG favicon & version foot.
- Icon source: 1024x1024 RGBA, transparent corners confirmed, exactly what `cargo tauri icon` expects; used unmodified.

### Awaits your Mac (cannot run in this Linux container)

- The PyInstaller freeze itself (PyInstaller freezes for its host OS), the frozen `--selfcheck`, `cargo tauri icon`, the Rust compile, `.app`/`.dmg` bundling, first-launch quarantine flow, & the quit-kills-engine check (`pgrep -f damp-backend` empty after quit). The pipeline is `./build_macos_app`; every step prints its own gate.


## v0.1.0 (2026-07-25)

First dev-build of the open-source Photos.app-style library manager, modeled on the provided macOS Photos screenshots.

### Delivered

- SQLite catalog (WAL, thread-local connections) at `<library>/damp.db`; managed originals under `library/originals/YYYY/MM` w/ collision uniquifying.
- Import pipeline: recursive gather, full SHA-256, exact-duplicate skip on (sha256, size), EXIF / ffprobe capture-time extraction w/ filesystem fallback, screenshot & screen-recording heuristics.
- Media API: keyset-cursor paging, nine filters, month/year summaries w/ cover ids, favorite / viewed / trash mutations, bucketed JPEG thumbnails (192/384/768, Pillow draft + ffmpeg poster frames), byte-range video streaming (206/416).
- Albums w/ covers, rename, delete; private albums w/ per-album scrypt passkeys, vault fallback, 30-minute HMAC unlock tokens, & a `media.private` flag that removes items from every general query (library, filters, summaries, People, Duplicates).
- Vault: single scrypt passkey guarding Recently Deleted + private-album fallback; trash is DB state w/ per-item days-left, restore, delete-forever (unlink + row cleanup), empty, & startup purge past retention.
- People: YuNet detection (score 0.72, max edge 1024) + SFace 128-d normalized embeddings; incremental centroid clustering at cosine 0.42 (env-tunable); videos sampled at the deduplakit timestamps scaled to 640 w; face crop thumbnails; rename; status endpoint reporting cv2/models/ffmpeg readiness.
- Duplicates: vendored deduplakit visual core (dual-gradient 128-bit dHash, confidence-masked DCT pHash, 4x4 color grid, weights .42/.38/.20, default 94 floor 58) + exact sets from the catalog; aspect-bucketed clustering w/ keeper verification & one recluster pass; resolve keeps best (pixels, size, age) & trashes the rest w/ reason `duplicate:<set>`; resolve-all-exact.
- Jobs: single-thread background runner w/ per-job counts for import, dedup, & face scans.
- Security: loopback-only middleware, Host allowlist, mutation header, vault header; tokens carry scope + expiry, vault scope opens everything.
- Identity: named DAMp; app icon composed from the DAMp monogram artwork w/ a layered orange neon glow (feFlood/feGaussianBlur/feMerge) on a 45-degree rotated rounded black diamond; shipped as SVG + 512 PNG in frontend/public, wired as favicon & sidebar brand mark.
- Frontend: vanilla TS + Vite on the vendored theme kit (accent re-cut to DAMp amber); sidebar w/ Pinned / Albums / Utilities incl. lock badges; Library topbar (Years / Months / All segmented control, zoom slider, filter menu); day-grouped grid w/ sticky headers, badges, durations, hover multi-select; month/year cover cards; lightbox viewer (thumb-to-full swap, video element, info panel, favorite, download, trash, arrows & keys); selection bar w/ Add to Album (401-aware unlock retry) & Delete; Collections page (Recent Days, People, Albums strips + Media Types & Utilities counts + honest empty states for Memories / Trips / Shared); People pages w/ scan progress banner; vault-gated trash list; Duplicates page w/ threshold slider & per-set resolve; Import page w/ job progress.

### Verified here

- Backend: 9 pytest green (import/filters/thumb/range, private-album flow incl. vault-scope token, trash lifecycle incl. permanent unlink, dedup end-to-end w/ resolve + trash reason, faces status & scan on faceless fixtures); ruff clean.
- Face engine: YuNet + SFace load, detector returns 0 on noise, SFace emits 128-d embeddings; models sha256-pinned in the installer.
- Frontend: tsc strict clean, 10 vitest green (format, store routing/cursors/selection, api token precedence), vite production build clean.
- Full-stack smoke: real uvicorn + built UI; imported 3 photos + 1 ffmpeg-generated video; video poster thumbnail rendered; ranged video request answered 206; dedup scan found the resized-export pair (keeper = larger, 100%); people status ready; UI served at `/`.

### Known gaps & honest notes

- Real-face clustering quality is untested in this container (no real faces available); the pipeline is mechanically verified & awaits your library. Threshold 0.42 is deliberately stricter than the SFace paper's 0.363 to favor precision for centroid matching; tune via `DAMP_FACE_THRESHOLD`.
- Not built yet: Map view, editing, sharing / shared albums, Memories / Featured / Trips content, the ML classifiers behind Receipts / Handwriting / Illustrations / Documents, Live Photos / Portrait / Bursts / Panoramas / Selfies / Cinematic detection, keyword manager UI (tables exist, no API), iCloud anything.
- Dedup signatures are recomputed per scan (not persisted yet); fine at thousands of items, a cache lands in a later build.
- People: no merge / split / recluster controls yet; incremental assignment only.
- HEIC decoding needs pillow-heif (installed by the dev requirements); w/o it HEIC files import but skip face scanning.
- Trash purge runs at startup; a long-running server does not purge mid-flight until restarted.
- Desktop packaging (Tauri shell) is the planned next milestone; this build is the web dev-build.

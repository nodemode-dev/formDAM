# backend HASHOUT_LOG · formDAM
current: v1.27.2 · 2026-10-22
### services/filesvc.py rename · a sidecar is moved only when it is this file's and the new name is free
- refers-to: filesvc rename (the sidecar loop after os.rename)
- kind: fix
- logged: v1.28.9 · 2026-11-11

Renaming a file moved IMG_1.xmp to the new name even when IMG_1.CR2 sat beside the JPEG and the sidecar was the RAW's, and os.rename silently replaced an existing b.xmp when a.jpg became b.jpg (POSIX rename overwrites). A sidecar of the form IMG_1.JPG.xmp is still moved, since it can only be this file's; the IMG_1.xmp form is left in place when another file in the folder still has the stem IMG_1 (any extension but .xmp, so an unimported RAW counts); and nothing is moved when the target sidecar already exists. The renamed file then simply has no sidecar beside it, which import and Read Sidecars handle. Checked with a scratch run on a referenced folder: renaming the JPEG of a RAW+JPEG pair leaves IMG_1.xmp; renaming a.jpg to b.jpg leaves an existing b.xmp untouched (a.xmp stays); a lone c.jpg renamed to cc.jpg takes c.xmp to cc.xmp.

### services/query.py parse_date_range · date-like text that is not a real date is searched as text
- refers-to: query parse_date_range (now a wrapper), _parse_date_range (the former body, unchanged)
- kind: fix
- logged: v1.28.9 · 2026-11-11

The regex branches built datetime() without checking ranges, so search text such as 2024-13, 2023-45, 0000-01 or 2024-02-30 (file name fragments often look like this), or a smart album date rule holding one, raised ValueError and the search, the album count or Discover answered 500; on Windows a bare year before 1970 raised OSError from timestamp(). The body moved unchanged into _parse_date_range, and parse_date_range returns None when it raises ValueError, OverflowError or OSError, so the text falls back to the plain LIKE search. Checked with a scratch run: the four strings above and 9999-12 give None and text_sql builds a clause; 2024-02-03 and 2024-02 still parse.

### routers/trash.py bio_unlock · device unlock is for the window, and fails when the vault key does not open
- refers-to: trash bio_unlock (window_allowed or shell_allowed first; unlock_vault's result checked); keychain_enable unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

bio_unlock sat behind the general automation gate only, so an agent with an automation token could raise the system Touch ID, Windows Hello or polkit prompt, with nothing saying a script asked, and receive a full vault token if the user approved; every other unlock needs the passkey, and the Privacy pane promises token holders cannot raise their own access. It now answers 403 unless the request comes from the window (session cookie) or the shell. It also ignored unlock_vault's result and issued a vault token even when the stored key could not be unwrapped; it now answers 500 with the message vault_unlock already gives. keychain_enable is left as is: it needs the passkey itself. Checked with a scratch run: with FORMDAM_AUTOMATION=1 and no window cookie the route answers 403; test_bio_channel (window cookie) passes.

### routers/edit.py export_trim · protected videos are refused and the temporary folder always goes
- refers-to: edit export_trim (the vault check after the trim check; shutil.rmtree in a finally around ffmpeg and the import)
- kind: fix
- logged: v1.28.9 · 2026-11-11

Export Trim on a hidden or private video pointed ffmpeg at the library path the vault had already emptied, so it answered 500 "ffmpeg could not write the clip" (and, had the plaintext been there, would have imported the clip as an ordinary visible item). It now answers 409 "Protected items stay inside the vault", as edit_with does. The dam-trim-* folder was removed with os.rmdir only after a successful import, so a failed ffmpeg run or a clip that was already in the library left it and the clip in the temp folder; it is now removed with shutil.rmtree in a finally. Checked with a scratch run: a trim export answers 200; a second one of the same clip answers 409 (duplicate) and leaves no dam-trim folder; a hidden video answers 409 with the vault message.

### routers/geo.py location and date routes + edit.py paste_edits · hidden, private and trashed items need the vault like everywhere else
- refers-to: geo _check, set_location (ids and copy_from), location_hidden, adjust_dates; edit paste_edits (every row checked before any write)
- kind: fix
- logged: v1.28.9 · 2026-11-11

These four routes never called ensure_visible, so without a vault or album token a caller could read a hidden, private or trashed item's coordinates and place names (POST /media/location with copy_from set to it), and move or clear its location, hide its location, change its capture date or overwrite its edit, which organize, output, files and the single-item edit routes all refuse with 401. Each now checks every id (and copy_from) with ensure_visible before writing anything; paste_edits checks all rows first, so a refused id leaves the others untouched. A missing id in the geo routes now answers 404 as in output's _check (paste_edits still skips it). Checked with a scratch run: each route answers 401 for a trashed item without a token and writes nothing, and answers 200 for a visible item.

### services/thumbs.py ensure_thumb · thumbnails appear whole or not at all
- refers-to: thumbs ensure_thumb (image and video branches), _placeholder_poster, _discard
- kind: fix
- logged: v1.28.9 · 2026-11-11

ensure_thumb saved the WebP straight to its final path and treats an existing file as done, so right after an import, when the grid and the CLIP, Look Up and OCR jobs ask for the same thumbnail, one thread could serve another's half-written file, two could write it at once, and a crash mid-save left a truncated thumbnail that was served for good. For videos every thread shared <out>.frame.jpg as ffmpeg's output, and a thread whose attempt failed deleted <out> that another had just finished. Each save now goes to <out>.<random>.tmp and is moved into place with os.replace (atomic on one volume), the ffmpeg frame name carries the same random token, and the failure cleanup removes only this call's frame and temporary file, never <out>. The placeholder poster is written the same way. A crash can leave a stray .tmp file, which nothing serves and which the vault's per-id scrub removes. Checked with a scratch run: 8 threads, 3 rounds each, on a new 3000x2000 image and 6 threads on a new video all returned thumbnails that PIL loads fully, with no .tmp or frame file left.

### routers/importer.py import_upload · a drag-and-drop import runs in the thread pool
- refers-to: importer import_upload (async def to def); the body unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

import_upload was the one coroutine endpoint, so the copy, hashing, metadata read, database writes and the synchronous ffmpeg poster for a dropped video all ran on uvicorn's single event loop thread, and every other request (thumbnails, job polls, /api/health) waited until the whole drop was imported. It is now a plain def like every other route, which FastAPI runs in its thread pool; UploadFile.file is an ordinary file object, and the import batch is a thread-local that is set and cleared inside the same call. Checked with a scratch run: a dropped JPEG imports and gets its batch id.

### services/syncsvc.py _apply_media · one object too large for the Shared Library no longer stops a device's journal for good
- refers-to: syncsvc SHARED_MAX, _apply_media (the missing-object branch); familynet.seal and unseal, familyserver and the personal channel unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

The Shared Library seals each object as one AES-GCM message, and AES-GCM in cryptography 50.0.1 refuses more than 2**31 - 1 bytes (OverflowError "Data or associated data too long", reproduced here with a lazily mapped 2 GiB buffer). A video of 2 GiB or more therefore never reaches the other device; _apply_media returned False for the missing object, pull stored the cursor at that line and stopped, and every later record from that device (shares, edits, removals) waited forever behind it. On the shared channel, a media record whose object is missing and whose declared size is over 2**31 - 1 is now skipped with a line in the engine log, so the journal moves on; the item itself still does not arrive. A missing object below that size still waits as before, since it may only be late. Deferred: carrying such objects at all needs chunked sealing (for example 16 MiB frames framed like vaultcrypt._encrypt_stream, streamed from disk on both sides), which changes the Shared Library's wire format between versions. Checked: the size limit by the call above; test_p1_lan passes. Not run: a pull with a real 2 GiB object.

### vaultcrypt.py _scrub and purge · sealing drops an item's rendered caches, and delete forever drops its Edit With files
- refers-to: vaultcrypt _scrub (cache/render, cache/effects and cache/share by "<id>_"), purge (library/edits and library/edits/work by "<id>-"); _protect and _unprotect unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

_scrub removed only thumbnails and face crops, so hiding, making private or trashing an item left plaintext copies beside the sealed original: rendered previews in cache/render/<id>_*, the Long Exposure still in cache/effects/<id>_le.png and the full video or photo copy a Web Gallery export cached in cache/share/<id>_*; and delete forever left those plus the item's Edit With results in library/edits/<id>-* and its working copies in library/edits/work/<id>-*. Because media ids can be reused after the newest item is purged, a new import could even show the deleted photo's cached Long Exposure. _scrub (run on seal and on purge) now also removes the three caches by "<id>_", which are rebuilt from the original when needed; purge also removes the edits and work files by "<id>-" (the glob needs the dash, so id 12 never matches 123). Deferred: the Edit With result of an item that is sealed but not deleted stays in plaintext in library/edits until delete forever; removing it on seal would lose the user's edit, and the full fix is to encrypt it into the vault blob with the item's content key in _protect (as _blob(blob, ".e")) and write it back in _unprotect, which changes the vault layout. Checked with a scratch run: delete forever of a trashed item removed its edits, work, effects, share and render files and kept a file of id <id>0; test_trash and test_vault_private pass.

### routers/trash.py POST /vault/lock · the window can drop the vault cookie when it locks
- refers-to: trash vault_lock; vaultcrypt.token_response, VAULT_COOKIE, COOKIE_PATH and the 30-minute token unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

Unlocking sets an HttpOnly dam_vt cookie on /api/media holding the vault token (30 minutes), so img and video tags can load hidden and trashed items. The window's re-lock on leaving Hidden or Recently Deleted only forgets its in-memory token, and there was no route to clear the cookie, so those items' thumb, file and render URLs kept answering for the rest of the half hour. POST /api/vault/lock now answers with the same cookie expired (Max-Age=0, same path, HttpOnly, SameSite=Strict). It does not revoke the token itself (tokens are stateless HMACs) and does not change the vault key's unlocked state. The window must call it when it re-locks; that call is in frontend/, outside this fixer's area, and is listed for the owner. Checked with a scratch run: after setup the cookie opens a trashed item's /file (200); after POST /vault/lock the cookie is gone and /file answers 401.

### routers/edit.py preview and put_edits · an Edit With file is only used for the item it belongs to
- refers-to: edit router preview (the external path is kept only when it equals the stored one), put_edits (state "external" replaced by the stored one when the file differs); extedit.external_path, _store, _adopt and package open unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

extedit.external_path takes the basename the client names and only checks the file exists in library/edits, and names are <media id>-<unix seconds>-<n>.<ext>, so they can be probed. A preview of any visible item with another item's external file name showed that file (the full Edit With result of a hidden or private photo, which the vault does not seal), and PUT /edits stored the name so /render served it from then on (and DELETE /edits would unlink it). preview now uses the client's external file only when it is the one stored for that item; put_edits keeps the client's "external" only when its file is the stored one, and otherwise puts the stored value back (none drops it), so a stale editor cannot drop a newer Edit With result either. Edit With adoption and package open still set it through _store. Checked with a scratch run: previewing item A with item B's external name shows A; B's own preview shows its external file; a PUT on A with B's name stores no external, on B keeps it.

### routers/library.py switch_library + jobs.any_running · no job of any kind may be running when the library switches
- refers-to: jobs any_running; library switch_library busy
- kind: fix + replaced code
- logged: v1.28.9 · 2026-11-11

Replaced: a fixed tuple of twelve job kinds (import, metadata, places, clip, faces, ocr, export, xmp, workflow, repair, memories, copy). consolidate, dedup, package, package-open, gallery, lookup and idevice-import were missing, and db.connect() follows FORMDAM_LIBRARY at once, so a consolidate job (with move, files moved out of the user's folders) or a dedup scan kept running against the new library with the old library's ids. jobs.any_running lists the kind of every job still in the running phase, and the switch answers 409 naming them while any is. Every job in this tree finishes on its own, so none can hold the switch for good. Checked with a scratch run: a running consolidate job makes the switch answer 409 naming it; test_p1_package (which switches libraries) passes.

### services/dedupsvc.py resolve + routers/dedup.py · a duplicate set is never resolved around a keeper that is trashed or not in the set
- refers-to: dedupsvc resolve (the keeper check before anything is trashed); dedup router dedup_resolve 409; list_sets and resolve_all_exact unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

resolve took keep_media_id (or the stored keeper) without checking it. After a scan, trashing the keeper from the grid left the set listed (its members are live), and "Keep best, trash the rest" then trashed every member too, so all copies sat in the Trash until the purge; a keep_media_id outside the set trashed the whole set and recorded an unrelated item as keeper. resolve now returns an error and trashes nothing unless the keeper is the set's keeper or one of its members and is not in the Trash; the route answers 409 with that message. A set whose stored keeper is trashed stays listed, so "Keep this one" on a member still resolves it. resolve_all_exact skips such a set. Checked with a scratch run: with the keeper trashed, resolve answers 409 and the member stays live; an outside keep_media_id answers 409; keeping the member answers 200 and trashes nothing. test_dedup passes. The window's two resolve buttons do not catch the error yet (frontend, outside this fixer's area), so the 409 shows nothing on screen.

### ffmpeg_fetch.py _download · the first-run ffmpeg download uses the standard library
- refers-to: ffmpeg_fetch _download; source, _install, fetch and the pins unchanged
- kind: fix + replaced code
- logged: v1.28.9 · 2026-11-11

Replaced: import httpx and an httpx.stream GET with follow_redirects. httpx is only in requirements-dev.txt and requirements-test.txt, and nothing in requirements.txt or requirements_macos.txt pulls it in, so every packaged engine failed the background fetch with "No module named 'httpx'" (logged only as a warning) and never placed ffmpeg; the 1.28.4 check passed because the dev venv has httpx. _download now uses urllib.request.urlopen (follows the GitHub redirect, raises on an HTTP error) and copies the body in 1 MiB blocks; no dependency added. On macOS the TLS context also loads /etc/ssl/cert.pem, the system root bundle, because a frozen python.org-style OpenSSL may have no default CA file there; the archive's files are still checked against the SHA-256 pins before anything is installed. Checked on Linux with the system Python (no httpx installed), through this machine's proxy CA: the real Linux archive downloaded (12.2 MB), fetch() into a temporary XDG_DATA_HOME passed the pins and placed ffmpeg and ffprobe, and a wrong URL raised HTTPError 404. Not run: a frozen engine, macOS, Windows.

### routers/trash.py and importer.py /internal/* · only the desktop shell may call the shell routes
- refers-to: trash _shell_only, shell_hello, bio_pending, bio_result; importer shell_glass; tests/test_bio_channel SHELL headers
- kind: fix
- logged: v1.28.9 · 2026-11-11

The /api/internal/* routes passed the general automation gate only, so a window page or an automation token could call them. Turning on "save passkey to the Keychain" (Windows Hello, keyring) keeps the passkey in PENDING under a nonce and prints FORMDAM-CTRL KCSTORE <nonce> on stdout, which the frozen engine tees into engine.log; anyone reading that log with API access could fetch /internal/bio/pending/<nonce> and get the passkey in clear, post a false /internal/bio/result to cancel an unlock, or claim a shell is attached. Each of the four routes now answers 403 unless the request carries the shell key (security.shell_allowed), which src-tauri's engine_post and engine_get always send. The nonce still reaches the log, but it no longer opens anything without the shell key. test_bio_channel posted to these routes with the window's headers only; its internal calls now send x-dam-shell as the shell does (no assertion changed). Checked: a scratch run shows the four routes answer 403 with the window cookie and 404/200 with the shell key; test_bio_channel and test_f1_guard pass.

### services/xmpsvc.py write_sidecar · a sidecar formDAM did not write is left alone, and a RAW+JPEG pair gets one sidecar each
- refers-to: xmpsvc write_sidecar (the same-stem lookup and the check of an existing file before the write); sidecar_for, find_sidecar, sidecar_job unchanged
- kind: fix
- logged: v1.28.9 · 2026-11-11

write_sidecar replaced IMG_1.xmp unconditionally. For a folder imported by reference that already held a sidecar from another app (develop settings, history), turning on sidecars, "Write sidecars" or a workflow sidecar step replaced it with a packet built from formDAM's fields only; and a RAW and a JPEG with the same stem in one folder wrote the same IMG_1.xmp, so the last one won. Now, when another media row has the same path up to its extension, this item's sidecar is IMG_1.CR2.xmp (the form find_sidecar already reads); and when the sidecar file exists and its first 64 KB do not carry x:xmptk="FormDAM" (the marker build_xmp has always written), nothing is written and the item counts as skipped (sidecar_job marks it done so it is not retried every run). Not done, for the owner: merging formDAM's fields into a foreign sidecar (parse it, set rating, label, keywords and IPTC fields, keep every other node) so such items get their metadata out too; and a pair whose formDAM IMG_1.xmp was written before this change keeps that file, which find_sidecar still reads first on a later import. Checked with a scratch run on a referenced folder: a foreign a.xmp is left byte for byte and the call returns None; with it gone, a.xmp is written and rewritten; a.png beside a.jpg gives a.png.xmp and a.jpg.xmp; a_b.jpg beside a%b.jpg is not taken for a pair. test_p1_xmp passes.

### services/outputsvc.py export_one · an original or a video exported without location or metadata no longer carries it
- refers-to: outputsvc ExportError, _copy_stripped, the byte-copy branch of export_one, export_job's ExportError arm and state "failures"
- kind: fix
- logged: v1.28.9 · 2026-11-11

Every video, and every photo exported with "unmodified originals", was a byte copy of the library file, so "Include location" off, a hidden location and Metadata "None" were ignored: an iPhone video kept its ISO6709 location and a photo its EXIF GPS and XMP place. When any of the three applies, the branch now fails closed. A video goes through packagesvc._strip_video (ffmpeg, streams copied, all metadata and data tracks dropped; a vault item's bytes go through a temporary file beside the target that is removed); without ffmpeg, or when it fails, nothing is left at the target and the item fails with "location and metadata could not be removed from this video (ffmpeg is needed)". A photo is written through gpsscrub.scrub and kept only when gpsscrub.has_gps reads it as clean (or cannot read it and the row has no location), as packages do; otherwise it is removed and the item fails. Metadata "None" on an original photo fails with a message saying to export a rendered copy, since nothing here can strip all of a camera file's metadata without re-encoding it. Failed items are counted as skipped as before, and the messages are listed in the job's state under "failures" (the export toast still shows only the count). Checked with scratch runs: a GPS JPEG exported as an original with location off reads no GPS, with Metadata "None" is skipped with a message and leaves no file, and with the defaults still keeps its GPS; a .mov carrying location tags exported with location off shows no location in ffprobe.

### services/libraryfs.py import_one + iccsvc.run_import · a copy that is only in the Trash is not a reason to delete from the iPhone
- refers-to: libraryfs import_one (the duplicate query and its result's "trashed" key); iccsvc run_import (the statuses list that decides deletable)
- kind: fix
- logged: v1.28.9 · 2026-11-11

The duplicate check matched any row with the same sha256 and size, including one in Recently Deleted. An iPhone import with "delete after import" then counted that photo as safely in the library and deleted it from the phone, and the Trash purged the only copy 30 days later. import_one now reads trashed_ts with the match and returns "trashed": true when the matching row is in the Trash; run_import records such a result as "trashed", so an entry with one is counted as a duplicate as before but is not put on the delete list. Other callers (folder import, package open, sync pull) still read the status "duplicate" and are unchanged. Checked with a scratch run of the ICC fake bridge: import, trash, import again with delete after import deletes nothing; after restoring the row it deletes the key. test_icc and test_core pass.

### tests · family layers F1, F4, F5, F9 and the P1 gap fills for formDAM
- refers-to: backend/tests (conftest, support, test_f1_guard, test_f4_versions, test_f5_boot, test_f9_release_profiles, test_p1_originals, test_p1_xmp, test_p1_package, test_p1_lan), backend/requirements-test.txt
- kind: rationale
- logged: v1.28.1 · 2026-10-26

FAMILY_TEST_PLAN v0.3.0, section 5 gap fill. The older suite ran against a guard that had since gained the automation gate, so most of it answered 403; the client fixture now opens a window session with the launch key, as the window does, and the suite runs on a temporary library and config folder (a module-level default also keeps a background thread that outlives a test from writing to the repo's library folder). test_trash no longer expects a trashed original at its library path, because the vault seals it. Differences from the family template: no websocket (formDAM has none, so F1 checks the surface is absent), no engine.json and no /api/version (F5 reads /api/health and frontend/package.json), the version sites are the package.json and lock, Cargo.toml and Cargo.lock, and the guard has the launch key, window cookie and automation token layers that the F1 file checks as well. The LAN server (familyserver) is exercised through its own app with a private peer address and the family key signature; the real listener is only started to check it stops. Package tests switch to a second temporary library with FORMDAM_LIBRARY monkeypatched so the switch is undone. No bug was found, so no ledger number was used.

### security.local_only_guard · an Origin must be this app's own window
- refers-to: security WINDOW_ORIGINS, origin_key, window_origin and the check after the cross-site one in local_only_guard; MUTATING, OPEN_PATHS, the launch key and the automation gate unchanged
- kind: rationale
- logged: zip v1.27.9 · 2026-10-25

The family agent-stack standard, rule G2 (AGENT_STACK_STANDARD.md v0.2.0, ledger FB-036, formai_dev sidecar). The guard never judged an HTTP request's Origin, so a page on any site could send a simple GET with its own Origin and, on the open paths (/api/health, /api/session), be answered outright. A present Origin must now be one of the window's origins: the engine's own (an http origin whose scheme, host and port equal the request's Host, which is how the desktop window and the served build load), the dev window on 5173 and the preview window on 4173 (localhost and 127.0.0.1 each), tauri://localhost or http://tauri.localhost. The comparison parses scheme, host and port (origin_key, modelled on formpdf's) and never compares a prefix, so http://localhost.evil.com, http://localhost:5173.evil.com and null fail with 403 "Rejected foreign Origin". A request with no Origin is decided as before (rule G4). The launch key, the window cookie and the automation gate still decide who may use the API; this check only refuses. The guard is an http middleware only (formDAM has no websockets).

Checked on the running engine (port 9151, launch key set, the built window served through FORMDAM_DIST) with /api/health, /api/session and a missing route: Origin http://evil.example, http://localhost.evil.com, http://localhost:5173.evil.com and null 403; the engine's own origin (127.0.0.1 and localhost), http://localhost:5173, http://127.0.0.1:5173, http://localhost:4173, tauri://localhost, http://tauri.localhost and no Origin pass (200, 404 for the missing route); cross-site without an Origin and a foreign Host still 403; cross-site with the dev Origin 200. The built window opened with #dam-key= in Chromium at 4x CPU and slow network, two shift runs and one throttle run: layout shift 0, no errors, 0 refusals from the window (18 refusals in the log before and after, all from the probes above). formDAM has no MCP server in this tree.

### security.local_only_guard · a request with no Origin is refused when Sec-Fetch-Site says cross-site
- refers-to: security local_only_guard (the check after host_allowed), MUTATING, OPEN_PATHS unchanged
- kind: rationale
- logged: zip v1.27.8 · 2026-10-25

The family agent-stack standard, rule G4 (AGENT_STACK_STANDARD.md v0.2.0, owner decision D4, ledger FB-035, formai_dev sidecar). The guard let a request with no Origin through once its Host was loopback, so a web page could make the engine answer a GET by pointing an img or a link at http://127.0.0.1:<port>/..., since browsers send no Origin on those; the open paths (/api/health, /api/session) answer such a request outright. Browsers label every request with Sec-Fetch-Site and only a page on another site gets cross-site, so the guard now answers 403 "Rejected cross-site request" to a request with no Origin whose Sec-Fetch-Site is cross-site (trimmed, case-insensitive). A request that carries an Origin is decided as before, and same-site stays allowed on purpose: a dev window on localhost:5173 loading straight from localhost:8000 is same-site, and no outside page can be same-site with localhost. The CLI, scripts and MCP tools send neither header and pass; the automation gate is untouched and still never trusts Sec-Fetch-Site to admit anyone (this check only refuses). The guard is an http middleware only; browsers always send an Origin on a websocket.

Checked on the running engine (port 9122, launch key set) at /api/health: no Origin with cross-site and with "  Cross-Site " 403; same-site, same-origin, none, no header, and cross-site with the dev Origin http://localhost:5173 200; a foreign Host 403. An Origin of http://evil.example on a GET answers 200 as before: the guard has never judged an HTTP Origin (mutating calls need the x-dam-local header, other /api routes the window cookie or automation token). In Chromium, a page served from http://127.0.0.2:9903 with an img and a clicked link pointing at /api/health got 403 for both, shown in the engine log. The built window served by the engine (FORMDAM_DIST) opened with #dam-key= in Chromium at 4x CPU and slow network, two shift runs (one shift entry each, value 0) and one throttle run: layout shift 0, no errors, 0 refusals from the window (5 refusals in the log before and after, all from the probes above). formDAM has no MCP server of its own in this tree, so no MCP check was possible.
### config.py _build_version · the engine reports the build's own version
- refers-to: config _build_version, VERSION; build_macos_app, build_linux_app, build_windows_app.bat --add-data ../frontend/package.json:.
- kind: rationale + replaced code
- logged: zip v1.27.0 · 2026-10-20

Replaced: VERSION = "1.13.9", a literal held back by the owner's old rule that the app keep reporting 1.13.9 while the zip moved on (lifted 2026-10-20). frontend/package.json is now the one version of record; the engine reads it from the repo, or, frozen, from the copy PyInstaller places at the bundle root, and says 0.0.0 rather than a stale number if neither is there. /api/health, the FastAPI title and the sidebar foot all follow it.
### routers/trash.py device_labels, _method_cap, GET /vault/device · unlock names per OS
- refers-to: trash device_labels, _method_cap, device_unlock_labels; _ctrl_roundtrip not-attached and timeout details; keychain_enable and bio_unlock details
- kind: rationale
- logged: zip v1.26.0 · 2026-10-20

The engine runs on the same computer as the shell, so it names the unlock from sys.platform: Touch ID and the macOS Keychain, Windows Hello and Windows Credential Manager, system sign-in and the system keyring. The names come from their own endpoint because /vault/keychain/status keeps its exact two-key shape, which test_bio_channel pins.
### formDAM brand pass · config.env prefixes, FORMDAM_* reads, user-facing strings, the control-line tag
- refers-to: config ENV_PREFIX, LEGACY_ENV_PREFIXES, env; main lifespan launch address, FastAPI title, _dist via env("DIST"); security _LEGACY_KEY, _ENV_KEY, AUTOMATION_OFF, automation_allowed FORMDAM_AUTOMATION, local_only_guard detail; automation router _from_window, _state forced, session and automation details; library router FORMDAM_LIBRARY, formDAM Library default name, details; importer and trash FORMDAM-CTRL prints; desktop_entry FORMDAM_DIST/MODELS/LIBRARY/PORT, Logs/formDAM, thread names; iccsvc FormDAMICCDelegate; native_picker prompts; packagesvc, syncapi, familynet messages; jobs, housekeeping, syncsvc, familyserver, extedit thread names; .env.example
- kind: rationale
- logged: zip v1.25.0 · 2026-10-20

The product is formDAM, so every string a person reads, every environment variable and every thread name says so. config.env now tries FORMDAM_, then DAM_, then DAMP_, so an existing backend/.env or shell export keeps working; FORMDAM_AUTOMATION is read only under its own name, because it opens the API to any local program and an old variable left in a profile should not do that silently. The launch key is popped under both names so neither reaches child processes. The control lines to the shell are tagged FORMDAM-CTRL, changed together w/ src-tauri/src/main.rs. Deliberately unchanged, because they are stored or exchanged formats and renaming them would orphan data or break older peers: dam.db and damp.db, the Application Support/DAM, %APPDATA%/DAM and ~/.config/dam data folders, the DAM Sync mirror folder, vaultcrypt MAGIC DAMV1 and its dam-* key labels, the dam_vt, dam_at_ and dam_session cookies, the x-dam-* headers, the dam_ automation token prefix, the dam: XMP prefix, the Keychain service ai.nodemode.dam.vault and the selfcheck "dam" key.
### audit fixes after round 72 · window session, package hardening, family replay, Clean Up input
- refers-to: security LAUNCH_KEY, LAUNCH_GENERATED, WINDOW_SESSION, SESSION_COOKIE, shell_allowed, window_allowed, automation_allowed, OPEN_PATHS; automation router GET/POST /session, _from_window, token-before-state; main lifespan launch address; packagesvc MIN_PASSWORD 16, MAX_MARKER, MAX_MANIFEST, MAX_MEMBER, _read_capped, _copy_capped, _check_space, _clean_file, _entry edit and live, _number, _apply_meta, _open_entry, open_package, _album_for, _merge_notes, check_password; editsvc _unit, _point, clean_spots, sanitize_state, _retouch; gpsscrub XMP_LOC, IIM_PLACE, _iim, _png_crcs; geosvc set_location_hidden pair; gallerysvc stamp and video metadata; familynet bound, _confirm, _tried, _accept_beacon, add_manual, fetch dev check; familyserver _sealed(request); edit router SegmentIn box range, _analysis_lock, cache key with sha256; setup/fetch_model.py
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

An independent read-only audit found two serious and eight moderate defects in this round's work; all are fixed and re-probed. (1) The automation gate trusted Sec-Fetch-Site, which any local program can send; with it a script could turn automation on and read the family key. Replaced: the launcher (desktop shell, setup/DAM_boot, DAM_boot.bat) makes a 256-bit key, hands it to the engine as DAM_SHELL_KEY and opens the window with it in the URL fragment (never sent to a server); the window posts it once to /api/session and gets an HttpOnly, SameSite=Strict cookie whose value is an HMAC of the key, so it survives engine reloads with the same key. The engine pops the key from its environment at import, so ffmpeg and Edit With apps never inherit it. An engine started by hand makes its own key and prints the connecting address. Cookies are not port-scoped, so a page from another local server opened in the same browser would send it on simple GETs, but it cannot read the responses (no CORS) and every write needs a custom header that forces a preflight the engine never grants. (2) Edit With files went into packages unscrubbed; now they are scrubbed and re-rendered if GPS remains. (3) A Live Photo's video took its own location flag; hiding a still's location now hides its video's too, and packages pass the still's choice to its video. (4) Zip sizes are capped (marker 4 KB, manifest 16 MB, member 8 GB, total against free disk) and each member is copied with a byte budget that cannot exceed its declared size. (5) Every manifest field is type- and range-checked and each entry is opened on its own, so a bad entry is counted as failed instead of ending the import. (6) Retouch spots are sanitized when a package's edit is stored and again when any edit renders, so non-finite boxes or short lists cannot break rendering. (7) Chosen passwords need 16 characters because WinZip AES uses PBKDF2-SHA1 with 1,000 rounds; the generated password carries 125 bits. (8) A photo already in the library is only linked, never changed, by a package. Minor: the family seal binds the path and the request nonce, so old responses cannot be replayed; a beacon for a new device or address is accepted only after a signed hello from that address names the same device (once a minute per address); a peer's journal listing must be its own and never ours; Clean Up boxes are range-checked and its analysis cache is locked and keyed by file hash; IPTC-IIM and nested XMP place names are blanked; PNG CRCs are recomputed after scrubbing; the Windows installer now verifies every model's SHA-256 through setup/fetch_model.py. Not changed: "local network" still means private, link-local and loopback ranges, so VPN ranges count; any holder of the family key can claim any device id (the key is the trust boundary).
### services/species.py + lookup.py v2 + data/lookup_world.json.gz + setup/gen_lookup_data.py · Look Up names about 384k species, 3.7k landmarks, 590 artworks and 1.2k foods on device
- refers-to: species MODEL/MATRIX/SCALES/NAMES, ready, _load, embed, _scores, _display, kind_of, identify, prepare, __main__; lookup VERSION 2, WORLD, _world, WORLD_LANDMARKS, ORGANISMS, BIO_MASS, DOMESTIC, CLEAR_GATE/CLEAR_MIN/CLEAR_MARGIN/FOOD_PICK, GROUPS fungus/art/food, TEMPLATES, VOCAB, CREATORS, PROMPTS, _mat disk cache, nearby, _within, _species, identify, apply image loader; lookupdata KIND_LABELS; gen_lookup_data landmarks/art/food; oc_install, DAM_oc_install.bat, build_macos_app bioclip lines and app/data bundling
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

Look Up used the library's CLIP B/32 vectors against about 500 hand-listed names. It now has three sources. (1) Species: BioCLIP (MIT) image tower, an int8 ONNX re-export pinned by sha256 after checking it against the official open_clip weights here (cosine 0.91 to 0.99, same top species on every sample), compared against BioCLIP's own text embeddings for 384,490 taxa from the bioclip-demo space (MIT). The fp32 matrix is 787 MB; the installer downloads it once, `python -m app.services.species prepare` converts it to int8 with a float16 scale per taxon (197 MB, mmap'd, scored in 64k-row chunks in about 0.25 s per photo) plus a 4 MB gzipped taxonomy, and deletes the source. Duplicate taxa are merged on genus and first epithet; a species is named at 0.3, otherwise genus then family is named when its summed probability reaches 0.45. BioCLIP is closed-world (it always names something), so it only runs when the CLIP gate's organism groups together carry at least 0.2 and outweigh food: a hamburger at 0.19 used to come back as a King Bolete. When it says domestic dog or cat, the CLIP breed list still names the breed. Kinds now come from the taxonomy (mammal, fish, reptile, amphibian, mollusc, crustacean, fungus), with the scientific name as a detail line. (2) Landmarks, artworks and dishes from Wikidata (CC0), vendored as a 119 KB gzip and rebuilt with setup/gen_lookup_data.py through the QLever endpoint (query.wikidata.org rate-limits to one query a minute and cuts off long results). Landmarks carry a radius by type (0.5 km church to 20 km national park); with GPS every landmark in range competes, which turns Eiffel from no answer into 1.0 and Colosseum into 0.87; without GPS the 1,500 most-linked landmarks compete. Art prompts carry the artist. (3) Prompt matrices over 64 rows are cached as float16 in the library cache keyed by a hash of the prompts, so the 1,500 to 3,700-row matrices are embedded once (about 2.6 ms a prompt). Art and food also accept a clear but low pick (gate 0.6, top 0.15 and 1.5 times the runner-up; food at 0.25) because their vocabularies hold near-synonyms. Known misses: Colosseum without GPS splits with Verona Arena and is dropped rather than guessed; Hokusai's wave carries a corrupted English label in the current Wikidata snapshot. app/data was never bundled by build_macos_app (offline place names were missing from the packaged app too); it is now added with --add-data. Replaced code: clipsvc._qr used QRCodeDetector.detect, which fires on feathers and fabric; it now needs a decoded payload.
### services/cleanmodels.py + edit router cleanup routes + editsvc._retouch mask/pixelate + cleanup._inpaint context · Clean Up selects objects and suggests distractions on device
- refers-to: cleanmodels SAM_MODEL/DET_MODEL/FACE_MODEL, status, _session, _polygons, segment, suggest, faces, pixelate, fill_polygons; edit router SegmentIn, _analysis, _analysis_base, _analyse, GET /media/{id}/cleanup, GET /media/{id}/cleanup/suggest, POST /media/{id}/cleanup/segment; editsvc._retouch kind mask & pixelate; cleanup._inpaint side; oc_install, DAM_oc_install.bat, build_macos_app fetch_model lines
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

Clean Up was brush-only, with LaMa filling the brushed area. Two more Apache-2.0 models from the opencv zoo now run on device, both sha256-pinned in the installers and the build script and bundled with the models folder. EfficientSAM-Ti (about 40 MB) turns a click or a box into an object outline: the image goes in at 1024 square, up to six prompts (label 1 a point, 2 and 3 box corners, -1 padding) and three candidate masks come back with predicted IoU. For a box prompt the best-IoU mask is right; for a single click argmax IoU picks a fragment (a wheel, a window), so a click takes the largest candidate under half the frame with IoU of at least 0.3, which on the street test picks the whole car. Outlines go to the client as up to twelve normalized polygons and are stored in the edit as {kind: mask, polygons}, so the edit stays resolution-independent and the export at full size fills the same shape. YOLOX-s (about 35 MB, COCO classes) proposes distractions: 640 letterbox with pad 114, raw BGR, grid decode with strides 8/16/32, score 0.45, NMS 0.5; the largest box is dropped when it is central and over 15 percent of the frame (that is the subject), and anything over half the frame is dropped. Faces come from YuNet, which People already ships; a brush stroke of three or more points that mostly lies inside a face box becomes {kind: pixelate, box}, applied after the fill as a block mosaic. Analysis runs on the 1024 developed base (with any external edit) and is cached per item, so suggestions take about 0.2 to 0.5 s and a selection about 2.5 s. Object masks are grown by short side / 90 rather than / 200 because motion blur and soft edges leave a ghost otherwise. The LaMa crop now always carries half the object size of context on each side (it had as little as 48 px for large objects, so the pavement and kerb lines did not continue through the fill). Replaced code: a high-pass grain transfer that pasted 8 px tiles from a ring around the mask into large fills; it left visible tile blocks and was removed. LaMa ignores pixels under the mask, so a coarse pass then a fine pass cannot sharpen large fills; they stay soft, which is the model's limit.
### security.automation_allowed + routers/automation.py + shell key · automation access off by default
- refers-to: security SHELL_HEADER, AUTOMATION_HEADER, OPEN_PATHS, AUTOMATION_OFF, _automation_state, forget_automation, automation_allowed, local_only_guard gate; automation router GET/PUT /system/automation, POST /system/automation/rotate, _from_window, _issue; main router list; src-tauri main.rs shell_key, engine_post/engine_get header, backend_command env
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

The owner's rule: agentic or MCP use of the library must be switched on by the user and is off by default. Before this, any local program that sent x-dam-local could drive the whole API. Now every /api path except /api/health needs one of four things. (1) The app window: browsers and WKWebView mark same-origin requests with Sec-Fetch-Site: same-origin, which fetch, images, video and downloads from the page all carry. (2) The desktop shell: it makes 256 random bits at launch, passes them to the engine it spawns as DAM_SHELL_KEY and sends them as x-dam-shell on its own calls (menu-bar import, Keychain unlock results, glass state). (3) An automation token: Settings > Privacy issues one (256 bits, shown once, only its SHA-256 kept), only from the window, and turning access off deletes it; a token holder can turn access off but cannot turn it on, rotate the token or mint another. (4) DAM_AUTOMATION=1 in the engine's environment, the explicit switch for the test suite and scripted runs, which the Privacy pane names when it is in force. Everything else gets 403 with a message saying where to turn access on. What this is and is not: it closes the documented doorway that scripts, agents and MCP servers use and makes their use a deliberate user choice; a program that already runs as the user and sets out to forge browser headers, or reads files on disk, is not stopped by it, which is why hidden, deleted and private items stay encrypted in the vault.
### services/familynet.py + familyserver.py + syncsvc shared channel + syncapi family routes · Shared Library on the local network with a share key
- refers-to: familynet mirror/new_key/normalize_key/pretty_key/settings/_derive/family_id/private_ip/sign/verify/seal/unseal/_request/_beacon_payload/_accept_beacon/add_manual/peers/_beacon_loop/_listen_loop/start_discovery/stop_discovery/fetch/_fetch_objects/serve_path/journal_listing; familyserver app, guard, /f/hello, /f/journal, /f/journal/{name}, /f/object/{name}, /f/edit/{name}, start/stop/sync_state; syncsvc config & _base shared branch, run_once fetch; syncapi /family, /family/key, /family/peers, shared channel folder refused; main lifespan familyserver
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

The owner's rule: the family library works only on the local network and only between DAM apps that hold the same share key, and it is off until turned on. The key is 160 random bits shown as 32 base32 characters; HKDF-SHA256 derives separate subkeys for request signatures, response encryption, the beacon MAC and a short Family ID members compare by eye. Discovery is a UDP broadcast every 20 s on port 48792 carrying the device id, port, time and an HMAC, with the device name sealed, so a member is recognised only by key holders and nobody else learns a name; a device can also be added by address. The peer endpoint is a second FastAPI app on its own port (8792 by default), started only while the Shared Library is on: it refuses any client that is not a loopback, link-local or private address, accepts only GET under /f/, and requires an HMAC over method, path, time and a fresh nonce from the requesting device (two minutes of clock skew, nonces remembered for four); every reply body is AES-256-GCM sealed with the path as associated data. The rest of DAM is never reachable from it. Transport reuses the sync engine unchanged: the shared channel's folder is now a private mirror under the library (family/DAM Sync); each pass first fetches every peer's journal files and the originals and Edit With files they reference into the mirror, then pulls and pushes as before, and peers fetch my journal from my mirror. Members fetch from each other directly; there is no relay and no folder transport any more, so a cloud folder cannot carry family photos. Replaced: the user-chosen folder for the shared channel.
### services/packagesvc.py + gpsscrub.py + gallerysvc.py + routers/packages.py + db v11 · encrypted share packages replace the guest server
- refers-to: packagesvc new_password/build/_entry/_payload/_strip_video/inspect/check_password/open_package/_import_member/_apply_meta/_apply_edit/_album_for/_merge_notes/add_note/ensure_album_share, ORIGIN_RE; gpsscrub scrub/_blank_tiff/_wipe_ifd/_png_chunks/_riff_chunks/has_gps; gallerysvc (web_gallery, download_path, gps_exif moved from the removed sharesvc); packages router; db MIGRATIONS[11] media.origin_sha, albums.share_uuid, album_notes, share_packages, guest-server tables dropped; main router list; removed shareserver.py, services/sharesvc.py, routers/sharing.py
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

The owner asked for sharing that never opens a server: a password-protected AES zip the user sends however they like, opened by dropping it into DAM. Format: a standard zip (pyzipper, WinZip AE-2, AES-256 with HMAC-SHA1 authentication per member) holding one plain marker member (formdam-share.json, only the format name and version, so DAM can recognise a package before asking for the password) and everything else encrypted: members named with 128 random bits and an encrypted manifest that carries the real names, origin hashes, metadata, keywords, edit state (with any Edit With file as its own member), trims, Live Photo pairs, and for album packages the album's share id and its notes. Nothing about the photos is readable without the password; the zip listing shows only random names and sizes. Passwords: suggested as 25 characters from a 32-symbol alphabet (125 bits), at least 10 characters if typed. Location is left out by default: GPS is removed in place, byte for byte, from TIFF-structured EXIF (JPEG APP1, HEIC Exif items, PNG eXIf, WebP EXIF, TIFF-based RAW) by retagging the GPS pointer and zeroing the GPS directory, and from XMP by blanking GPS and location values to the same length, so pixels and file size are untouched; the result is re-read and, if GPS is still found, the photo goes as a rendered JPEG instead (counted and said in the result); videos are remuxed by ffmpeg without metadata. Opening: the upload is kept under cache/incoming for at most a day, the password is checked against the manifest before the import job starts, member names are taken only if they are 32 hex characters and file names are reduced to safe basenames. Photos are matched first by origin hash (the original's hash travels in the manifest, and an imported copy whose bytes differ because GPS was removed remembers it), so sending an album back and forth never duplicates. Packages arrive as a new album or a stack; album packages always join the album with the same share id, add what is new and merge notes by id, which is how a shared album stays in step in both directions without a server. Private, hidden and vaulted items are never packed, and an incoming item that matches one of them is left alone. The guest web server, its routes, tables and settings are removed; the static Web Gallery export stays.
### syncsvc & sharesvc · fixes from the independent audit
- refers-to: syncsvc SHA_RE, EXT_RE, JOURNAL_RE, _object_path, _scope, _secret, _retract, _apply_retract, _apply_media checks, _live_row, _attach_live, pull journal listing & per-record guard, set_shared contributor rule, FIELDS trims; db SYNC_MEDIA_COLUMNS private & trims; sharesvc item_ids cache & forget_items, allowed live check, contribute duplicates, download_path trims & ffmpeg checks, gps_exif, settings name; shareserver contribute guard in the middleware, VIEW_ONLY_PX; sharing.share_album re-share fields & smart albums
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

A read-only audit of the new code found these, all fixed here. Sync: hidden items' records (caption, location, keywords) were written to the journal, and items that became private, hidden or vaulted after syncing stayed in the folder and visible elsewhere. Now any secret item (private, hidden, or vaulted while not merely deleted) is never written; if its original is already in the folder, the file (and its Live video) is deleted and a retract record carrying only the hash & size makes other computers hide and seal their copy. Hiding is one-way across computers: unhiding does not unhide elsewhere. Journal records are untrusted input: the hash must be 64 hex characters and only a short alphanumeric extension is taken from the name, so a crafted record cannot point the import at a path outside the folder; a duplicate import of a private or hidden local item is never touched; malformed records are skipped one by one. iCloud placeholders (.NNNNNNNN.jsonl.icloud) and gaps in a device's numbering stop that device's cursor until the file arrives, instead of skipping it; names that are not journal files (conflicted copies) are ignored. Only the contributor can move a Shared Library item back to Personal; a shared record never alters a photo that is only in my Personal Library. Trims and Live Photo videos now sync. Sharing: re-sharing an album applied only the flags and kept the old password and expiry; it now applies everything on the form. Shared videos ignored trims and could be cached as a 0-byte file when ffmpeg failed: trims are cut, the return code and size are checked, only the first video and any audio streams are copied. Downloads off now also caps stills at 2048 px (videos still stream, to play). Include location now writes GPS into rendered photos and the web gallery too, never for a location the user hid. Contribution uploads are refused in middleware, before the body is read, unless the link allows them and the length is under the limit. Guest uploads of files the library already has no longer attach existing items. A share's item list is cached for 5 s, with every per-item request still re-checking that item live. Smart albums are refused instead of sharing as empty. The guest page shows a chosen name, not the hostname, by default.
### services/syncsvc.py + routers/syncapi.py + db v10 · library sync across computers & the Shared Library
- refers-to: syncsvc device_id/device_name/config/configure/_scope/_carries_object/_record/_put_object/_put_edit/push/_write_device/devices/_keywords/_apply_media/_fetch_edit/_apply_album/pull/_cursor/_after_pull/run_once/_loop/start/sync_now/ensure/set_shared; syncapi GET /sync, PUT /sync/device, PUT /sync/{channel}, POST /sync/now, POST /media/shared-library; query FLAGS shared_library & personal_library; db SYNC_STAMP, SYNC_MEDIA_COLUMNS, MIGRATIONS[10] meta_ts, shared_lib, shared_origin, albums uuid & meta_ts, sync_tombstones, triggers; main lifespan syncsvc.ensure
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

Sync runs through any folder the computers share (iCloud Drive, Dropbox, OneDrive, Syncthing, a NAS, an external drive) rather than a server, so DAM stays loopback-only and the user picks the transport. Layout: DAM Sync/devices/<id>.json (name, last seen), objects/<sha[:2]>/<sha><ext> (content-addressed originals, plus objects/edits for Edit With results), journal/<device id>/<seq>.jsonl. Every device writes only its own journal directory, so cloud folders never see two writers on one file; files are written to .tmp & renamed, so a reader never sees half a file. Change tracking is in SQLite: triggers stamp media.meta_ts when a synced column changes or a keyword is added or removed, and stamp albums.meta_ts on rename or membership change; a deleted album leaves a tombstone. The triggers fire only when the UPDATE did not itself set meta_ts, which is how applying a remote record keeps the remote stamp instead of re-stamping it. A pass pulls first (other devices' journals from a per-device cursor of file and line, applying a media record only when its stamp is newer than the local one, so the last writer wins per photo), then pushes everything stamped since the last push. Identity across machines is the content hash & size the importer already keys on; albums get a UUID. An item whose original has not arrived yet (cloud still downloading) stops that device's cursor at that line & is retried next pass, so nothing is skipped & albums that follow it see their photos. Synced: originals, edit state & Edit With files, favorite, rating, label, reject, title, caption, alt text, keywords, capture date, location & its hidden flag, hidden, deletion, plain albums. Not synced: private & vaulted items (never written to the folder), hidden items (never sent; hiding an already-synced photo sends only the flag so other computers hide it too), smart albums, people & faces (each computer recognises its own), memories. The Shared Library is the same engine on a second folder scoped to items flagged shared_lib, remembering which device contributed each one: participants see, edit & delete them; the contributor moving one back to Personal removes it from the others' libraries (to Recently Deleted, with the reason) while it stays on the contributor's. The library view switch (Both, Personal, Shared) is a quick filter on shared_lib. The pass runs every 60 s while a channel is on, & on demand. Phones are not peers: they reach the library through share links.
### shareserver.py + services/sharesvc.py + routers/sharing.py + macshare.py + db v9 · sharing links, shared albums, web gallery, Mail, Messages & AirDrop
- refers-to: shareserver app routes /s/{token}[/unlock|/items|/t|/r|/v|/d|/activity|/post|/contribute], catch-all 404, start/stop/sync_state/running, PAGE; sharesvc settings/save_settings/_secret/lan_addresses/base_urls/url_for/_shareable_ids/create/describe/listing/live/item_ids/allowed/needs_unlock/unlock/check_cookie/items/activity/post/contribute/still_path/download_path/web_gallery/GALLERY/qr_png; sharing router settings, links, albums, revoke, activity, owner comment, qr, send, gallery; macshare.available/launch/run; desktop_entry --share; main lifespan sync_state & stop; db MIGRATIONS[9] shares, share_items, share_activity
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

DAM's engine stays loopback-only. Sharing is a second, separate FastAPI app on its own port (8790 by default) that starts only when the user turns sharing on and has no route except /s/<token>/...; everything else answers 404, so a guest can never reach /api. Tokens are 144-bit random. A share is either a link over a fixed set of items or a shared album that follows the album as it changes; both re-check every item on every request (not trashed, private, hidden, a Live Photo's hidden video, or vaulted), so hiding or vaulting a photo removes it from every share at once, and an album turned private takes its link down. Passwords are scrypt-hashed like album passkeys; a correct one sets an HttpOnly, SameSite=Strict cookie scoped to that share's path, signed with a share-only secret kept in settings (never the vault secret, whose tokens are accepted for any scope); eight wrong tries in ten minutes lock the link for the rest of the window. Guests get rendered (edited) stills as WebP & downloads with location removed by default: photos are re-encoded from the render, videos are remuxed by ffmpeg w/o metadata; turning Include location on serves an unedited original as-is. Guests may like (toggle per name), comment, & on shared albums with contributions on, upload photos & videos that are imported like any other file, added to the album & logged as activity; the owner sees unread counts, reads the activity & replies as the owner. Links work for anyone who can reach this computer: the LAN, or a VPN such as Tailscale; there is no relay, so a computer that is off or asleep serves nothing, which is the honest limit next to iCloud links. Web Gallery writes a static folder (index.html, photos/, thumbs/) that opens locally or uploads to any host, for reach beyond the LAN. QR codes come from OpenCV's QRCodeEncoder. On the Mac, Mail, Messages & AirDrop go through NSSharingService in a short-lived helper process (the frozen engine re-runs itself with --share, a dev checkout runs desktop_entry.py), because the sharing services need an NSApplication on a main thread that the engine's own event loop does not provide; elsewhere Mail opens a mailto link with the share link & AirDrop & Messages say they need the Mac app. The helper is written against AppKit's documented API and has not been run on a Mac from this container.
### services/extedit.py + edit-with routes · Edit With round trip
- refers-to: extedit.edits_dir/work_dir/external_path/_working_copy/start/status/stop/_adopt/_tick/_loop; editsvc.render_still external base; edit._base external arg, preview & auto external, revert_edits unlink, POST/GET/DELETE /media/{id}/edit-with
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

Edit With no longer hands the original to another app. It writes a working copy under library/edits/work (the original bytes when the photo is unedited & in a format editors save back, otherwise the current version rendered to an LZW TIFF, so in-app edits & RAW develop carry over), opens that, & a single poll thread watches the copy's mtime & size every 1.5 s. A change that holds still for two polls is adopted: the copy is decoded to prove it is a whole image, copied to library/edits/<id>-<stamp>-<n>, & the edit state becomes {"external": {file, app, ts}}, which render, preview & auto-enhance use as their base, so later in-app adjustments sit on top & Revert to Original removes both (and the file). The session keeps watching for further saves until it is stopped or 12 hours pass. Saving under a new name in the other app is not seen; the copy has to be saved in place. Vaulted & private items refuse, as before. Replaced: the menu entry called `filesvc.open_with(original, app)`, which let the other app overwrite the original.
### services/lookup.py + lookupdata.py + db v8 · Look Up for animals, plants & landmarks
- refers-to: lookup.identify/apply/nearby/_within/_landmark_near/scan_job/ensure, GROUPS, NEUTRAL, TEMPLATES, GENERIC; lookupdata vocabularies & LANDMARKS; clipsvc._store lookup call; discover.ensure_lookup & GET /media/{id}/lookup; browse.details lookup & subjects filter; db MIGRATIONS[8] lookup_state, lookup_json & media_dict drop; files POST /system/learn-more, filesvc.open_url
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

Look Up is zero-shot on the CLIP vector the library already stores, in two stages. A gate softmax over eight subject groups plus neutral prompts (people, food, rooms, cars, screenshots, documents, streets, landscapes) decides what the photo is of; the top group needs 0.2 & a second group 0.015 (a bee on a flower gates as flower first). Inside a group a softmax over its curated names (about 70 dog breeds, 32 cat breeds & coats, 70 birds, 27 insects & spiders, 70 flowers, 40 plants & trees, 80 other animals, 106 landmarks) must reach 0.3; when the group is certain (0.8) but no name is, the species itself is reported (Cat, Dog, Flower) w/ the leading names as alternatives, which is the honest answer for mixed or ambiguous breeds. Landmarks use the photo's GPS first: names within each landmark's radius compete against the neutral prompts & win at 0.35; w/o GPS a landmark needs 0.5 & a raw similarity of 0.25 so street scenes do not become landmarks. Results are stored as lookup_json for the info panel & as lookup labels (never generic ones, INSERT OR IGNORE so subject labels are not overwritten) so search & Subjects & Content find them. New CLIP vectors are looked up as they are indexed, & a housekeeping job covers vectors indexed before this version. Learn More opens the English Wikipedia article in the user's browser through the backend; only a bare title is accepted, the URL is built here. On the fixture set: golden retrievers & a Labrador puppy, a palm, a bumblebee on a flower & Temple Bar (w/ & w/o GPS) are named, two cat photos give Cat w/ breeds as alternatives, grayscale macaws read as Grey Parrot & a vicuña as Deer (llama & alpaca as alternatives). Accuracy is CLIP ViT-B/32 zero-shot, below Apple's dedicated models.
### services/cleanup.py + editsvc _retouch strokes · Clean Up object removal
- refers-to: cleanup.ready/_engine/warm/_key/inpaint/_inpaint/_run, MEMO; editsvc._retouch points strokes & cleanup call; edit.get_edits warm + cleanup flag
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

Clean Up runs LaMa (opencv/inpainting_lama, Apache-2.0, 512 by 512 ONNX, image 0..1 RGB & a 0/1 mask in, 0..255 RGB out) on each brushed region rather than the whole frame: the mask is grown slightly, every connected component gets a square crop about 2.2 times its box plus 32 px so the model sees enough surroundings, the crop is scaled to 512, filled, scaled back & feathered in by a blurred mask, so pixels outside the brush are untouched. Strokes are polylines of normalised points w/ a brush radius; single clicks stay circles, so earlier edit states still render. CPU timing here: about 14 s cold (session load) & 6 s warm for one region, so opening the editor warms the session in a thread & the last six results are memoised by a hash of a strided image sample plus the exact mask, which makes tab switches & export re-renders of the same strokes free. Without the model file or onnxruntime the old OpenCV Telea fill is used. Replaced: `out = cv2.inpaint(...)` as the only fill is now the fallback.
### services/rawdev.py + decode raw_opts + editsvc _lens + edit raw-info · RAW develop and lens corrections
- refers-to: rawdev._xy/_matrix/multipliers/as_shot/params/develop; decode._raw_full opts branch, open_image raw_opts; editsvc.render_still raw opts, _lens, _geometry lens call; edit.py _base raw key, raw_info, PASTE_KEYS raw & lens
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

Kelvin white balance: the CIE xy of a Planckian (Kim et al. cubic) white at the chosen temperature becomes XYZ, the camera's own rgb_xyz_matrix maps it to camera RGB, & the reciprocal, normalised to green, is LibRaw's user_wb; tint scales the two green multipliers. As Shot is found by a 50 K by 2-point grid search for the temperature & tint whose multipliers best match the file's camera_whitebalance, so the sliders open on the shot's own values (NEF 5050 K tint 52, CR2 4900 K tint 10, and rendering at those values reproduces the camera WB within 1-2 levels). A developed RAW decodes to 16-bit linear w/o LibRaw's auto-brightness, is normalised so the 99th percentile sits at white, scaled by the exposure stops, given a soft shoulder above 0.8 when highlights are Blend or Recover (LibRaw highlight modes 2 & 5 keep the clipped channels' data), then BT.709-encoded; LibRaw's own auto-brightness otherwise cancels any exposure change & darkens rebuilt highlights. Demosaic offers AHD, DHT & linear; noise uses LibRaw's wavelet threshold & FBDD; fringe scales the red & blue planes (chromatic_aberration). Lens corrections (all images) remap radially by 1 + k r^2 & lift or darken corners by r^2, before geometry. Replaced in decode._raw_full: `rgb = raw.postprocess(use_camera_wb=True, output_bps=8, half_size=half)` is now the no-options branch only. RAW & lens settings paste like other adjustments.
### exifmeta _image_kinds/_video_kinds + db v7 + editsvc long_exposure · the remaining Photos media types
- refers-to: exifmeta._image_kinds, _video_kinds, read_image/read_video tails; metasvc.META_VER 2, apply kinds update, keep_location rule; db MIGRATIONS[7]; query FLAGS animated/timelapse/cinematic/spatial/long_exposure; browse.MEDIA_TYPES; editsvc.long_exposure, _average_frames, render_still effect branch; edit.py _store is_long_exposure + preview LE base
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

Animated: GIF, PNG & WebP w/ more than one frame. Spatial photos: a HEIC whose top-level images are two of the same size (the stereo pair; depth & gain maps are auxiliary, not top-level). Videos: every format & stream tag is scanned, so time-lapse is a capture-mode tag whose value is time-lapse (ExifTool shows Apple's as Track1 CaptureMode), cinematic is any cinematic key or a cinematic handler, spatial is a spatial or stereo key or Stereo 3D side data (MV-HEVC). These are tag rules, checked here on files written w/ those tags, not on iPhone originals. Long Exposure is what Photos does: an effect on a Live Photo, computed from up to 90 frames of the paired video, aligned by ECC translation to the middle frame & averaged, cached under cache/effects; the edit state carries effect=long_exposure, so it is revertible & pastes like any edit, & the item joins the Long Exposure type. META_VER 2 re-reads every item for the new kinds; the location rule changed so a rescan never overwrites a location the user set or removed. Replaced: `keep_location = row["lat"] is not None and row["meta_ver"] and row["meta_ver"] >= META_VER` (which would have re-read GPS on every version bump).
### routers/curate.py memory_from_prompt + curatesvc._pick near-duplicate rule + routers/library.py disk metadata · describe a memory, rate files on disk
- refers-to: curate.memory_from_prompt (/memories/prompt); curatesvc._pick last-shot comparison; library._sidecar_record, disk_meta (/disk/meta), disk_browse rating & label
- kind: rationale + replaced code
- logged: zip v1.22.0 · 2026-10-10

Describe a Memory runs the description as a full text search w/ the visual scope (CLIP, places, dates, people, keywords) & builds a memory from the hits through the same picker, so "dogs at the beach" or "Tokyo in May 2025" works offline w/o a generative model. The picker's burst guard used to drop any image under 2 s after the previous one, which also dropped different photos sharing a file-time date; it now drops only when the dimensions & camera model also match. Replaced: `if last is not None and r["created_ts"] - last < 2 and r["kind"] == "image": continue`. Browse Disk reads each file's XMP sidecar for rating & label & writes them back (0-5, X reject, 6-9 labels, keywords merged) the way Bridge rates files that are not in a catalog; a file that is also in the library gets the same values in the catalog.
### app/libraries.py + routers/library.py + db.connect path check + referenced imports · library switcher, repair, consolidate, disk browsing
- refers-to: libraries.config_dir/current/listing/remember/forget; library.py /library, /library/switch, /library/forget, /library/repair (repair_job), /library/import-orphans, /library/consolidate, /disk/browse, /disk/thumb, /disk/file; db.connect (per-thread path check); libraryfs.import_one reference arg + consolidate; importer.ImportIn.reference + upload ids; vaultcrypt._protect consolidate-first; trash._purge_row keeps referenced files; desktop_entry library default from the registry; main.py router tuple
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

A library is a folder (dam.db, originals, cache, vault). The registry (libraries.json in the per-user config folder: Application Support/DAM, %APPDATA%/DAM or ~/.config/dam; DAM_CONFIG overrides) remembers known libraries & the last one opened, & the desktop entry opens that one unless DAM_LIBRARY is set. Switching is in-process: DAM_LIBRARY is repointed, every thread's sqlite connection notices its file changed on the next query & reconnects (connect() now keys the cached connection by path), the schema migrates, the vault session resets & re-reads its keypair, the CLIP matrix, search cache & edit previews are dropped, & the backfills start for the new catalog; the page reloads. It refuses while any job runs, so no job writes half its work into the wrong catalog. Referenced ("Add in place") items keep an absolute rel_path, which os.path.join already resolves, & referenced=1. Their files are never deleted by DAM: permanent delete removes the catalog row only, & making a referenced item private first copies it into the library & seals that copy (the outside file is the user's & stays; the UI says so). Consolidate copies (or moves) referenced files into the dated originals tree. Repair runs PRAGMA integrity_check, reports missing originals & offline referenced files, rebuilds missing thumbnails, lists media files in originals that no row points to (importable in one step), deletes thumbnails & renders for ids that no longer exist, optionally re-hashes every original, & finishes w/ PRAGMA optimize; the last report is kept in settings. Disk browsing (/disk/*, separate from the import picker's /fs/browse) lists a folder's media w/ whether each is already in the library (by path, or name + size), serves cached WebP thumbnails keyed by path, mtime & size (ffmpeg frame for video) & a preview, and only for media extensions, so the endpoint cannot be used to read arbitrary files.
### services/curatesvc.py + routers/curate.py + query group/memory rules · groups of people, memories
- refers-to: curatesvc.groups/_person_sets/_pick/_upsert/generate/custom/listing/items; curate.py /people/groups, /people/groups/{key}, /memories, /memories/generate, /memories/{id} GET PATCH DELETE, /memories/{id}/remove, /memories/{id}/music, ensure_memories; query.rule_sql group & memory; main.py router order (curate before people), housekeeping + startup
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

Groups are computed, not stored: every visible item w/ two or more visible people contributes each 2- to 4-person combination; a combination seen in 3+ items is a group, & a smaller group is dropped when a larger one containing it appears at least as often, so "A & B & C" does not also list "A & B" unless A & B also appear apart. people_groups keeps only a user name or a hide flag per key (sorted person ids). The curate router registers before people so /people/groups is not read as /people/{person_id}. Memories come from trips, this week in each past year (a 7-day window), months w/ 30+ items ("Best of May"), named people w/ 12+ items ("Over the Years"), pets w/ 8+ items, & CLIP subjects (beach, snow, food, sunset, mountains, flowers, live music, celebrations); 6 items minimum. Picking drops screenshots, screen recordings, rejects & all but one frame per stack, splits the range into 40 equal time buckets & takes the best of each (favorite x3 + rating + edited + a small bonus for video), then removes shots under 2 s apart. A memory keeps its items once made, so removals stick across regeneration; hiding is a soft delete so a hidden memory is not recreated. Music is a theme (gentle, uplifting, dreamy, none) rendered in the browser, or a local audio file the engine streams from its path; nothing licensed ships.
### services/xmpsvc.py + outputsvc.py + routers/output.py + libraryfs sidecar read · XMP, File Info, templates, export, contact sheets, print, workflows
- refers-to: xmpsvc.record_for/build_xmp/parse_xmp/apply_record/import_sidecar/embedded_xmp/write_sidecar/sidecar_job/write_jpeg_xmp (adapted from formlit metadata.py & xmpembed.py, Apache-2.0); outputsvc.export_one/export_job/contact_sheet/print_sheet/run_workflow/apply_fields; output.py /fileinfo/common, /fileinfo, /metadata-templates, /xmp/settings, /xmp/write, /xmp/read, /export, /contact-sheet, /print-sheet, /workflows, ensure_sidecars, start_autosave; libraryfs.import_one sidecar tail; main.py router tuple, housekeeping, autosave start
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

Metadata travels the way Bridge & Lightroom expect: rating (reject = -1), label, title, description, alt text, the IPTC Core & Extension fields File Info edits, hierarchical keywords as lr:hierarchicalSubject w/ leaves in dc:subject, capture date, GPS (exif:GPSLatitude in the XMP D,M.mmmmN form) & named people as PersonInImage. DAM-only state (favorite, the edit JSON) goes in a dam: namespace so other apps ignore it. Sidecars sit beside the original as name.xmp; vault-protected items never get one, because a sidecar beside a sealed file would leak its metadata. Writing is opt-in (Keep XMP sidecars up to date), then any item whose xmp_ts is NULL (every metadata, keyword, location, date or edit write nulls it) is rewritten by a 30 s ticker; Write XMP Sidecars does it on demand. Import reads a sidecar beside the source (name.xmp, NAME.XMP or name.ext.xmp) or the embedded packet, so ratings, labels & keywords made in Bridge or Lightroom arrive w/ the files; keyword paths go through keywordsvc.assign, which builds the hierarchy. File Info edits title, description & alt text as columns & everything else in iptc_json; multi-item editing writes only the fields touched & reports mixed values as placeholders. Templates save filled fields & apply in replace or fill-empty mode. Export renders through editsvc at full resolution, resizes by long/short edge, width or height, encodes JPEG (4:4:4 at q >= 90), HEIC, PNG, TIFF (LZW) or WebP, names files w/ the rename tokens, files them in date, month, place or album subfolders, carries EXIF from the source w/ orientation reset to 1 (pixels are already upright) & GPS dropped when location is excluded or hidden, embeds the XMP packet (JPEG APP1 by hand, the others through Pillow's xmp argument) & can add a sidecar; Export Unmodified Original copies the file. Contact sheets & print layouts are 300 dpi Pillow PDFs (A4, Letter, A3, Tabloid; columns, captions, title; print pages rotate to the photo). Workflows are saved step lists (template, keywords, rating, label, rename, sidecars, export) run as one job.
### services/editsvc.py + routers/edit.py · non-destructive editing, preview, auto, paste, revert, trim
- refers-to: editsvc.STAGES/FILTERS/edits_of/apply_edits/render_still/effective/_tone/_geometry/_retouch/_markup/auto_enhance; edit.py /media/{id}/edits GET PUT DELETE, /media/batch/edits, /media/{id}/preview, /media/{id}/auto, /media/{id}/trim, /media/{id}/trim/export, invalidate, _base LRU; main.py router tuple
- kind: rationale + replaced code
- logged: zip v1.22.0 · 2026-10-10

The edit is one JSON state per item (light, color, bw, detail, filter + amount, levels, curves, geometry {rotate, flipH, flipV, straighten, crop}, retouch spots, markup shapes), not an op list: sliders map 1:1 to keys, paste can replace the adjustment groups & keep the target's crop, retouch & markup (Photos' Paste Edits rule), & the render cache key is a hash of the JSON. Replaced the P3 seed: `edits_of` returned a list & `apply_edits` returned the image unchanged. Order is fixed: retouch (in the uncropped, unrotated frame, so spots survive later crops), geometry, tone, markup (in the final frame). Straighten rotates about the centre & crops to the largest same-aspect rectangle, so no empty corners. Tone runs in float32 sRGB: exposure as 2^stops, brightness as a gamma, highlight & shadow masks from smoothstepped luminance, contrast about 0.5, black point, levels, curves by piecewise-linear interpolation, saturation & vibrance (vibrance weighted by 1 - current saturation), warmth & tint as channel offsets, B&W w/ a tone-shifted channel mix, definition as large-radius local contrast, bilateral noise reduction, unsharp sharpening & a radial vignette; brilliance spreads into shadows, highlights & contrast. Filters are named presets added on top of the sliders, scaled by amount. Retouch is cv2.inpaint (Telea) on circular masks, so Clean Up works offline w/o a generative model. Markup draws pen, box, oval, arrow & text w/ Pillow. Saving clears the render cache, the item's thumbnails, the in-memory preview bases & its CLIP vector (re-embedded by the next clip pass) & nulls xmp_ts. Previews decode the base once per (item, width, edited_ts) into a 4-entry LRU & return JPEG w/ no-store; a 1600 px preview of the full pipeline takes about 0.3 s. Trim stores trim_in/out for playback; Save as New Clip stream-copies the range w/ ffmpeg (no re-encode) & imports it, dated at the original's capture time plus the trim start.
### services/clipsvc.py + cliptok.py + routers/discover.py + db v6 pets + query visual/similar/pet/search rules · visual search, pets, content
- refers-to: clipsvc.status/ready/embed_images/embed_texts/classify/index_job/_store/_assign_pet/_refresh_pet_covers/search/similar/forget; cliptok.Tokenizer.encode/_bpe; discover.py /clip/status, /clip/index, /labels, /pets, /pets/{id}, /pets/merge, /media/{id}/not-pet, /search/suggest, ensure_clip; db.py SCHEMA_VERSION 6 + MIGRATIONS[6]; query.rule_sql search/pet/visual/similar branches, text_sql visual scope, _visual_ids; wiring.connect followon clip step; main.py router tuple + housekeeping + startup; exifmeta exifread logger level; oc_install, setup/build_macos_app, setup/DAM_oc_install.bat model fetch; requirements onnxruntime pin
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

One model does object, scene & natural-language search, subject labels, content collections & pet grouping: OpenCLIP ViT-B/32 trained on LAION-2B (MIT), the onnx-community int8 export (152 MB, sha256-pinned at revision de693d0) run by onnxruntime (MIT, already in the Mac bundle through RapidOCR). The export is one graph w/ both towers, so image calls pass a two-token dummy text & text calls a blank 224 image; the cost is one extra small pass per call. The tokenizer is OpenAI's CLIP BPE re-written against the published vocab & merges w/ the stdlib re (letters [^\W\d_], digits one at a time), verified against the reference ids for "a photo of a cat". Images embed from the 384 px thumbnail (bicubic shortest side 224, centre crop, CLIP mean/std), 16 per batch, newest first; vectors are float16 in clip_vectors & a numpy matrix in memory, rebuilt when the index changes. Search keeps results within 0.06 cosine of the best hit & above 0.22, values chosen on a mixed 18-photo set (dogs, cats, receipt, diagram, pub, car, flowers) where every true hit scored >= 0.24 & every miss <= 0.21; results are cached per text until the index changes, so paging a search does not re-embed. Labels are zero-shot over 70 subject prompts & 8 content prompts (document, receipt, handwriting, illustration, diagram, whiteboard, menu, map): softmax at the CLIP scale of 100, kept when p >= 0.12 & cosine >= 0.18, top 4; QR codes come from cv2.QRCodeDetector on the thumbnail. Pets: a dog or cat image joins the nearest pet of its species when cosine to the running centroid >= 0.78 (same animal re-cropped 0.93, different animals of one breed <= 0.69), else starts a new pet; pets live in their own table (v6) so the face rebuild, which deletes unnamed people, never touches them. The text scope "visual" ORs semantic hits into free-text search; rule "search" stores a whole text search inside a smart album; rule "similar" lists items within 0.6 cosine of one item. The clip step runs after every import through followon & as a 6 h catch-up through housekeeping.
### services/geosvc.py + routers/geo.py + app/data places & countries + query bbox rule · places, trips, location & date edits
- refers-to: geosvc.reverse/country_at/assign/on_metadata/backfill_job/search/points/places_summary/home_place/trips/set_location/set_location_hidden/adjust_dates; geo.py routes /places, /places/points, /places/countries, /places/search, /places/reverse, /trips, /media/location, /media/location-hidden, /media/dates, ensure_geo_backfill; wiring.connect geosvc hook; main.py router tuple + housekeeping + startup backfill; query.rule_sql bbox branch
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

Reverse geocoding is offline, so a local-first library never sends a coordinate anywhere. places.json.gz is GeoNames cities5000 (CC BY 4.0) cut to name, lat/lon at 1e-4, country, admin1 & population, without PPLX/PPLH/PPLQ/PPLW rows (city sections & dead places, which would name Paris "Paris 04"); countries.json.gz is Natural Earth 1:50m admin-0 (public domain), Douglas-Peucker simplified after splitting each ring at its midpoint so closed rings survive. Lookup scans a 1 degree latitude band w/ numpy haversine, then prefers the most populous place within 8 km of the point (the city over its own districts) & accepts the nearest within 60 km; past that, the country comes from point-in-polygon, so a photo at sea or in the outback still gets a country. Places are assigned by a metasvc on_applied hook (import & backfill) & by a resumable "places" job for catalogs that already had GPS. Home is the most-photographed place; a trip is a run of located items at least 100 km from home w/ no gap over 2 days & at least 4 items, titled by its top two places, or its country when it spans several. Location edits null alt & xmp_ts so the XMP writer re-emits the record; location_hidden keeps the coordinates but drops the item from the map, the Places summary & bbox queries. Date adjust keeps orig_created_ts once (the first original), set mode moves the earliest item to the given time & keeps the others' spacing (Photos' multi-item rule), revert restores it; metasvc never overwrites an adjusted date.
### routers/organize.py + routers/files.py + services/keywordsvc.py + stacksvc.py + filesvc.py + renamesvc.py + app/wiring.py + albums.py smart/folders · organizing
- refers-to: organize.set_meta/set_meta_batch/_apply_meta, keyword routes, stack routes, album-folder routes, move_album, create_smart/update_smart; files.rename_preview/rename/copy_to/reveal/open_with/editors; keywordsvc.tree/ensure/update/delete/merge/assign/paths_for/export_text/import_text; stacksvc.create/best_of/dissolve/remove/stack_burst/auto/on_metadata; filesvc.rename_plan/rename/copy_originals/reveal/open_with/editor_apps; renamesvc.expand (adapted from formlit rename.py, Apache-2.0); wiring.connect; albums._album_payload, album_detail smart branch, add_items smart guard; main.py wiring + router tuple
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

Ratings 0 to 5, seven colour labels (Bridge's set plus orange and purple, Photos-style), reject, title, caption & alt text are plain media columns written singly or in batch; any write clears xmp_ts so the sidecar writer (P8) knows the record changed. Keywords keep the existing keywords table (name UNIQUE, so a leaf name lives once; "A|B|C" input builds the chain) & gain parent_id & a one-key shortcut; delete re-parents children, merge moves assignments, the text import & export use the tab-indented format Lightroom & Bridge exchange. Stacks are a table plus media.stack_id; the query layer collapses each stack to its top; bursts stack themselves through a metasvc on_applied hook registered in wiring.connect, the one place hooks are wired so later phases do not edit main.py. Smart albums are albums rows w/ rules_json, evaluated by query.py at read time (count, cover & items), so they never go stale; adding items to one is refused. Album folders nest w/ a cycle check; deleting one lifts its albums & subfolders to its parent. Rename runs a plan first (preview == result), skips vault-protected items bc their rel_path is the decrypt target, carries an XMP sidecar along, & keeps referenced items' absolute paths absolute. Reveal & Edit With shell out (open -R / open -a, explorer, xdg-open) & refuse protected items so a hidden original never leaves the vault through another app.
### services/decode.py + routers/render.py + services/editsvc.py (seed) + RAW in classify/thumbs/facesvc/visual/metasvc · RAW & a render endpoint
- refers-to: decode.open_image/raw_size/image_size/_raw_preview/_raw_full; render.render/render_image/source_of/clear_cached; editsvc.render_still (edit pipeline lands in P7); classify.IMAGE_EXTS raw entries; thumbs.ensure_thumb image branch; facesvc._load_image_bgr; visual.image_signature raw branch; metasvc._dims + apply raw dims; guard._any_token "/render"; importer.UPLOAD_EXTS
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

RAW through rawpy (MIT; its wheels bundle LibRaw, LGPL-2.1 or CDDL-1.0, dynamically linked & recorded in LICENSES.md) rather than a Pillow plugin: Pillow's TIFF reader would claim DNG, NEF, CR2 & ARW first & return the 160 px thumbnail IFD, which is exactly what metadata did before metasvc took RAW dimensions from LibRaw. Small requests (<= 1600 px, not develop) use the embedded preview & rotate it by the raw flip when it is still in sensor orientation; larger ones demosaic w/ the camera white balance, half size when the request allows. Every still decode now goes through decode.open_image, which also fixes a pre-existing face defect: cv2.imdecode ignores EXIF orientation, so sideways-stored iPhone portraits were scanned sideways. Removed from facesvc._load_image_bgr: `data = np.fromfile(path, dtype=np.uint8); img = cv2.imdecode(data, cv2.IMREAD_COLOR)` & its Pillow fallback block. Removed from thumbs.ensure_thumb: the direct `Image.open(src)` + `img.draft` + `ImageOps.exif_transpose` block (now decode.open_image after editsvc.render_still). /media/{id}/render serves any still as WebP at a width bucket, applying the edit list, cached on disk under cache/render keyed by edit hash; vault-protected items decode from the sealed bytes in memory & are never cached (no-store). The vault cookie is honored on /render as on /thumb & /file.
### db v5 + services/exifmeta.py + services/metasvc.py + services/query.py + routers/browse.py + libraryfs batches · metadata foundation
- refers-to: db.py MEDIA_V5_COLUMNS, MIGRATIONS[5], media_dict heavy-field pop; exifmeta.read_image/read_video/_apple_makernote; metasvc.apply/pair_live/backfill_job/on_applied; query.where/rule_sql/text_sql/page/parse_date_range; browse.py all routes + ensure_backfill; libraryfs.import_one tail, begin_batch/end_batch; importer.py batch calls; main.py router tuple + lifespan
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

One migration (v5) adds every column & table the parity phases need so a catalog migrates once: camera, lens, exposure, GPS & place columns, Apple content & burst ids, media-type flags, rating, label, reject, title, caption, alt text, edit list, trim, stacks, import batches, referenced flag, CLIP state, plus album folders, smart-album rules, stacks, CLIP vectors, labels, memories, groups, metadata templates & workflows. exifmeta reads with exifread (BSD-3-Clause; read_exif adapted from formlit, Apache-2.0) & fills gaps from Pillow; exifread has no Apple ContentIdentifier or BurstUUID tags, so _apple_makernote walks the "Apple iOS" IFD itself (offsets are relative to the maker note start). Videos read QuickTime tags via ffprobe (ISO 6709 location, content identifier, frame rate). metasvc.apply runs at import & from a resumable backfill (meta_ver), corrects a file-time capture date when EXIF has one (unless the date was adjusted), keeps a location once set, & pairs Live Photos by content id on every import path, not only ImageCaptureCore. Panorama = long/short >= 2.4, slo-mo = >= 100 fps, selfie = Apple front camera, portrait = Apple capture type. query.py is the one place filters, smart-album rules, advanced find, text search & sorting become SQL: keyset pagination over any sort column (cursor {v,id}), nested any/all groups, keyword rules include child keywords, stacks collapse to their top unless expanded. media_dict drops exif_json & iptc_json so 400-item pages stay small; /media/{id}/details returns them. Import batches are thread-local in libraryfs so the ImageCaptureCore lambda needs no new argument; empty batches are deleted at end_batch.
### app/mediacodecs.py + main.py + services/followon.py + services/housekeeping.py + dedupsvc carry_to_keeper · parity phase 1 fixes
- refers-to: mediacodecs.register (called once beside the FastAPI app); routers/system.py ocr_scan gate; routers/importer.py start_import run tail, import_upload tail, idevice_import run; services/dedupsvc.py carry_to_keeper + resolve loop; main.py lifespan housekeeping block; requirements*.txt pillow-heif pin
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

HEIC: pillow-heif was installed & frozen into the Mac build but never registered, so Pillow refused every HEIC (no size, file-time date, 404 thumbnail, skipped by faces, OCR & duplicates). mediacodecs.register() calls register_heif_opener() once per process; the module name avoids shadowing the stdlib codecs. The call sits after the import block so ruff E402 stays clean. OCR: the scan endpoint required tesseract even when RapidOCR was the engine; it now asks ocrsvc.engine_name(). Removed from ocr_scan: `if not ocrsvc.tesseract_path(): raise HTTPException(409, detail="tesseract is not on PATH (brew install tesseract)")`. Removed from import_upload: `if counts["imported"] and ocrsvc.engine_name(): jobs.start("ocr", ocrsvc.scan_job)`, replaced by followon.start_after_import, which every import path (folder, menu bar, drop, iPhone) now calls; it starts OCR & the face scan when their engines are ready & not already running, so new photos are read & grouped w/o a button, as Photos does. Duplicates: resolve now carries favorite & rating (max), title, caption, alt text & location (fill if empty), album membership & keywords to the keeper before trashing the others, & re-derives the keeper's private flag (+ vault reconcile) when it inherits a private album; faces are not moved bc their boxes belong to the other file. Purge: Recently Deleted expired only at engine start; housekeeping runs registered tasks every 6 h on a daemon thread & resets its sqlite connection per pass.
### app/db.py + oc_install · catalogs older than Live Photos crashed the engine at startup
- refers-to: app/db.py :: SCHEMA (idx_media_live_of removed), init_db (no version row starts at 1); oc_install :: fetch_model curl
- kind: rationale + removed code
- logged: zip v1.21.2 · 2026-09-18

Cause of round 68, from the owner's Terminal run of the bundled engine: init_db ran SCHEMA first, & SCHEMA held `CREATE INDEX IF NOT EXISTS idx_media_live_of ON media(live_of);`. For a catalog created before schema 4 the media table already exists without live_of, CREATE TABLE IF NOT EXISTS leaves it alone, & the index fails (sqlite3.OperationalError: no such column: live_of) before migration 4 can add the column. Present since the Live Photos round & in v1.16.0; it surfaced now because the owner's installed DAMp predated schema 4 (their later builds had failed on the Rust E0463 fixed in v1.17.0), so this was the first time the newer engine met their catalog. My round-68 replays missed it because their legacy library was created by v1.16.0, already at schema 4. Fix: the index lives only in migration 4 (after the column exists), & a catalog w/o a version row starts at 1 so every migration runs; duplicate-column errors were already tolerated, so re-running is harmless on fresh catalogs. The removed early-return stamped a version-less catalog as current w/o migrating it (removed: `conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,)); conn.commit(); return`). Verified: a real library made by the owner's v1.16.0 engine, downgraded to schemas 3, 2, 1 & no version row; the old code reproduces the owner's exact error on schema 3; the fixed code brings every copy to 4 w/ all columns, the index & all rows; the engine from source & freshly frozen starts from a schema-3 library in the old DAMp folder & prints its URL. oc_install: curl retries transient network & DNS failures (--retry 4 --retry-all-errors) & removes a partial model on final failure.
### desktop_entry.py + requirements_macos.txt + requirements.txt · engine failures made visible, build inputs pinned
- refers-to: desktop_entry.py :: _Tee, _open_log, main (calls _open_log after the selfcheck branch); requirements_macos.txt (all lines); requirements.txt (python-multipart, zip v1.21.0)
- kind: rationale
- logged: zip v1.21.1 · 2026-09-18

The desktop shell reads the engine's stdout & stderr only to find the http://127.0.0.1:<port> line & discards everything else, so when the engine dies before that line the owner sees a bare "failed to start" dialog & no cause (round 68). Frozen builds now tee both streams into ~/Library/Logs/DAM/engine.log (elsewhere: beside the library folder) w/ a start marker per launch, & faulthandler writes native crash stacks to the same file; the pipes the shell reads are unchanged. Verified in a frozen build: normal start (URL on the pipes & in the log), startup exception (full traceback & "Application startup failed" in the log). requirements_macos.txt was fully unpinned, so a Mac rebuild today silently pulled FastAPI 0.141.1, uvicorn 0.53.0 & Starlette 1.6.0 instead of the tested 0.121.1 / 0.32.1 / 0.49.3; it now carries the same pins as requirements.txt for every shared package (the pyobjc frameworks & rapidocr-onnxruntime stay Mac-only & unpinned; the pinned set resolves w/o conflict). Round 68 replays that did NOT reproduce the owner's crash, so they are not the cause: legacy DAMp library (vault passkey, hidden, deleted, expired trash, private album) adopted by the new engine from source & frozen; today's unpinned stack incl. OCR; the Mac worker-thread server path; the old DAMp engine still running on the same library.
### repo-wide · rename DAMp to DAM, part 3: copy & temp names
- refers-to: services/iccsvc.py start reason + both not-running errors; services/native_picker.py macOS, Windows, zenity & kdialog prompts; services/idevicesvc.py both temp prefixes
- kind: rationale
- logged: zip v1.18.2 · 2026-09-18

User-facing strings & temp folder names only; no behavior changed. With this round the rename is complete in code: the only DAMp/DAMP/damp strings left are the five migration constants (desktop_entry LEGACY_DATA_DIR, db LEGACY_CATALOG, config LEGACY_ENV_PREFIX, the second vaultcrypt WebKit cache id, main.rs KC_LEGACY), kept until every install has launched DAM once.
### repo-wide · rename DAMp to DAM, part 2: internal contracts
- refers-to: security.py LOCAL_HEADER/VAULT_HEADER + loopback message; config.py LEGACY_ENV_PREFIX + env() + library_root/models_dir/face_threshold/trash_retention_days; desktop_entry env block + selfcheck key + thread names; main.py title + DAM_DIST; importer.py DAM-CTRL lines + temp prefix + 501 message; trash.py KEYCHAIN_SERVICE + shell message + DAM-CTRL; jobs.py thread name; iccsvc DAMICCDelegate; tests conftest + vault headers in five test files; .env.example
- kind: rationale
- logged: zip v1.18.1 · 2026-09-18

Every contract moved on all sides in this one round so no zip ships half a rename: x-dam-local & x-dam-vault (engine, page, shell, both suites), DAM-CTRL (engine prints, shell filter), DAM_PORT (shell sets, desktop_entry reads), DAM_DIST/DAM_MODELS/DAM_LIBRARY (desktop_entry sets, config reads). config.env() prefers DAM_* & still honors a DAMP_* value when the new name is unset (dev shells, old .env files); desktop builds never need the fallback bc desktop_entry sets the DAM_* names itself. Verified live: new header 200, old header 403, the engine prints DAM-CTRL TRAYSET 1 exactly as the shell filter expects. The ImageCaptureCore delegate class registers at runtime, so its rename is invisible outside the process. Part 3 still owes the iccsvc, idevicesvc & native_picker copy & temp prefixes.
### repo-wide · rename DAMp to DAM, part 1: data adoption
- refers-to: desktop_entry.py :: LEGACY_DATA_DIR + default_library; db.py :: LEGACY_CATALOG, _adopt_lock, _adopt_legacy_catalog, connect head; config.py :: db_path; vaultcrypt.py :: WEBKIT_CACHE_IDS; tests/test_v030_features.py health assertion
- kind: rationale
- logged: zip v1.18.0 · 2026-09-18

The app is now DAM, so the desktop library lives in Application Support/DAM & the catalog is dam.db. Both are adopted, never copied: default_library renames the legacy DAMp folder when DAM does not exist yet (atomic on one volume, contents & vault untouched), & connect moves damp.db w/ its -wal & -shm under a lock before the first sqlite connection, so an uncheckpointed WAL is never orphaned & concurrent first connects cannot race. The WebKit purge covers both bundle ids so the old app's cache goes too. The legacy names that remain (LEGACY_DATA_DIR, LEGACY_CATALOG, the second cache id) are required for migration & can be dropped once every install has launched DAM. Verified on the previous round's encrypted library: catalog adopted, old passkey unlocks, hidden item & its encrypted thumbnail still open.
### app/vaultcrypt.py · encryption at rest for hidden, deleted & private media
- refers-to: vaultcrypt (new: key pair, album identities, Sealed blob format, reconcile/purge, opener/thumb_bytes, token_response, sweeper, startup); guard._any_token + ensure_visible tail; trash vault_setup/vault_unlock/bio_unlock/unhide/restore/_purge_row; mediaapi hide_media/trash_media/media_thumb/media_file; albums create_album/unlock_album/album_detail/_refresh_private_flag; main lifespan; libraryfs._dest_for; desktop_entry selfcheck
- kind: rationale
- logged: zip v1.17.0 · 2026-09-18

The user found every hidden & deleted file in plain form under library/originals. Protection had been database flags only, & the leak was wider: plain thumbnails in cache/thumbs, face crops in cache/faces, OCR text in the catalog, file/thumb endpoints that never asked for the vault token on hidden or deleted rows, & long-lived WebKit caching. Design: X25519 vault key pair; the public half seals, so hide/delete/private-add encrypt w/o any unlock; the private half is stored provisionally until the first vault setup/unlock, then only wrapped by scrypt(passkey, n=2^15) + AES-GCM. Own-passkey albums get their own pair, keyed in vault_albums by (album_id, album created_ts) because sqlite reuses album ids; each album private key is also sealed to the vault key, so the vault passkey remains the master that opens every album. Items carry one random content key sealed to one home ("v" or "a:<key_id>"); home follows the flags (hidden/trashed win, then the lowest own-passkey private album, then the vault). Blob format: 16-byte header (magic, version, chunk log2, 8-byte nonce prefix) + 64 KiB AES-GCM chunks whose AAD binds header, index & a last-chunk flag, so truncation fails & byte ranges decrypt independently (video seeking). media.rel_path stays stable while vaulted (API contract, caught by the trash test); _dest_for now skips names still owned by a vaulted row so imports cannot collide. OCR text & face_state ride inside the encrypted meta; ocr_text is '' & face_state 2 while vaulted so both scans skip. Transitions run under one RLock; read paths (protected/is_vaulted/opener/thumb_bytes) stay lock-free so a long video encryption never stalls library thumbnails. Cookies: img & video cannot send headers, so unlock responses set dam_vt / dam_at_<id> (HttpOnly, SameSite=Strict, Path=/api/media) & _any_token honors them only on /thumb & /file. Sweeper: every 15 s (woken on unlock) it seals anything protected but plain, re-homes or decrypts once keys are open, scrubs plain thumbs & face crops of vaulted ids, & forgets orphan album identities; it resets its sqlite connection per sweep & stops if the library root changes (the full suite exposed a cross-library race inside one process). WebKit purge runs only in the frozen macOS engine. Local imports of vaultcrypt inside handlers are deliberate: no import-block edits & no cycle risk. tests/test_trash.py now fails by design at `assert os.path.isfile(on_disk)` after trashing: it encodes the old keep-plain behavior.

### app/vault.py · _secret
- refers-to: vault.py :: _secret, module head
- kind: removed-code
- logged: zip v1.17.0 · 2026-09-18

```python
def _secret() -> bytes:
    stored = setting_get("token_secret")
    if stored is None:
        stored = base64.b64encode(os.urandom(32)).decode()
        setting_set("token_secret", stored)
    return base64.b64decode(stored)
```

Persisted the token signing secret so unlock tokens survived engine restarts. Replaced by a per-process `_SECRET` bc a token must never outlive the in-memory vault key it stands for. Existing token_secret rows are now unused.

### app/services/iccsvc.py + db v4 · device browsing, selective import, delete-after, Live Photo pairing
- refers-to: contents/device_thumb/close_device; gen guard; requestThumbnail + Quartz ImageIO encode; requestDeleteFiles; MIGRATIONS[4] live_video_id/live_of; libraryfs.link_live; guard.ensure_visible parent check; trash._purge_row cascade; 15 query sites gaining live_of IS NULL
- kind: rationale
- logged: zip v1.16.0 · 2026-07-31

The three recorded next steps landed together. Browsing: the session now stays open while the Import page browses (idempotent open, explicit /idevice/session/close skipped while an import job runs); every catalog snapshot carries a generation & downloads/deletes/thumbs validate it, so a mid-browse catalog change errors cleanly instead of importing the wrong indexes. Thumbs ride ICC's own requestThumbnail (CGImage -> JPEG via Quartz ImageIO, cached per gen; Quartz missing degrades to kind glyphs, never errors). Selective import filters the snapshot by keys; downloads land in per-key subdirs under ICSaveAsFilename so library names stay the camera's own (the v1.15.0 key-prefix leak died in review here, caught by the roundtrip test). Delete-after is opt-in, runs once at job end, & only over items whose every file imported or was already in the library (duplicate = safely present), so a failed download can never cost the only copy; deletion errors report, never fail the job. Live Photos: the ICC sidecar signal (ICSavedAncillaryFiles) is authoritative at import time, so pairing needs no heuristics: link_live stamps photo.live_video_id & companion.live_of inside one guarded update pair; companions leave every general query (media/search/summary/people/dedup/system counts/faces/ocr scans, 15 sites), stream through guard.ensure_visible only as visibly as their parent (private cascades at read time, one chokepoint), & purge cascades both directions in trash._purge_row. Folder-import pair detection (stem heuristics) is deliberately NOT built: the sidecar signal is exact, the heuristic guesses; recorded as the honest boundary.

### app/services/iccsvc.py · native iPhone import (ImageCaptureCore)
- refers-to: iccsvc (new); idevicesvc facade; desktop_entry main-thread split; requirements_macos + build collect flags; Entitlements.plist + Info.plist usage string
- kind: correction + rationale
- logged: zip v1.15.0 · 2026-07-31

The hardware test failed: the iPhone never connected. Root cause found upstream, not in our code: requirements_macos.txt carried UNPINNED pymobiledevice3, & its 8.0.0 (2026-03-05) made the entire API async (list_devices/create_using_usbmux/AfcService all coroutines), so our sync calls returned un-awaited coroutine objects & device listing raised on every poll. Two deeper problems surfaced w/ it: the GPL-3.0-or-later package was being bundled into the MIT app unledgered (banned for distributed builds by the licensing policy), & the AFC path was never the Photos.app mechanism anyway. Rebuilt on Apple's own ImageCaptureCore via pyobjc-framework-ImageCaptureCore (MIT): ICDeviceBrowser discovers cameras (mask Camera|Local), isAccessRestrictedAppleDevice maps locked/untrusted (iOS 26 Wired Accessories guidance in the error strings), session -> complete content catalog -> per-file requestDownloadFile w/ sidecars into a temp dir feeding libraryfs.import_one(move=True), so sha dedup/HEIC/posters/faces/OCR ride the existing pipeline. ICC delivers delegate callbacks on the process MAIN thread only: desktop_entry now pumps the CFRunLoop on the real main thread (AppHelper.runConsoleEventLoop) & uvicorn moved to a worker thread on macOS w/ a join-then-exit watcher; jobs threads talk to the main thread over callAfter + threading.Events. The bridge is injectable (_bridge_factory) so the whole orchestration is fake-tested off-macOS (3 new tests). pymobiledevice3 left the freeze; the AFC code path survives as an optional dev fallback that self-disables w/ a reason on 8+ (async-only). Rule extracted: an unpinned dependency in a freeze file is a time bomb; freeze sets either pin or get replaced by platform frameworks.

### app/services/ocrsvc.py · model lifecycle
- refers-to: release_engine; capped RapidOCR threads; _rapid_available; scan_job finally + per-item yield
- kind: correction
- logged: v1.13.9 · 2026-07-26

Three lifecycle sins made post-scan DAMp heavy: sessions lived forever after a scan (idle memory), onnxruntime defaulted to every core during scans (thumb starvation), & engine_name instantiated the model just to answer a status poll (so the search card silently re-loaded ONNX after every release). Now: find_spec answers availability w/o sessions; construction caps threads (2 intra / 1 inter, TypeError-guarded for older wheels); the scan loop yields 2ms per item; & a finally releases everything + gc.collect(). Rule extracted: heavyweight engines get an explicit lifecycle (acquire for the job, release after), & status endpoints must never pay acquisition cost.

### app/services/ocrsvc.py · the bundled text model
- refers-to: _rapid_engine/engine_name/_extract; importer autostart condition; requirements + collect-all
- kind: correction + rationale
- logged: v0.13.3 · 2026-07-26

Tesseract-only OCR was the wrong tool for photographs (document engine, PATH-dependent, user-installed); text-in-image search read as broken. RapidOCR (PP-OCR det+rec over onnxruntime, models inside the wheel, fully offline) is now the primary engine, lazily constructed once; tesseract remains only as fallback. _extract converts via PIL to RGB numpy so HEIC rides pillow-heif. Smoke-proof in-container: the user's exact failing query text detected at 0.98. Correction owned here: v0.11.0's claim that pymobiledevice3 was collected into the freeze was false (silent no-op edit); found while wiring this model's collect, both now present & grep-verified.

### app/routers/importer.py · multi-root imports + menubar pref
- refers-to: ImportIn.paths; /system/menubar GET/POST + DAMP-CTRL TRAYSET
- kind: explainer
- logged: v0.13.3 · 2026-07-26

The tray picker returns many selections, & the jobs runner reuses a running job of the same kind, so per-file POSTs would drop everything after the first: /import now accepts paths & walks all roots inside ONE job. The menubar preference lives engine-side (settings table) so the shell can ask at startup; toggling prints a TRAYSET control line, the same channel Touch ID uses.

### app/routers/importer.py · /import/upload
- refers-to: import_upload; UPLOAD_EXTS; python-multipart requirement
- kind: explainer
- logged: v0.13.1 · 2026-07-26

Dropped files arrive as blobs (webviews expose no paths), so upload is the only correct transport: each part streams to a temp dir & feeds libraryfs.import_one(move=True), inheriting dedup/HEIC/poster/OCR behavior instead of duplicating it. Extension allowlist guards the endpoint (MIME from webviews is unreliable for HEIC); rejects count as skipped, per-file failures never abort the batch.

### app/routers/people.py + db v3 · locked covers
- refers-to: cover endpoints; people.cover_locked; refresh_cover early return; MIGRATIONS[3]
- kind: rationale
- logged: v0.12.0 · 2026-07-26

Person covers are cover_face_id (a face crop), so Set as Cover resolves the chosen image to that person's best face IN that image & locks the choice; refresh_cover returns early when locked, making the manual pick permanent through rescans & rebuilds. Schema v3 is a real migration this time (fresh schema + ALTER for v2 dbs); the first edit landed the column on the wrong table (albums also has cover_media_id) & the anchor discipline caught it before shipping · noted bc that near-miss is exactly why the asserts exist.

### app/services/idevicesvc.py · iPhone import over usbmuxd + AFC
- refers-to: idevicesvc; importer /idevice endpoints; requirements + --collect-all pymobiledevice3
- kind: rationale
- logged: v0.11.0 · 2026-07-26

Researched path: macOS ships usbmuxd, so pymobiledevice3 (pure python) reaches lockdown + AFC w/ no kernel extensions, no FUSE, no Image Capture private frameworks. The service walks /DCIM recursively for media extensions, pulls each file to a temp dir (pull() when present, get_file_contents fallback), & feeds libraryfs.import_one(move=True): sha dedup, HEIC decode, posters & follow-on jobs all come free from the existing pipeline. Factories (_list/_lockdown/_afc) are injectable, which is how the fake-device test exercises listing, a two-file import & the dedup re-import w/o hardware. Job phases stay owned by the runner; sub-progress uses a separate stage key after colliding w/ the runner's phase semantics during development. Deliberate v1 boundaries, recorded: never delete from the device; Live Photos land as their photo+video pair.

### app/routers/trash.py · the bio control channel
- refers-to: SHELL/PENDING; /internal/shell/hello, /internal/bio/pending, /internal/bio/result; /vault/bio/unlock; keychain endpoints reimplemented; removed-code: the subprocess security-CLI block
- kind: rationale + removed-code
- logged: v0.10.0 · 2026-07-26

Removed the CLI keychain (add/find-generic-password via subprocess): its items ACL-trust the security tool, not DAMp, & GUI-child quirks made it undiagnosable remotely. The engine now brokers instead of touching secrets storage: it prints a nonce'd DAMP-CTRL line, parks the request on an Event (40s), & verifies whatever passkey the shell returns against the vault hash before issuing a token, so a local process forging /internal/bio/result gains nothing w/o the real passkey. /vault/keychain/status|enable keep their names (frontend & Settings unchanged) but are backed by shell state & the store roundtrip; pending passkeys live in-process only & are popped on completion. Three threaded tests lock hello/unlock/store.


### app/services/thumbs.py · eviction, the missing half of the placeholder fix
- refers-to: THUMB_VER 3; stale _ph cleanup in the success path
- kind: correction
- logged: v0.8.0 · 2026-07-25

v0.7.0 stopped placeholders from occupying real thumb paths but evicted nothing: ensure_thumb's existence check happily returned every placeholder v0.6.0 had already written, so the user's symptom survived two fixes. The version bump in the filename is the eviction (old files orphan; regeneration is lazy & cheap), chosen over content-sniffing cached JPEGs, which would be fragile. Rule extracted for future fixes: a caching bug is not fixed until existing bad entries are invalidated.

### app/dedup/visual.py + ocrsvc.py · launchd PATH & brew discovery
- refers-to: visual._find_tool, ffmpeg_path, ffprobe_path; ocrsvc tesseract discovery
- kind: rationale
- logged: v0.7.0 · 2026-07-25

macOS GUI apps inherit launchd's minimal PATH, not the user's shell PATH, so shutil.which() alone finds nothing Homebrew installs · the exact "brew install tesseract but it isn't working" report, & the hidden reason video posters only worked in terminal-launched sessions. _find_tool() falls back to /opt/homebrew/bin, /usr/local/bin & /opt/local/bin. Chosen over mutating PATH or launchctl config bc it needs no user action & survives repackaging.

### app/services/thumbs.py · placeholders must never occupy the real path
- refers-to: ensure_thumb tail; _placeholder_poster; importer poster pre-warm
- kind: correction
- logged: v0.7.0 · 2026-07-25

The v0.6.0 placeholder wrote to the real thumb path on extraction failure, so one bad moment (ffmpeg missing at first request) cached a permanent placeholder · seen in the wild at one size bucket while another bucket had a real frame. Placeholders now render to {id}_{size}_ph.jpg, the real path stays empty until extraction succeeds, & every later request retries. Imports pre-warm the 384 poster so first paint is real. The placeholder art also lost its triangle (it read as a play button).

### app/services/thumbs.py · correction: the v0.4.0 first-frame claim was false
- refers-to: thumbs.py :: THUMB_VER, ensure_thumb video branch, _placeholder_poster
- kind: correction + removed-code
- logged: v0.6.0 · 2026-07-25

v0.4.0's notes claimed first-frame seeks w/ versioned thumb names; the edits had targeted non-existent text & silently no-opped, so v0.4.0-v0.5.0 actually shipped the original block:

    subprocess.run([ffmpeg, ..., "-ss", "1", ...], check=True)  # single 1s seek, unversioned {id}_{size}.jpg names

Now real: THUMB_VER=2 in filenames (old caches naturally orphaned), seeks 0 then 0.5, & a generated dark poster when ffmpeg is missing or extraction fails, so the tile never 404s. The regression test exercises the poster path. Root-cause process fix: all scripted edits assert anchors (see checklist Round 4 corrections).

### app/db.py · exn() rowcount helper
- refers-to: db.py :: exn; facesvc.merge_people; people.reassign_media
- kind: rationale
- logged: v0.6.0 · 2026-07-25

ex() returns lastrowid or rowcount, correct for INSERTs but meaningless for UPDATE counting (lastrowid is the previous insert). Moved-face counts (merge, reassign-media) now use exn() = cursor.rowcount. Kept ex() untouched to avoid disturbing every insert call-site.

### app/services/facesvc.py · rebuild that cannot lose names
- refers-to: facesvc.rebuild_people
- kind: rationale
- logged: v0.6.0 · 2026-07-25

Deleting all people on rebuild was correct for clustering & unacceptable for users (Round 4 item 3). New contract: named people are permanent anchors. Before re-clustering, top-EXEMPLAR_K embeddings per named person are captured; their rows survive; the clusterer is pre-seeded w/ those exemplars under the existing ids so re-scanned faces flow back to them; only unnamed groups are rebuilt from scratch. Threshold changes therefore re-shape anonymous clusters w/o ever touching a name.


## Org-navi-map

```
backend/
├── app/
│   ├── config.py            version + library/model paths + env knobs
│   ├── security.py          loopback-only middleware, local + vault headers
│   ├── db.py                schema, thread-local sqlite, query helpers
│   ├── vault.py             scrypt passkeys, HMAC scope tokens
│   ├── jobs.py              background thread job runner + registry
│   ├── ffmpeg_fetch.py      first-run download of the pinned LGPL ffmpeg, PATH order
│   ├── ffmpeg_record.py     release and per-file SHA-256 pins for that download
│   ├── main.py              app wiring, lifespan init, static dist mount
│   ├── dedup/
│   │   └── visual.py        vendored deduplakit signature core (trimmed)
│   ├── services/
│   │   ├── classify.py      ext/mime maps, screenshot + screenrec heuristics
│   │   ├── mediainfo.py     Pillow EXIF + ffprobe metadata + fs times
│   │   ├── libraryfs.py     sha256, gather, YYYY/MM import, exact-skip
│   │   ├── thumbs.py        bucketed JPEG thumbs, image + video posters
│   │   ├── facesvc.py       YuNet + SFace, video frames, clustering, crops
│   │   └── dedupsvc.py      exact + visual sets, keeper verify, resolve
│   └── routers/
│       ├── guard.py         visibility + vault checks for handlers
│       ├── system.py        health, job status, library summary counts
│       ├── importer.py      import job endpoint
│       ├── mediaapi.py      list/filters/summary, thumb, ranged file, flags
│       ├── albums.py        CRUD, items, private unlock tokens
│       ├── people.py        scan job, clusters, person media, face thumbs
│       ├── trash.py         vault setup/unlock, trash list, restore, purge
│       └── dedup.py         scan job, sets, resolve, resolve-exact
├── tests/                   pytest suite (core, vault, trash, dedup, faces)
├── models/                  ONNX face models (installer-downloaded, ignored)
├── requirements.txt         runtime deps
├── requirements-dev.txt     pytest, ruff, pillow-heif, httpx
├── ruff.toml                lint select pin (E4/E7/E9/F)
├── .env.example             env knob reference
├── desktop_entry.py         PyInstaller entry: selfcheck, env defaults, port 0
├── requirements_macos.txt   unpinned runtime set for the freeze venv
├── oc_install               venv + deps (darwin branch) + model fetch
└── boot_backend             uvicorn 127.0.0.1:8000
```

## Table of contents

- [app/config.py](#appconfigpy)
- [app/security.py](#appsecuritypy)
- [app/db.py](#appdbpy)
- [app/vault.py](#appvaultpy)
- [app/jobs.py](#appjobspy)
- [app/dedup/visual.py](#appdedupvisualpy)
- [app/services/classify.py](#appservicesclassifypy)
- [app/services/mediainfo.py](#appservicesmediainfopy)
- [app/services/libraryfs.py](#appserviceslibraryfspy)
- [app/services/thumbs.py](#appservicesthumbspy)
- [app/services/facesvc.py](#appservicesfacesvcpy)
- [app/services/dedupsvc.py](#appservicesdedupsvcpy)
- [app/routers/guard.py](#approutersguardpy)
- [app/routers/mediaapi.py](#approutersmediaapipy)
- [app/routers/albums.py](#approutersalbumspy)
- [app/routers/trash.py](#approuterstrashpy)
- [app/routers/people.py](#approuterspeoplepy)
- [app/routers/dedup.py](#approutersdeduppy)
- [app/main.py](#appmainpy)

## app/config.py

### app/config.py · library_root and friends
- refers-to: config.py :: library_root / models_dir / face_threshold / trash_retention_days
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Paths are functions, not module constants, so tests can monkeypatch `DAMP_LIBRARY` per-test and every read sees the live env. Default library lives inside the repo for dev friendliness; point the env var at a real disk for daily use.

## repo-wide

### repo-wide · rename photolakit to DAMp
- refers-to: all backend files
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Mechanical sweep before first ship: env vars PHOTOLAKIT_* to DAMP_*, headers x-photolakit-local/vault to x-damp-local/vault, catalog file photolakit.db to damp.db, install script name to DAMp_oc_install, job thread prefix & API title to DAMp. Behavior unchanged; any pre-rename library folder keeps working by pointing DAMP_LIBRARY at it & renaming the .db file.

## app/security.py

### repo-wide

### repo-wide · rename photolakit to DAMp
- refers-to: all backend files
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Mechanical sweep before first ship: env vars PHOTOLAKIT_* to DAMP_*, headers x-photolakit-local/vault to x-damp-local/vault, catalog file photolakit.db to damp.db, install script name to DAMp_oc_install, job thread prefix & API title to DAMp. Behavior unchanged; any pre-rename library folder keeps working by pointing DAMP_LIBRARY at it & renaming the .db file.

## app/security.py · local_only_guard
- refers-to: security.py :: local_only_guard
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Vendored from deduplakit w/ renamed headers. Three rings: client IP must be loopback, Host header must match the localhost allowlist (DNS-rebinding guard), and every mutating /api call must carry `x-damp-local: 1` (cross-site form posts cannot set custom headers). `x-damp-vault` is declared here so the whole header surface lives in one file.

## app/db.py

### app/db.py · SCHEMA
- refers-to: db.py :: SCHEMA
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Single executescript w/ IF NOT EXISTS everywhere + a schema_meta version row for future migrations. `media.private` is denormalized (derivable from album membership) bc every hot query filters on it; albums.py keeps it in sync. `UNIQUE(sha256, size)` is the import-time exact-dupe gate. Trash is `trashed_ts` + `trash_reason`, never a file move.

### app/db.py · thread-local connections
- refers-to: db.py :: connect / reset_thread_conn
- kind: rationale
- logged: v0.1.0 · 2026-07-25

One sqlite connection per thread (uvicorn workers + job threads), WAL + busy_timeout for cross-thread writes. `reset_thread_conn` exists for tests (fresh library per test) and for job threads to close their connection on exit.

## app/vault.py

### app/vault.py · token scheme
- refers-to: vault.py :: issue_token / check_token
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Tokens are `scope|expiry|hmac` (30 min TTL) signed w/ a persisted random secret in settings, so unlocks survive server restarts but nothing secret ever reaches the browser beyond the opaque token. `check_token` accepts the requested scope or the `vault` scope: the vault passkey is the master key that opens trash and every private album. scrypt n=2^14 r=8 p=1 matches OWASP interactive-login guidance; per-album hashes and the vault hash share the same helpers.

## app/jobs.py

### app/jobs.py · run wrapper
- refers-to: jobs.py :: start
- kind: warning-context
- logged: v0.1.0 · 2026-07-25

Job threads must call `reset_thread_conn()` in finally: sqlite connections are thread-local and a dangling connection from a finished job thread would hold the WAL file handle. One job per kind runs at a time via `running()` checks in the routers.

## app/dedup/visual.py

### app/dedup/visual.py · vendor trim
- refers-to: dedup/visual.py :: module head + removed tail
- kind: removed-code
- logged: v0.1.0 · 2026-07-25

Vendored verbatim from deduplakit's engine, then trimmed to the standalone signature core (constants, dHash/pHash/color helpers, image_signature, video_signature, ffmpeg/ffprobe discovery, similarity). Removed the deduplakit-coupled imports:

```python
from ..services.kinds import classify
from .gates import GateController
from .models import DupRecord, DupSet, FileRec, ScanCancelled, Stats
```

and everything from `_created_key` downward, incl. the orchestration entrypoint:

```python
def find_visual_sets(
    candidates: List[FileRec],
    ...,
    stats: Stats,
    ...,
    gate: Optional[GateController] = None,
) -> List[DupSet]:
```

plus its helpers `_created_key`, `_aspect_bucket`, `_cluster`, `_keeper_order`, `_verify_against_keeper`. Those depended on deduplakit's FileRec/DupSet/Stats/gates; DAMp reimplements the clustering against catalog rows in services/dedupsvc.py. Unused `logging` / `Counter` imports went w/ them; `threading` stays for `_DCT_LOCK`. Engine constants (DEFAULT 94, FLOOR 58, weights .42/.38/.20, VIDEO_SAMPLE_POINTS) are untouched so behavior matches deduplakit v0.11.0.

## app/services/classify.py

### app/services/classify.py · screenshot heuristics
- refers-to: classify.py :: looks_screenshot / looks_screen_recording
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Honest rule-based detection, not ML: filename regex (screenshot / screen recording / rpreplay) plus "PNG w/o an EXIF capture time" for screenshots, since cameras write EXIF and screen captures do not. Apple's Receipts/Handwriting/Illustrations/Documents need a real document classifier; deliberately absent rather than faked (see BUILD_NOTES gaps).

## app/services/mediainfo.py

### app/services/mediainfo.py · capture time precedence
- refers-to: mediainfo.py :: image_meta / video_meta / fs_created
- kind: explainer
- logged: v0.1.0 · 2026-07-25

created_ts precedence: EXIF DateTimeOriginal (then DateTime) for images, container creation_time for videos, else st_birthtime, else mtime; created_src records which won. Dimensions are read post exif_transpose so portrait iPhone shots grid correctly.

## app/services/libraryfs.py

### app/services/libraryfs.py · import_one
- refers-to: libraryfs.py :: import_one / _dest_for
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Full-file SHA-256 (not partial) bc the hash is the library's permanent integrity id and the exact-dedup key. Destination is `originals/YYYY/MM/<name>` from capture time w/ `-N` uniquifying on collision; rel_path stored so the whole library relocates by moving one folder + the env var.

## app/services/thumbs.py

### app/services/thumbs.py · size buckets
- refers-to: thumbs.py :: SIZES / ensure_thumb
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Requests bucket to 192/384/768 so the cache holds at most three renditions per item regardless of UI zoom values. Pillow `draft` short-circuits JPEG decode at reduced scale; videos use `ffmpeg -ss 1` (skips black first frames) w/ cleanup of partial files on failure.

## app/services/facesvc.py

### app/services/facesvc.py · engine choice and licensing
- refers-to: facesvc.py :: DETECT_MODEL / EMBED_MODEL / status
- kind: rationale
- logged: v0.1.0 · 2026-07-25

YuNet (MIT) + SFace (Apache-2.0) from opencv_zoo: permissive licenses, tiny (233 KB + 37 MB), run headless via opencv-python-headless (Apache-2.0). Deliberately avoided dlib/face_recognition bc its landmark model carries research-only training-data terms. cv2/numpy imports are guarded so the whole app runs w/o them; `status()` tells the UI exactly what is missing.

### app/services/facesvc.py · clustering threshold
- refers-to: facesvc.py :: _Clusterer.assign
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Incremental centroid assignment: cosine vs each person centroid (normalized running sum), best >= threshold joins and updates the centroid, else a new person row. Threshold 0.42 vs the SFace paper's 0.363 verification threshold: centroid matching compounds errors (one wrong join drags the centroid), so precision is favored; `DAMP_FACE_THRESHOLD` exposes it. Real-face quality untested in-container (no real faces available); mechanics verified w/ noise (0 detections) + a fabricated detection row producing a 128-d embedding.

### app/services/facesvc.py · video frames
- refers-to: facesvc.py :: _video_frames
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Reuses deduplakit's VIDEO_SAMPLE_POINTS (12/30/50/70/88 percent) so a clip contributes five face-scan frames at the same story beats the dedup engine fingerprints, but decoded at 640 px wide rawvideo (dedup uses 64 px, far too small for faces). Height computed from probe dims rounded to even for yuv-safe scaling.

### app/services/facesvc.py · image loading
- refers-to: facesvc.py :: _load_image_bgr
- kind: explainer
- logged: v0.1.0 · 2026-07-25

cv2.imdecode over np.fromfile handles non-ASCII paths; HEIC falls back to Pillow (pillow-heif when installed) converted RGB to BGR. MAX_EDGE 1024 downscale before detection: YuNet degrades past ~1k anyway and it bounds SFace crops + memory.

## app/services/dedupsvc.py

### app/services/dedupsvc.py · clustering adapter
- refers-to: dedupsvc.py :: _cluster / _verified / scan_job
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Reimplements deduplakit's set-building against catalog rows: candidates group by (kind, aspect bucket rounded to width/height*10), membership probes the first 3 of a cluster, then every cluster is re-verified pairwise against the elected keeper (sort: pixels desc, size desc, created asc, id asc) w/ one recluster pass for evicted strays. Exact sets come straight from a DB GROUP BY on (sha256, size), zero hashing cost, since import stores full hashes. Private items are excluded from scans entirely: surfacing a private photo in a public dedup pair would leak the vault. Signatures are recomputed per scan; persistence is a listed roadmap item.

### app/services/dedupsvc.py · resolve reversibility
- refers-to: dedupsvc.py :: resolve
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Resolving never deletes: losers get `trashed_ts` + `trash_reason='duplicate:<set>'` so the trash UI labels them and a restore fully undoes a bad resolution. Keeper can be overridden per call (`keep_media_id`).

## app/routers/guard.py

### app/routers/guard.py · ensure_visible
- refers-to: guard.py :: ensure_visible / can_view_private
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Single choke point for private media access: vault-scope token sees everything; otherwise any album-scope token for an album containing the item works. Used by every media-level endpoint (meta, thumb, file, flags, trash) so there is no path to bytes of a private item w/o an unlock.

## app/routers/mediaapi.py

### app/routers/mediaapi.py · keyset cursors
- refers-to: mediaapi.py :: list_media / FILTERS
- kind: rationale
- logged: v0.1.0 · 2026-07-25

(sort_field, id) keyset pagination instead of OFFSET: stable under concurrent imports/trashes and O(log n) at any depth, which OFFSET is not at 75k items. FILTERS maps each preset to a WHERE fragment + ORDER BY; the cursor field is derived from the ORDER BY so recently_saved/viewed page on their own timestamps.

### app/routers/mediaapi.py · range streaming
- refers-to: mediaapi.py :: media_file / _parse_range / _iter_range
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Byte-range implementation adapted from deduplakit's files router: suffix ranges, open-ended ranges, 416 w/ `Content-Range: bytes */size` on invalid, 512 KiB chunks. Required for `<video>` seeking; browsers refuse to scrub w/o Accept-Ranges + 206.

## app/routers/albums.py

### app/routers/albums.py · private flag refresh
- refers-to: albums.py :: _refresh_private_flag
- kind: rationale
- logged: v0.1.0 · 2026-07-25

`media.private` is recomputed from "is this item in any private album" on every add/remove/album-delete, incl. album deletion restoring items to public. Creating a private album requires either its own passkey or an existing vault passkey (422 otherwise) so a private album can never exist w/ no key that opens it.

## app/routers/trash.py

### app/routers/trash.py · purge model
- refers-to: trash.py :: purge_expired / _purge_row
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Startup purge deletes rows past retention: unlink original, then faces / album_items / media_keywords / dup_members / media rows, so nothing dangles. Every trash read/mutation requires a vault token; setup is 409-guarded so the passkey cannot be silently replaced over HTTP.

## app/routers/people.py

### app/routers/people.py · listing filter
- refers-to: people.py :: list_people
- kind: explainer
- logged: v0.1.0 · 2026-07-25

People counts only faces on visible media (not trashed, not private), so trashing or privatizing photos updates the People page w/o rescanning. min_faces defaults to 1; sorted by media count desc for a Photos-style ordering.

## app/routers/dedup.py

### app/routers/dedup.py · threshold bounds
- refers-to: dedup.py :: ScanIn
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Threshold is validated ge FLOOR_SIMILARITY (58) le 100 straight from the vendored engine constants, so the API cannot request a similarity the engine defines as noise.

## app/db.py (v2)

### app/db.py · schema v2 migration
- refers-to: db.py :: SCHEMA_VERSION / MIGRATIONS / init_db
- kind: explainer
- logged: v0.3.0 · 2026-07-25

v2 adds media.hidden, media.ocr_text & people.hidden via an in-place ALTER migration keyed off schema_meta.version, tolerant of duplicate-column reruns. Every general visibility clause across routers & services is now `trashed_ts IS NULL AND private=0 AND hidden=0`, making Hidden a first-class tier like Photos: excluded from Library, search, People stats, Collections counts & dedup scans until explicitly unhidden from the vault-gated page.

## app/services/classify.py (v2)

### classify.py · dims-gated screenshot heuristic
- refers-to: classify.py :: SCREEN_DIMS / looks_screenshot
- kind: rationale
- logged: v0.3.0 · 2026-07-25

The v0.1 rule (any PNG w/o EXIF time) swallowed exports & artwork, per real-usage feedback. Now a screenshot is: the classic filename pattern, OR a PNG w/o EXIF whose exact pixel dims (either rotation) sit in a curated set of Mac/iPhone/iPad screen resolutions. main.py runs a one-time startup reclassify over existing rows (settings classify_ver=2) using created_src=='exif' as the stored EXIF-presence signal, so already-imported libraries heal themselves.

## app/services/facesvc.py (dominance)

### facesvc.py · dominance model
- refers-to: facesvc.py :: MIN_FACE_AREA / _Clusterer / refresh_cover / unassign_face / merge_people
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Tiny background faces polluted groups: detections under 0.4 percent of frame area are skipped, & each face carries dominance = quality x sqrt(area). Centroids are quality-WEIGHTED sums so strong crops steer matching (the requested best-face-crops training db, realized as weighted exemplars over every stored embedding); covers are the argmax dominance face, recomputed in Python (sqlite sqrt is not guaranteed) on every assign/unassign/merge. unassign_face deletes newly-empty people & is the correction loop: removing a wrong face immediately reshapes that person's centroid for future scans.

## app/services/thumbs.py (v2)

### thumbs.py · first-frame posters & cache versioning
- refers-to: thumbs.py :: THUMB_VER / thumb_path / video branch
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Video posters now come from frame 0 w/ a 0.5s retry for encoders whose first packet is not a clean keyframe. THUMB_VER landed in the filename so every existing poster (cut at 1s in earlier builds) regenerates lazily on next view w/o a migration pass or stale-file cleanup.

## app/services/facesvc.py (accuracy)

### facesvc.py · exemplar verification & quality gates
- refers-to: facesvc.py :: face_threshold / MIN_JOIN_QUALITY / MIN_NEW_PERSON_QUALITY / _exemplar_ok / rebuild_people / assign_face
- kind: rationale
- logged: v0.4.0 · 2026-07-25

Too-generic grouping had three causes, each gated: the 0.42 default cosine was loose (now 0.55, w/ precedence setting > env > default; the earlier attempt edited a same-named function in config.py & silently no-opped · the settings-aware getter now lives here & shadows the env helper); centroid-only matching let averages drift (a candidate must now ALSO hit one of the person's 10 best-quality stored crops within 0.03 of threshold · the best-face-crops db doing real work at assign time); & low-quality detections founded junk people (under 0.82 quality can join but never create; under 0.6 does not even update centroids). rebuild_people re-clusters every stored embedding quality-desc at the chosen strictness in seconds w/o re-detection, persisting the threshold; names & manual merges reset, which the UI states before running. assign_face powers per-crop reassignment incl. new-person creation w/ cover recompute on both sides.

## app/routers/trash.py (keychain + hidden)

### trash.py · Keychain unlock via security CLI
- refers-to: trash.py :: KEYCHAIN_SERVICE / keychain_enable / keychain_unlock
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Real Touch ID needs LAContext in signed native code; the shipping path is the macOS `security` CLI: enable verifies the passkey then stores it under service ai.nodemode.damp.vault (add-generic-password -U); unlock reads it back (find-generic-password -w), re-verifies against the scrypt hash, & issues a normal vault token. Keychain ACL prompts are where the fingerprint shows up today; a native LAContext sheet is the recorded next step once the app is signed. Non-darwin returns 501, & the endpoint never stores anything that is not already the user's passkey.

## app/services/ocrsvc.py

### ocrsvc.py · tier-1 tesseract
- refers-to: ocrsvc.py :: tesseract_path / scan_job
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Photos-style text search w/o heavyweight ML deps: tesseract is treated exactly like ffmpeg · a user-supplied PATH binary (brew install tesseract), never bundled. The scan job OCRs images directly & videos via their 768 poster, storing normalized text in media.ocr_text; /media/search folds it into the name/people/album LIKE union. Absent binary means status.tesseract=false & a 409 on scan, w/ zero degradation elsewhere.

### services vendor note · fsbrowse + native_picker
- refers-to: fsbrowse.py / native_picker.py
- kind: provenance
- logged: v0.3.0 · 2026-07-25

Both vendored from deduplakit v0.11.0 (same license, same author-project) w/ two changes: the exclusions import is inlined (ENV_DIR_NAMES/OS_META_DIRS/looks_like_env constants) & the dialog prompt says import into DAMp. native_picker IS the real OS dialog · osascript choose folder w/ showing package contents on macOS, PowerShell FolderBrowserDialog on Windows, zenity/kdialog on Linux · run by the backend so the zero-Tauri-API page never needs IPC.

## desktop_entry.py

### app/db.py (v2)

### app/db.py · schema v2 migration
- refers-to: db.py :: SCHEMA_VERSION / MIGRATIONS / init_db
- kind: explainer
- logged: v0.3.0 · 2026-07-25

v2 adds media.hidden, media.ocr_text & people.hidden via an in-place ALTER migration keyed off schema_meta.version, tolerant of duplicate-column reruns. Every general visibility clause across routers & services is now `trashed_ts IS NULL AND private=0 AND hidden=0`, making Hidden a first-class tier like Photos: excluded from Library, search, People stats, Collections counts & dedup scans until explicitly unhidden from the vault-gated page.

## app/services/classify.py (v2)

### classify.py · dims-gated screenshot heuristic
- refers-to: classify.py :: SCREEN_DIMS / looks_screenshot
- kind: rationale
- logged: v0.3.0 · 2026-07-25

The v0.1 rule (any PNG w/o EXIF time) swallowed exports & artwork, per real-usage feedback. Now a screenshot is: the classic filename pattern, OR a PNG w/o EXIF whose exact pixel dims (either rotation) sit in a curated set of Mac/iPhone/iPad screen resolutions. main.py runs a one-time startup reclassify over existing rows (settings classify_ver=2) using created_src=='exif' as the stored EXIF-presence signal, so already-imported libraries heal themselves.

## app/services/facesvc.py (dominance)

### facesvc.py · dominance model
- refers-to: facesvc.py :: MIN_FACE_AREA / _Clusterer / refresh_cover / unassign_face / merge_people
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Tiny background faces polluted groups: detections under 0.4 percent of frame area are skipped, & each face carries dominance = quality x sqrt(area). Centroids are quality-WEIGHTED sums so strong crops steer matching (the requested best-face-crops training db, realized as weighted exemplars over every stored embedding); covers are the argmax dominance face, recomputed in Python (sqlite sqrt is not guaranteed) on every assign/unassign/merge. unassign_face deletes newly-empty people & is the correction loop: removing a wrong face immediately reshapes that person's centroid for future scans.

## app/services/thumbs.py (v2)

### thumbs.py · first-frame posters & cache versioning
- refers-to: thumbs.py :: THUMB_VER / thumb_path / video branch
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Video posters now come from frame 0 w/ a 0.5s retry for encoders whose first packet is not a clean keyframe. THUMB_VER landed in the filename so every existing poster (cut at 1s in earlier builds) regenerates lazily on next view w/o a migration pass or stale-file cleanup.

## app/services/facesvc.py (accuracy)

### facesvc.py · exemplar verification & quality gates
- refers-to: facesvc.py :: face_threshold / MIN_JOIN_QUALITY / MIN_NEW_PERSON_QUALITY / _exemplar_ok / rebuild_people / assign_face
- kind: rationale
- logged: v0.4.0 · 2026-07-25

Too-generic grouping had three causes, each gated: the 0.42 default cosine was loose (now 0.55, w/ precedence setting > env > default; the earlier attempt edited a same-named function in config.py & silently no-opped · the settings-aware getter now lives here & shadows the env helper); centroid-only matching let averages drift (a candidate must now ALSO hit one of the person's 10 best-quality stored crops within 0.03 of threshold · the best-face-crops db doing real work at assign time); & low-quality detections founded junk people (under 0.82 quality can join but never create; under 0.6 does not even update centroids). rebuild_people re-clusters every stored embedding quality-desc at the chosen strictness in seconds w/o re-detection, persisting the threshold; names & manual merges reset, which the UI states before running. assign_face powers per-crop reassignment incl. new-person creation w/ cover recompute on both sides.

## app/routers/trash.py (keychain + hidden)

### trash.py · Keychain unlock via security CLI
- refers-to: trash.py :: KEYCHAIN_SERVICE / keychain_enable / keychain_unlock
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Real Touch ID needs LAContext in signed native code; the shipping path is the macOS `security` CLI: enable verifies the passkey then stores it under service ai.nodemode.damp.vault (add-generic-password -U); unlock reads it back (find-generic-password -w), re-verifies against the scrypt hash, & issues a normal vault token. Keychain ACL prompts are where the fingerprint shows up today; a native LAContext sheet is the recorded next step once the app is signed. Non-darwin returns 501, & the endpoint never stores anything that is not already the user's passkey.

## app/services/ocrsvc.py

### ocrsvc.py · tier-1 tesseract
- refers-to: ocrsvc.py :: tesseract_path / scan_job
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Photos-style text search w/o heavyweight ML deps: tesseract is treated exactly like ffmpeg · a user-supplied PATH binary (brew install tesseract), never bundled. The scan job OCRs images directly & videos via their 768 poster, storing normalized text in media.ocr_text; /media/search folds it into the name/people/album LIKE union. Absent binary means status.tesseract=false & a 409 on scan, w/ zero degradation elsewhere.

### services vendor note · fsbrowse + native_picker
- refers-to: fsbrowse.py / native_picker.py
- kind: provenance
- logged: v0.3.0 · 2026-07-25

Both vendored from deduplakit v0.11.0 (same license, same author-project) w/ two changes: the exclusions import is inlined (ENV_DIR_NAMES/OS_META_DIRS/looks_like_env constants) & the dialog prompt says import into DAMp. native_picker IS the real OS dialog · osascript choose folder w/ showing package contents on macOS, PowerShell FolderBrowserDialog on Windows, zenity/kdialog on Linux · run by the backend so the zero-Tauri-API page never needs IPC.

## desktop_entry.py · env defaults & selfcheck
- refers-to: desktop_entry.py :: main / selfcheck / default_library
- kind: rationale
- logged: v0.2.0 · 2026-07-25

The frozen engine's entry sets three defaults before importing the app: DAMP_DIST & DAMP_MODELS point into sys._MEIPASS (the only correct path inside a PyInstaller onefile), & DAMP_LIBRARY lands in the platform app-data dir (~/Library/Application Support/DAMp/library on macOS) bc a frozen binary has no repo to anchor the web default. Port comes from DAMP_PORT w/ 0 meaning OS-assigned, which the shell's handshake depends on. --selfcheck prints one JSON line proving Pillow/numpy/cv2/pillow_heif importability + version + bundled dist & models; build_macos_app gates on it so a bad freeze fails at build time, not first launch.

## app/main.py

### app/db.py (v2)

### app/db.py · schema v2 migration
- refers-to: db.py :: SCHEMA_VERSION / MIGRATIONS / init_db
- kind: explainer
- logged: v0.3.0 · 2026-07-25

v2 adds media.hidden, media.ocr_text & people.hidden via an in-place ALTER migration keyed off schema_meta.version, tolerant of duplicate-column reruns. Every general visibility clause across routers & services is now `trashed_ts IS NULL AND private=0 AND hidden=0`, making Hidden a first-class tier like Photos: excluded from Library, search, People stats, Collections counts & dedup scans until explicitly unhidden from the vault-gated page.

## app/services/classify.py (v2)

### classify.py · dims-gated screenshot heuristic
- refers-to: classify.py :: SCREEN_DIMS / looks_screenshot
- kind: rationale
- logged: v0.3.0 · 2026-07-25

The v0.1 rule (any PNG w/o EXIF time) swallowed exports & artwork, per real-usage feedback. Now a screenshot is: the classic filename pattern, OR a PNG w/o EXIF whose exact pixel dims (either rotation) sit in a curated set of Mac/iPhone/iPad screen resolutions. main.py runs a one-time startup reclassify over existing rows (settings classify_ver=2) using created_src=='exif' as the stored EXIF-presence signal, so already-imported libraries heal themselves.

## app/services/facesvc.py (dominance)

### facesvc.py · dominance model
- refers-to: facesvc.py :: MIN_FACE_AREA / _Clusterer / refresh_cover / unassign_face / merge_people
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Tiny background faces polluted groups: detections under 0.4 percent of frame area are skipped, & each face carries dominance = quality x sqrt(area). Centroids are quality-WEIGHTED sums so strong crops steer matching (the requested best-face-crops training db, realized as weighted exemplars over every stored embedding); covers are the argmax dominance face, recomputed in Python (sqlite sqrt is not guaranteed) on every assign/unassign/merge. unassign_face deletes newly-empty people & is the correction loop: removing a wrong face immediately reshapes that person's centroid for future scans.

## app/services/thumbs.py (v2)

### thumbs.py · first-frame posters & cache versioning
- refers-to: thumbs.py :: THUMB_VER / thumb_path / video branch
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Video posters now come from frame 0 w/ a 0.5s retry for encoders whose first packet is not a clean keyframe. THUMB_VER landed in the filename so every existing poster (cut at 1s in earlier builds) regenerates lazily on next view w/o a migration pass or stale-file cleanup.

## app/services/facesvc.py (accuracy)

### facesvc.py · exemplar verification & quality gates
- refers-to: facesvc.py :: face_threshold / MIN_JOIN_QUALITY / MIN_NEW_PERSON_QUALITY / _exemplar_ok / rebuild_people / assign_face
- kind: rationale
- logged: v0.4.0 · 2026-07-25

Too-generic grouping had three causes, each gated: the 0.42 default cosine was loose (now 0.55, w/ precedence setting > env > default; the earlier attempt edited a same-named function in config.py & silently no-opped · the settings-aware getter now lives here & shadows the env helper); centroid-only matching let averages drift (a candidate must now ALSO hit one of the person's 10 best-quality stored crops within 0.03 of threshold · the best-face-crops db doing real work at assign time); & low-quality detections founded junk people (under 0.82 quality can join but never create; under 0.6 does not even update centroids). rebuild_people re-clusters every stored embedding quality-desc at the chosen strictness in seconds w/o re-detection, persisting the threshold; names & manual merges reset, which the UI states before running. assign_face powers per-crop reassignment incl. new-person creation w/ cover recompute on both sides.

## app/routers/trash.py (keychain + hidden)

### trash.py · Keychain unlock via security CLI
- refers-to: trash.py :: KEYCHAIN_SERVICE / keychain_enable / keychain_unlock
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Real Touch ID needs LAContext in signed native code; the shipping path is the macOS `security` CLI: enable verifies the passkey then stores it under service ai.nodemode.damp.vault (add-generic-password -U); unlock reads it back (find-generic-password -w), re-verifies against the scrypt hash, & issues a normal vault token. Keychain ACL prompts are where the fingerprint shows up today; a native LAContext sheet is the recorded next step once the app is signed. Non-darwin returns 501, & the endpoint never stores anything that is not already the user's passkey.

## app/services/ocrsvc.py

### ocrsvc.py · tier-1 tesseract
- refers-to: ocrsvc.py :: tesseract_path / scan_job
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Photos-style text search w/o heavyweight ML deps: tesseract is treated exactly like ffmpeg · a user-supplied PATH binary (brew install tesseract), never bundled. The scan job OCRs images directly & videos via their 768 poster, storing normalized text in media.ocr_text; /media/search folds it into the name/people/album LIKE union. Absent binary means status.tesseract=false & a 409 on scan, w/ zero degradation elsewhere.

### services vendor note · fsbrowse + native_picker
- refers-to: fsbrowse.py / native_picker.py
- kind: provenance
- logged: v0.3.0 · 2026-07-25

Both vendored from deduplakit v0.11.0 (same license, same author-project) w/ two changes: the exclusions import is inlined (ENV_DIR_NAMES/OS_META_DIRS/looks_like_env constants) & the dialog prompt says import into DAMp. native_picker IS the real OS dialog · osascript choose folder w/ showing package contents on macOS, PowerShell FolderBrowserDialog on Windows, zenity/kdialog on Linux · run by the backend so the zero-Tauri-API page never needs IPC.

## desktop_entry.py

### app/db.py (v2)

### app/db.py · schema v2 migration
- refers-to: db.py :: SCHEMA_VERSION / MIGRATIONS / init_db
- kind: explainer
- logged: v0.3.0 · 2026-07-25

v2 adds media.hidden, media.ocr_text & people.hidden via an in-place ALTER migration keyed off schema_meta.version, tolerant of duplicate-column reruns. Every general visibility clause across routers & services is now `trashed_ts IS NULL AND private=0 AND hidden=0`, making Hidden a first-class tier like Photos: excluded from Library, search, People stats, Collections counts & dedup scans until explicitly unhidden from the vault-gated page.

## app/services/classify.py (v2)

### classify.py · dims-gated screenshot heuristic
- refers-to: classify.py :: SCREEN_DIMS / looks_screenshot
- kind: rationale
- logged: v0.3.0 · 2026-07-25

The v0.1 rule (any PNG w/o EXIF time) swallowed exports & artwork, per real-usage feedback. Now a screenshot is: the classic filename pattern, OR a PNG w/o EXIF whose exact pixel dims (either rotation) sit in a curated set of Mac/iPhone/iPad screen resolutions. main.py runs a one-time startup reclassify over existing rows (settings classify_ver=2) using created_src=='exif' as the stored EXIF-presence signal, so already-imported libraries heal themselves.

## app/services/facesvc.py (dominance)

### facesvc.py · dominance model
- refers-to: facesvc.py :: MIN_FACE_AREA / _Clusterer / refresh_cover / unassign_face / merge_people
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Tiny background faces polluted groups: detections under 0.4 percent of frame area are skipped, & each face carries dominance = quality x sqrt(area). Centroids are quality-WEIGHTED sums so strong crops steer matching (the requested best-face-crops training db, realized as weighted exemplars over every stored embedding); covers are the argmax dominance face, recomputed in Python (sqlite sqrt is not guaranteed) on every assign/unassign/merge. unassign_face deletes newly-empty people & is the correction loop: removing a wrong face immediately reshapes that person's centroid for future scans.

## app/services/thumbs.py (v2)

### thumbs.py · first-frame posters & cache versioning
- refers-to: thumbs.py :: THUMB_VER / thumb_path / video branch
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Video posters now come from frame 0 w/ a 0.5s retry for encoders whose first packet is not a clean keyframe. THUMB_VER landed in the filename so every existing poster (cut at 1s in earlier builds) regenerates lazily on next view w/o a migration pass or stale-file cleanup.

## app/services/facesvc.py (accuracy)

### facesvc.py · exemplar verification & quality gates
- refers-to: facesvc.py :: face_threshold / MIN_JOIN_QUALITY / MIN_NEW_PERSON_QUALITY / _exemplar_ok / rebuild_people / assign_face
- kind: rationale
- logged: v0.4.0 · 2026-07-25

Too-generic grouping had three causes, each gated: the 0.42 default cosine was loose (now 0.55, w/ precedence setting > env > default; the earlier attempt edited a same-named function in config.py & silently no-opped · the settings-aware getter now lives here & shadows the env helper); centroid-only matching let averages drift (a candidate must now ALSO hit one of the person's 10 best-quality stored crops within 0.03 of threshold · the best-face-crops db doing real work at assign time); & low-quality detections founded junk people (under 0.82 quality can join but never create; under 0.6 does not even update centroids). rebuild_people re-clusters every stored embedding quality-desc at the chosen strictness in seconds w/o re-detection, persisting the threshold; names & manual merges reset, which the UI states before running. assign_face powers per-crop reassignment incl. new-person creation w/ cover recompute on both sides.

## app/routers/trash.py (keychain + hidden)

### trash.py · Keychain unlock via security CLI
- refers-to: trash.py :: KEYCHAIN_SERVICE / keychain_enable / keychain_unlock
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Real Touch ID needs LAContext in signed native code; the shipping path is the macOS `security` CLI: enable verifies the passkey then stores it under service ai.nodemode.damp.vault (add-generic-password -U); unlock reads it back (find-generic-password -w), re-verifies against the scrypt hash, & issues a normal vault token. Keychain ACL prompts are where the fingerprint shows up today; a native LAContext sheet is the recorded next step once the app is signed. Non-darwin returns 501, & the endpoint never stores anything that is not already the user's passkey.

## app/services/ocrsvc.py

### ocrsvc.py · tier-1 tesseract
- refers-to: ocrsvc.py :: tesseract_path / scan_job
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Photos-style text search w/o heavyweight ML deps: tesseract is treated exactly like ffmpeg · a user-supplied PATH binary (brew install tesseract), never bundled. The scan job OCRs images directly & videos via their 768 poster, storing normalized text in media.ocr_text; /media/search folds it into the name/people/album LIKE union. Absent binary means status.tesseract=false & a 409 on scan, w/ zero degradation elsewhere.

### services vendor note · fsbrowse + native_picker
- refers-to: fsbrowse.py / native_picker.py
- kind: provenance
- logged: v0.3.0 · 2026-07-25

Both vendored from deduplakit v0.11.0 (same license, same author-project) w/ two changes: the exclusions import is inlined (ENV_DIR_NAMES/OS_META_DIRS/looks_like_env constants) & the dialog prompt says import into DAMp. native_picker IS the real OS dialog · osascript choose folder w/ showing package contents on macOS, PowerShell FolderBrowserDialog on Windows, zenity/kdialog on Linux · run by the backend so the zero-Tauri-API page never needs IPC.

## desktop_entry.py · env defaults & selfcheck
- refers-to: desktop_entry.py :: main / selfcheck / default_library
- kind: rationale
- logged: v0.2.0 · 2026-07-25

The frozen engine's entry sets three defaults before importing the app: DAMP_DIST & DAMP_MODELS point into sys._MEIPASS (the only correct path inside a PyInstaller onefile), & DAMP_LIBRARY lands in the platform app-data dir (~/Library/Application Support/DAMp/library on macOS) bc a frozen binary has no repo to anchor the web default. Port comes from DAMP_PORT w/ 0 meaning OS-assigned, which the shell's handshake depends on. --selfcheck prints one JSON line proving Pillow/numpy/cv2/pillow_heif importability + version + bundled dist & models; build_macos_app gates on it so a bad freeze fails at build time, not first launch.

## app/main.py · lifespan + dist mount
- refers-to: main.py :: lifespan / StaticFiles mount
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Lifespan runs init_db, creates originals/cache dirs, and purges expired trash. If `frontend/dist` exists the backend serves it at `/`, giving the single-process deployment path; the Vite dev server + proxy covers development.

### app/routers/importer.py · /system/window reshaped (v1.14.6)
- refers-to: importer.py :: WindowIn / set_window
- kind: removed-code
- logged: v1.14.6 · 2026-07-26

```python
if body.alpha is not None:
    alpha = max(0.3, min(1.0, body.alpha / 100.0))
    print(f"DAMP-CTRL WINALPHA {alpha:.3f}", flush=True)
    out["alpha"] = round(alpha * 100)
if body.material is not None:
    print(f"DAMP-CTRL WINMAT {1 if body.material else 0}", flush=True)
    out["material"] = body.material
```
WINALPHA removed w/ the whole-window fade (shell arm deleted); WINMAT was already dead shell-side since round 38. The endpoint is now { blur (0-64 clamp), clear (emits WINCLEAR 1, shell re-asserts the transparent webview backdrop) }. test_window_control_clamps tracks the new shape.

### app/services/thumbs.py + app/upgrade_thumbs.py · WebP v4 (v1.14.13)
- refers-to: thumbs.py :: THUMB_VER 4 / convert_legacy / ensure_thumb; upgrade_thumbs.py :: main / run_async; main.py :: lifespan trigger; mediaapi.py :: mime by suffix
- kind: rationale
- logged: v1.14.13 · 2026-07-26

Thumbs are WebP q80 method 4 at the same 192/384/768 buckets (payload diet, not a resolution change). Video posters go ffmpeg-frame-to-temp-jpg then Pillow-to-WebP so the bundled ffmpeg never needs a libwebp encoder · keep that two-step. ensure_thumb converts a legacy _v3.jpg in place when hit, so the system is correct even if the sweep never runs. upgrade_thumbs.py is deliberately a separate, standalone script (user requirement): importable (lifespan spawns run_async, a niced daemon thread after 3s · a subprocess would break under PyInstaller where sys.executable is the bundled binary) AND directly runnable. The .v4_done marker gates everything; delete it to force a re-sweep. THUMB_VER bumps must update both the script's suffix pair & the legacy path helper.

### app/mediacodecs.py + app/services/exifmeta.py · pi-heif, not pillow-heif (v1.27.4)
- refers-to: mediacodecs.py :: register; exifmeta.py :: spatial HEIC probe; desktop_entry.py :: selfcheck; setup/build_*_app freeze flags
- kind: rationale
- logged: v1.27.4 · 2026-10-23

The family bundle audit found pillow-heif's wheels carry libx265, the HEVC encoder, under GPL-2.0, and the freeze collected it into the engine. formDAM only decodes HEIC and HEIF, so it now uses pi-heif, the decode-only build of the same bindings: libheif and libde265 (LGPL-3.0) as separate shared libraries, and the same `register_heif_opener` and `open_heif(path, convert_hdr_to_8bit=...)` calls. The build scripts install it through requirements and pass `--exclude-module pillow_heif`, so a stray pillow-heif in a build venv can never be frozen in; formvis and formlit already freeze this way. The self-check reports `pi_heif`.

### app/main.py · .js, .mjs and .css keep their types on Windows (v1.28.4)
- refers-to: main.py :: the three mimetypes.add_type calls after the last import
- kind: rationale
- logged: v1.28.4 · 2026-10-31

Python's `mimetypes` takes file types from the Windows registry (`HKEY_CLASSES_ROOT\.js`, value `Content Type`) over its own table, and some installers and editors set `.js` to `text/plain`. On those PCs the engine served the built window's scripts as `text/plain`, WebView2 refused every module script under strict MIME checking, and the desktop window stayed blank; macOS, Linux, dev mode (Vite serves the page) and Windows PCs with the default value never showed it. The three calls pin `.js` and `.mjs` to `text/javascript` and `.css` to `text/css`, which covers `StaticFiles`, `FileResponse` and any direct `guess_type`. They sit after the last import, not above the imports: a module that re-reads the registry while importing cannot undo them, and no import follows a statement (E402). They look redundant off Windows; keep them. Repro on a Windows PC: `reg add "HKCU\Software\Classes\.js" /v "Content Type" /d "text/plain" /f`, then launch the rebuilt app; restore with `/d "text/javascript"`. Checked here: with the table poisoned to `text/plain` for js, mjs and css through `mimetypes.init(files=...)`, the three calls return `text/javascript`, `text/javascript` and `text/css`; `py_compile` passes. Not yet run on a Windows PC.

### app/ffmpeg_fetch.py + app/ffmpeg_record.py + main.py · ffmpeg arrives on first run, from formcut-binaries (v1.28.4)
- refers-to: main.py :: ffmpeg_fetch.start() after the MIME lines; ffmpeg_fetch.py (new); ffmpeg_record.py (new); dedup/visual.py :: _find_tool; services/facesvc.py
- kind: rationale
- logged: v1.28.4 · 2026-10-31

The two modules are new and identical in formvis, formvfx, formwav, formlit, formpromo and formDAM. ffmpeg stays external, never copied into the bundle: when no ffmpeg is on PATH, the frozen engine downloads, in a background thread, the LGPL build pinned in `ffmpeg_record.py` (release 7.1.5-2, the record formcut carries) from `nodemode-dev/formcut-binaries`, checks every file for the host triple against its SHA-256 before placing any, and installs it in the shared per-person folder `formcut-binaries/ffmpeg-7.1.5-2` (Application Support on macOS, LOCALAPPDATA on Windows, XDG_DATA_HOME or ~/.local/share on Linux), so the family downloads it once. The programs get their plain names and the folder goes first on PATH, which `_find_tool` searches first, so video thumbnails, video dedup and video faces find it with no change. An ffmpeg already on PATH is used and nothing is fetched. Outside a frozen build nothing is fetched unless `FORM_FFMPEG_AUTO=1`, so tests never reach the network; `FORM_FFMPEG_AUTO=0` turns it off in a desktop build, and `FORMCUT_FFMPEG_RELEASE` points at a mirror. Checked against the real release in the formvis copy of the module (byte-identical): pins equal the record, the Linux archive downloaded, verified and ran from the new PATH entry (7.1.5, LGPL), a tampered hash installed nothing, and the background start fetched only when no ffmpeg was on PATH. Not run in a built desktop app.

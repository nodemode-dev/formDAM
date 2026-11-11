# frontend HASHOUT_LOG · formDAM
current: v1.27.7 · 2026-10-25
### ui/components/hidden.ts + trash.ts · a vault token obtained after leaving is dropped, and a 401 retries once
- refers-to: ui/components/hidden.ts :: mountHiddenPage gone flag, load(retried), entry IIFE, teardown; ui/components/trash.ts :: mountTrashPage entry IIFE
- kind: fix
- logged: v1.28.9 · 2026-11-10

Each vault page clears the token on unmount so every entry re-locks, but the token can arrive after the unmount: open Hidden or Recently Deleted with device unlock stored, click another sidebar row while the device prompt is up, then authenticate. vaultGate then set a token nobody would clear, so every later api() call carried it, the next Hidden or Recently Deleted visit and private albums without their own passkey opened without asking, and once the token expired Hidden ran vaultGate (true, a token exists), /hidden 401, vaultGate (true) ... without end, while Recently Deleted showed "Nothing in the trash". Both pages now drop a token that arrives after they are gone, and on a 401 clear the token before asking again, retrying once (Hidden toasts the error instead of looping; Recently Deleted goes back if the unlock is refused). Checked: tsc --noEmit. Not run: the device prompt in a window.

### ui/components/people.ts · Select All picks only the people the name filter shows
- refers-to: ui/components/people.ts :: mountPeoplePage filterInput input handler, allBtn click
- kind: fix
- logged: v1.28.9 · 2026-11-10

Select All built its list from state.people while the grid showed only the people matching Search people, so typing a name, Select, Select All and Remove (or Hide, or Merge) acted on every person in the library, including the hidden ones. Select All now takes the same filtered list renderPeople shows, and changing the filter clears the picked set (and resets the button to Select All), so a pick can never include a card the user cannot see. Checked: tsc --noEmit. Not run: the People page in a window.

### public/splash.html · the logo no longer moves while the page streams in
- refers-to: public/splash.html :: body (padding-top, justify-content), p (height, line-height)
- kind: rationale
- logged: v1.28.2 · 2026-10-26 · Ledger FB-114

The desktop shell shows splash.html while the engine starts. Its body centred the logo and the line under it as flex children, so when a paint came between the logo and the line the logo was centred alone and then moved up 57 px when the line arrived: layout shift 4.8e-4 (about one throttled load in ten in the window smoke F7, source an IMG with no class, which also made the 15-run stress fail). The body now starts at a fixed padding-top and the line has a fixed 16 px height, so the logo's position no longer depends on its later sibling; the padding (50vh - 121px) puts the logo where it was (y 365.8 in a 900 px viewport, the 36 px being what the head elements and body already contribute). Verified: a server that sends the page up to the line, pauses 1 s and sends the rest measured a shift of 4.8e-4 (IMG 421 to 364) before and 0 after, with and without the pause, logo y 365.8 before and after.

### tests/window · the window smoke (F7) in its own folder
- refers-to: tests/window/test_window.py (pytest and Python Playwright, not vitest; vitest only includes tests/**/*.test.ts)
- kind: rationale
- logged: v1.28.2 · 2026-10-26

FAMILY_TEST_PLAN section 4, F7. The script starts the engine from backend/ on a free port with an empty library and config folder under a temporary home, FORMDAM_DIST pointing at the built frontend/dist and FORMDAM_SHELL_KEY set, then opens the window the way the desktop shell does (src-tauri main.rs navigates to http://127.0.0.1:PORT/#dam-key=KEY, and engine/session.ts trades the key for the window cookie). Without the key the window shows its lockout card and every /api call answers 403, so the test also asserts the lockout card is absent and #app mounted. Pages: the window entry with the key, and splash.html, the second HTML document the shell loads first. Chromium runs at 4x CPU slowdown and a 150 ms, 1.6 Mbps network; the test asserts a title, no 403, no failed or 4xx/5xx request, no console or page error and layout shift 0 after load, network idle and a 3 s settle. IGNORED_REQUESTS is empty. It needs `npm run build` first.

### styles/app.css .topbar-sub · the count under a topbar title no longer shifts the title
- refers-to: styles/app.css :: .topbar-sub; the spans created in library.ts, search.ts, curate.ts, dedup.ts and libmanage.ts
- kind: rationale
- logged: v1.28.2 · 2026-10-26 · Ledger FB-113

The topbar subtitle is an inline span that starts empty and is filled when the library summary arrives. An empty inline span makes no line box, so the title block was 19.75 px high and, centred in the 52 px bar, jumped up by 7.8 px when "N items" appeared (layout shift 7.5e-6 in the window smoke, F7, at 4x CPU and a slow network, the shift source being DIV.topbar-title). The span is now a block with a fixed 16 px line height and minimum height, so the line is reserved before the text arrives. Verified: the F7 window smoke failed before (shift 7.5e-06) and passes after (shift 0, two runs); no other shift entries.

### package-lock.json · zero npm audit findings, written by npm 11
- refers-to: package-lock.json (written by npm, not by hand); package.json :: devDependencies (unchanged: `^8.1.5`, `^4.1.11` already admit the fixed versions)
- kind: rationale + gotcha
- logged: v1.27.7 · 2026-10-25

Family rule from `FAMILY_DEV_PLAN.md` v0.4.x Phase 2b (formai_dev sidecar): every frontend installs with zero `npm audit` findings. This tree had five, all in development tools: Vite 8.1.5 (launch-editor command injection in the dev server, ledger FB-004), Vitest and @vitest/mocker 4.1.11 (code injection through manual mock registration), undici 7.29.0 through jsdom and source-map-js 1.2.1 through Vite (both denial of service, FB-005). The ranges in `package.json` already admit the fixed versions, so only the lock moved: Vite 8.3.5, Vitest and @vitest/mocker 4.1.12, undici 7.30.1, source-map-js 1.2.2. Gotcha: npm 10.9.9 fails on this tree with `Cannot read properties of null (reading 'edgesOut')` in arborist's peer-set walk whenever Vite or Vitest is re-resolved, from `npm install` with raised floors and from `npm update` alike; undici and source-map-js update fine. npm 11.21.1 (`npx -y npm@11.21.1 update vite vitest`) wrote the lock, and npm 10 then installs from it with `npm ci`. Raising the floors in `package.json` is left for when npm 10 can resolve them. After: `npm audit` 0, `tsc --noEmit`, `vite build`, `vitest run` 3 files and 10 tests passing, the dev server on `127.0.0.1:5173` only.

### settings App pane · About formDAM credit and licence name
- refers-to: ui/components/settings.ts :: PANES app (About formDAM heading, the new credit line, hint)
- kind: rationale
- logged: v1.27.6 · 2026-10-24

The owner relicensed formDAM to Apache-2.0 (copyright NodeAgentc, Inc.), so the About hint says Apache-2.0 where it said MIT. formDAM's Home has no credit line, so by the owner's choice the credit "by nodemode.ai" sits in About, directly under the heading, as a `settings-hint` built with the rest of the pane (nothing appears later) and marked translate="no" through `h()`'s attribute path.
### settings App pane · About formDAM with a closed Licences and notices section; "Glass" in place of "Liquid glass"
- refers-to: ui/components/settings.ts :: PANES app (About formDAM heading, hint, details.settings-notices), PANES appearance heading, sideNote; styles/app.css :: .settings-notices
- kind: rationale
- logged: v1.27.3 · 2026-10-23

The owner's licensing plan (L1, approved 2026-10-23): Adobe's DNG patent licence asks products that read DNG to show "This product includes DNG technology under license by Adobe Systems Incorporated." prominently, and the owner chose an About box with an accordion closed by default. formDAM has no About box, so Settings > App ends with an "About formDAM" heading, one line, and a native `<details>` "Licences and notices" holding the notice; it is built with the rest of the pane and opens in place. The owner's rename table also gives formDAM's translucent panels its own word: the Appearance heading and the side panel note say "Glass" where they said "Liquid glass" (Apple's name). Setting keys, CSS classes and `GlassPrefs` are unchanged.
### settings vault card, trash ensureVault modal, hidden and trash locked states · unlock names from /vault/device
- refers-to: settings keychainWrap Promise.all status + labels; trash ensureVault device fetched before openModal, kcRow built only when available, append spread, toast; trash and hidden empty-sub lines
- kind: rationale
- logged: zip v1.26.0 · 2026-10-20

The passkey modal now waits for the unlock status and names before it opens, so the save row is built once w/ the right words or not at all; before, it was appended and then removed or relabelled after a fetch, which shifted the modal. The locked-state lines are static and name no method, so they cannot change after paint.
### formDAM brand pass · formDAM-icon files, titles, sidebar mark, every user-facing string, package name
- refers-to: public/formDAM-icon.png and .svg; index.html and splash.html title and icon; sidebar side-brand; session showLockout copy; people face banner; collections shared empty state; libmanage default library name and package toast; outputs default export folder; packages hints; privacy state lines and FORMDAM_AUTOMATION; search text engine hint; settings vault, menu bar hints; sharing family hint, peer fallback name, package toast and lede; package.json and package-lock.json formdam-frontend
- kind: rationale
- logged: zip v1.25.0 · 2026-10-20

Text only, no DOM structure or timing changed. Internal identifiers that never reach a reader stay as they were: the x-dam-* request headers (the engine's contract), the dam-key fragment, the dam-* CSS ids, keyframes, custom events and drag types, and the dam-amber theme name.
### engine/session.ts + main.ts gate + .lockout-card · the window connects with the launcher's key
- refers-to: session KEY_RE, openSession, showLockout hashchange; main.ts top-level gate before initPrefs; parity.css .lockout-card; packages.ts MIN_PASSWORD 16 and hint
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

Before any API call, main.ts reads a dam-key fragment, removes it from the address with replaceState, and trades it for the session cookie; without a fragment it asks whether the cookie is already valid (reloads and other tabs in the same browser). If neither works, one static card replaces #app and module evaluation parks on a promise that never settles, so nothing else mounts or calls the engine; a later hashchange carrying a key connects and reloads once. Checked under 4x CPU and a slow network: no key shows the card, the key connects and loads every thumbnail, reload and a second tab stay connected, a forged header from another browser gets 403.
### ui/components/infopanel.ts lookupCard detail line + engine/types LookupResult detail/rank
- refers-to: infopanel lookupCard lookup-kind text; types LookupResult detail, rank
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

Look Up results can carry a detail (the scientific name for species, the artist for artworks) and a rank (genus or family when the species itself was not clear). Both go into the existing kind line, so the card keeps its height and nothing below it moves.
### ui/components/editor.ts Clean Up pane · Select Object, Show Distractions, face pixelation
- refers-to: editor Spot, CleanInfo, Suggestion, Box4; cleanMode, cleanInfo, suggestions, pendingBox; modeRow, suggestBtn, suggestLabel, cleanStatus, loadCleanInfo, segmentWith, faceUnder; drawOverlay retouch branch; overlay pointerdown retouch branch; parity.css .ed-mask .ed-pixel .ed-suggest .ed-pending .ed-clean-status
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

The Clean Up pane gains a Brush / Select Object switch and a Show Distractions button; both stay disabled until GET /media/{id}/cleanup (fetched once when the tab first opens) says the models are present, and the status line says so when they are not. Distractions draw as accent outlines in the existing 0..1 SVG overlay with a title per box; clicking one, or clicking the photo in Select Object mode, shows a marching dashed box at the spot while the engine outlines the object, then adds a mask spot drawn as a filled polygon path and asks for one preview. A used suggestion is dropped from the overlay. A brush stroke that lies mostly inside a detected face box is swapped for a pixelate spot drawn as a dashed box. The status line has a reserved min-height of two lines so messages never move the slider and buttons below; the probe checked every pane child's top before and after under 4x CPU and slow network. Only overlay children are replaced; the image, frame and pane are not rebuilt.
### ui/components/privacy.ts + settings Privacy pane
- refers-to: privacy.privacyPane; settings PANES privacy entry
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

Settings gains a Privacy pane with Automation Access (off by default): turning it on shows the token once with Copy and New Token; turning it off revokes it and hides the token. The pane says plainly what the switch guards and what it cannot, notes when the engine was started with DAM_AUTOMATION=1, and lists the other reach-beyond-this-computer features and where they are switched on.
### sharing.ts familyCard · Shared Library with a share key
- refers-to: sharing.familyCard, FamilyState, FamilyPeer, mountSharedPage refresh; parity.css .pkg-pw-row inputs
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

The family card replaces the folder card: an On switch (off by default, refused with a reason until a key exists), the Family ID, the key hidden until Show Key, New Key and paste-a-key (both disabled while on, so the key cannot change under a running family), the port, add a device by address, the members found with when each last synced, and the last pass. Errors land in a reserved line; peers are keyed by device id and only their time text is patched.
### ui/components/packages.ts + sharing.ts, albums.ts, libmanage.ts edits · encrypted packages in the window
- refers-to: packages.packageFlow, sentPanel, openPackageFlow, notesFlow, mountPackageList, waitJob, seg; sharing.shareEntries, mountSharedPage packages section & Open Package, registerSharing tile entry; albums.mountAlbumDetail shareBtn & notesBtn; libmanage.registerLibraryDrops zip routing; parity.css .field-error, .pkg-*
- kind: rationale + replaced code
- logged: zip v1.24.0 · 2026-10-10

Share as Encrypted Package replaces Share Link everywhere it was offered (tile menu, selection bar, viewer, album header). The form pre-fills a strong password the user can replace, and the result shows the file, the password in a monospace block with Copy, Show in Finder, and on the Mac AirDrop, Mail and Messages for the file. A .zip dropped anywhere in the window, or chosen with Open Package on the Sharing page, is inspected first; a package opens a password prompt whose error line keeps its height, so a wrong password never moves the form. The album header gains Notes. Replaced: the link form, guest server card, link list and guest activity pane.
### sharing.ts sync cards, Move to Shared Library, library view switch
- refers-to: sharing.syncCard, moveLibrary, mountSharedPage sync section & device name, registerSharing tile entry; organize.openQuickFilters Both/Personal/Shared; organize FLAG_VALUES shared & personal library
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

The Sharing page carries two sync cards (this library, the Shared Library) that paint from one /sync payload: folder, on switch, last pass & the other devices or participants. A change re-reads the state at 2.5 s & 8 s so the first pass shows without waiting for the 15 s refresh; every write is to text of an existing node. The photo menu flips an item between libraries & patches its shared_lib in place. The quick filter menu gains a three-way Both, Personal, Shared switch ahead of the other filters, kept exclusive by replacing either library flag.
### ui/components/sharing.ts + albums Share button + sidebar Sharing
- refers-to: sharing.shareForm, serverNotice, resultPanel, shareLinkFlow, shareAlbumFlow, sendFiles, galleryFlow, shareEntries, mountSharedPage, registerSharing; albums.mountAlbumDetail shareBtn; sidebar PINNED Sharing; main route shared; icons-extra share, link, sync; parity.css .share-*
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

Share is reachable from the selection bar, the tile menu, the viewer toolbar & an album's header. The share form carries the opt-in in place: when sharing is off it says what turning it on does & the button flips only that note, so the form never jumps. The QR image has its size set before it loads. The Sharing page patches its rows by share id & repaints only their sub-line & unread badge on the 15 s refresh; the activity list is keyed by activity id with its empty state outside the list so patching never meets an unkeyed node.
### organize Edit With round trip
- refers-to: organize.startEditWith, roundTrips, openWithFlow
- kind: rationale + replaced code
- logged: zip v1.23.0 · 2026-10-10

Edit With starts a round trip & polls its status every 2 s while the session lives; each new save from the other app bumps the thumbnail version, patches the item & reloads the viewer still, the same three steps the editor's Done uses, so the grid tile & open viewer update in place. One timer per item; starting again replaces it. Replaced: `api(/media/{id}/open)` straight on the original.
### infopanel Look Up section
- refers-to: infopanel.createInfoPanel lookupSection, lookupCard, paint lookup patchList; types.LookupResult, MediaDetails.lookup; parity.css .lookup-*
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

The info panel shows Look Up results above Subjects: the name, what kind of thing it is (and "near this photo's location" for a GPS landmark match), other likely names, Show All (a search for that name) & Learn More (Wikipedia in the browser). The results arrive w/ the details response, so the section paints in the same frame as the rest of the panel instead of appearing later & pushing it down; cards are keyed by name & alternatives so stepping between photos patches only what changed.
### editor Clean Up tab, RAW Develop, Lens Corrections & Live Photo Effect
- refers-to: editor.ts EditState retouch points, retouchPane (Remove Last, Clear All), strokeNode, overlay pointerdown retouch branch, tab label Clean Up; RAW Develop & Lens Corrections sections; Live Photo Effect select; parity.css .ed-stroke
- kind: rationale
- logged: zip v1.23.0 · 2026-10-10

The Retouch tab is now Clean Up: a click still drops a circle, a drag paints a stroke whose polyline grows in place (one node, its points attribute updated, points thinned under 0.3 percent of the frame & capped at 1500) & the preview is requested once on release, so the photo never re-renders mid-stroke. Strokes under three points collapse to a click. RAW Develop shows only for RAW files: choosing Custom (Kelvin) seeds the temperature & tint sliders from the shot's own values (raw-info), which stay hidden otherwise so the panel does not jump on open. Lens Corrections apply to every photo. Live Photo Effect appears only when the item has a paired video.
### library sort menu + stack and memory tile entries · gaps found by the independent grade audit
- refers-to: library.ts sort menu (First added, Name Z to A, Smallest first, Recently viewed); store.ts SortOrder viewed; organize.ts tileEntries Make Stack Top, Remove from Stack; curate.ts registerCurate Remove from Memory
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

A read-only audit of the parity grades found engine features w/o an interface path. Wired here because each is one menu entry: the four sort orders the engine already had, choosing a stack's top & taking items out of a stack, & removing items from a memory (shown only on a memory page). Removal relies on invalidateMedia plus the media topic: the grid refetches the page & appendItems drops tiles no longer in it, so nothing is rebuilt. Left engine-only & said so on the comparison page: pet merge, group hiding, template deletion, consolidate by moving, auto-stacking.
### infopanel Text in Photo + curate Describe a Memory + libmanage disk ratings
- refers-to: infopanel.createInfoPanel ocrSection (Copy); curate.mountMemoriesPage describe button; libmanage.paintDiskMeta, mountDiskPage keys handler
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

The info panel shows the recognised text of a photo, selectable, w/ a Copy link (Live Text's copy path); the section stays hidden when there is none, so the panel does not reserve space for it. Memories gains Describe a Memory. Browse Disk tiles paint stars & a label dot from sidecars & the page listens for 0-5, X & 6-9 on picked files while it is mounted; the listener is removed on teardown.
### ui/components/libmanage.ts + drops · libraries, repair, browse disk, folder & album drops
- refers-to: libmanage.switchTo/mountLibraryPage/mountDiskPage/quickLook/collectEntries/uploadAll/albumTarget/registerLibraryDrops; grid.ts tile dragstart (application/x-dam-ids); sidebar.ts album rows carry data-album-id, Browse Disk & Libraries rows; importer.ts Add in place checkbox; main.ts libraries & disk routes, registerLibraryDrops; parity.css lib, disk & drop-target rules
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

The Library page lists known libraries (open, remove from list), opens or creates one through the folder picker, runs Repair (optional checksum pass) & shows its last report w/ an Import Unknown Files action, & copies referenced files in. A switch reloads the page, because every cache in the store belongs to the old catalog. Browse Disk is Bridge's folder view: shortcuts (home folders, mounted volumes), breadcrumbs, folders as chips, media as tiles w/ engine thumbnails & an In Library badge, click to pick, double-click to preview, then Import Copies or Add in Place. Drops: files or whole folders dropped anywhere (folders walked w/ webkitGetAsEntry) import in 40-file chunks; dropped on a sidebar album row or onto an open album, they also join that album, duplicates included; tiles drag onto album rows to add without importing. The import page's own drop zone keeps its handler, & the global one ignores drops inside it.
### ui/components/curate.ts + grid multi-select · memories, groups, slideshow, compare
- refers-to: curate.memoriesStrip/mountMemoriesPage/mountMemoryPage/groupsStrip/Music/playMemory/openSlideshow/openCompare/createMemoryFlow/registerCurate; grid.ts tile click (Cmd/Ctrl-click toggle, Shift-click range, selectAnchor); icons-extra pause; collections.ts Memories & Groups sections (replaced the "Automatic Memories are on the roadmap" placeholder); sidebar.ts Memories row; main.ts memories & memory routes, registerCurate
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

Memory music is generated w/ WebAudio (a four-chord pad plus an arpeggio through a low-pass & a feedback delay; tempo, voicing & delay differ per theme), so a memory has a soundtrack w/o shipping licensed audio; a chosen local file plays through the engine instead. The slideshow keeps two absolutely positioned layers & crossfades by opacity once the next image has decoded, w/ a slow Ken Burns scale-and-drift per still, preloads the following item, plays videos muted, & goes fullscreen when allowed; space pauses, arrows step, Esc leaves. Compare shows 2 to 4 items w/ one shared transform (linked zoom & pan, wheel zoom around the cursor, 100% from the focused pane) or per-pane transforms when unlinked; ratings, reject & favorite keys apply to the focused pane, as in Bridge's Review & Lightroom's Survey. The grid gained Cmd/Ctrl-click to toggle & Shift-click to extend a selection; before this, a selection could only start from the tile check button. Removed from collections.ts: the Memories emptyState placeholder body.
### ui/components/outputs.ts · File Info, Export, Contact Sheet, Print, Workflows
- refers-to: outputs.pickFolder/fileInfoFlow/exportFlow/pdfModal/contactSheetFlow/printFlow/workflowsFlow/newWorkflowFlow/outputEntries/registerOutputs; main.ts registerOutputs; parity.css fileinfo, pdf-frame, wf-step rules
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

One Output menu (selection bar, viewer toolbar) & the first four entries in the tile menu reach every output path. File Info groups the IPTC fields the way Bridge's dialog does (Description, Creator & Rights, Contact, Location & Status), shows the place lookup as placeholders, saves only touched fields & holds the XMP auto-write toggle. Export picks a folder through the native picker & falls back to a typed path when the shell has none. Contact sheets & prints render as engine PDFs in an iframe so the system print dialog (Print...) & Save PDF both work inside Tauri's WebView, where window.print on the app page would print the UI; option changes reload the PDF in place. Shortcuts: Cmd/Ctrl-Shift-E export, Cmd/Ctrl-Alt-I File Info, Cmd/Ctrl-P print.
### ui/components/editor.ts + viewer toolbar seam + thumb versions · photo editor & video trim
- refers-to: editor.openEditor (layout, runPreview, slider, curves, filters, crop/retouch/markup overlay, undo/redo, compare, auto, revert, Done), openTrim, honorTrim, copyEdits/pasteEdits/revertToOriginal, editEntries, registerEditor; viewer.ts viewerHooks.toolbar rendered in the top bar, reloadStill, videoReady; api.ts thumbVersions + thumbUrl v param; store.ts loadMore thumbVersions fill; grid.ts paintTileMeta thumb refresh; main.ts registerEditor; parity.css editor rules
- kind: rationale
- logged: zip v1.22.0 · 2026-10-10

The editor shows engine renders, not a canvas re-implementation, so what you see is exactly what export, thumbnails & the viewer show; one pipeline, no drift. Slider input debounces 50 ms & keeps one request in flight (the newest wins); each result is decoded off-screen & swapped into the same img in one step, so the image never blanks, & a result that lands mid-drag waits for pointerup so the crop frame never jumps under the cursor. The frame is sized from the preview's natural size & an SVG overlay with a 0..1 viewBox sits exactly on it, so crop rectangles, retouch spots & markup are stored normalised & survive any preview size. Crop shows the uncropped geometry w/ a rule-of-thirds frame & aspect presets; retouch shows the unrotated frame (spots are stored there); markup shows the final frame. Undo/redo hold up to 100 JSON snapshots; M or the Compare button shows the original while held; E opens the editor from the viewer, Enter saves, Esc cancels; Cmd/Ctrl-Shift-C and -V copy & paste edits. The viewer's toolbar hook array existed since P4 but was never rendered; it is now spread into the top bar. Thumbnails are cached a week by the browser, so thumbUrl appends v=edited_ts & paintTileMeta swaps a tile's src when its version changes; the old pixels stay until the new ones load. Videos open a trim panel; playback in the viewer honours the saved trim.
### ui/components/search.ts + find.ts + discover.ts · structured search, Advanced Find, Pets, Subjects & Content
- refers-to: search.ts SCOPES, mountSearchPage (currentSpec, run, suggest, headReady), find.advancedFindFlow/registerFind, discover.clipCard/mountPetsPage/mountSubjectsPage/petsStrip/contentCards/discoverEntries/registerDiscover; organize.smartFromSpec + RULE_FIELDS visual; collections.ts Pets & Content sections; sidebar.ts Pets & Subjects rows; main.ts pets & subjects routes, registerDiscover, registerFind
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

Search now runs through the query engine instead of /media/search, so it covers titles, captions, keywords, places, dates, camera, subjects & "Looks like" (CLIP) besides filenames, text, people & albums, & its results page like the library (keyset paging, day sections, the same tiles & selection). Removed from search.ts: the `/media/search` fetch, `items` array, `tileFor` map into `grid.replaceChildren(...)`, the empty-state `grid.replaceChildren(...)` & the bindTileSize/bindSelectionClasses pair (mountGrid owns both now). Suggestion rows (people, places, keywords, subjects, pets, albums, dates, looks like) are keyed chips that open the exact rule. The header cards (OCR, visual index) & suggestions settle before the grid mounts, so results never jump under late-arriving rows (CLS 0.02 before, 0.000008 after, at 4x CPU & a slow network). Advanced Find (Cmd/Ctrl-F) reuses the smart-album rule editor w/ a live count, shows results as a query route or saves them as a smart album; a text search saves as a "search" rule. Pets show as round covers w/ inline naming; "Not This Pet" & "Show Similar" join the tile menu through tileHooks.
### ui/components/map.ts + places.ts · Places map, Trips, location & date editors
- refers-to: map.createMap (project/unproject, draw, drawClusters, thumbFor, fitBox, bounds, pointer & wheel handlers); places.tripsStrip/placesStrip/mountPlacesPage/mountTripsPage/locationFlow/dateFlow/placeEntries/registerPlaces; viewer.ts viewerHooks.refreshInfo; collections.ts Places & Trips sections (replaced the "Trip detection needs location data support" placeholder); sidebar.ts Places row; main.ts places & trips routes + registerPlaces; parity.css map, location & date rules
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

The map is one canvas w/ a Web Mercator projection & no tile server, so it works offline & never leaks where the library was shot. Country outlines are projected once into Float64Arrays & drawn for each horizontal world copy in view; markers cluster on a 58 px screen grid per frame & show the newest item's thumbnail w/ a count badge, as Photos does. Clicking a cluster zooms to its bounds until the cluster cannot split, then opens its items; "Show N in View" counts the visible bbox through /browse/count & opens the area as a query route. Redraws are coalesced to one rAF & happen only inside the canvas, so panning never touches layout. Colours come from computed CSS (container colour for land & borders, a probe span for the accent) so themes recolour the map. The location editor searches the offline gazetteer, accepts pasted "lat, lon", picks by clicking the map, removes or hides the location, & names a picked point via /places/reverse; the date editor sets, shifts or reverts. Both patch state.byId per item & call viewerHooks.refreshInfo so only the info rows change. Removed from collections.ts: the Trips emptyState placeholder body. Empty states start hidden & strips reserve their height, so nothing flashes "No Trips" before data arrives (measured CLS 0.000008 at 4x CPU & a slow network).
### ui/components/infopanel.ts + organize.ts + pages.ts + ui/keyed.ts + ui/prompt.ts + ui/icons-extra.ts + styles/parity.css · organizing UI
- refers-to: infopanel.createInfoPanel (paint, load, commit, keyword add/remove); organize.assignKeywordsFlow/openKeywordManager/renameFlow/copyToFlow/openWithFlow/stackFlow/ruleEditor/smartAlbumFlow/newFolderFlow/moveAlbumFlow/openQuickFilters/tileEntries/registerOrganize; pages.mountImportsPage/mountKeywordsPage/mediaTypeCards/coverCard; keyed.patchList/setText; prompt.promptText; icons-extra EXTRA_GLYPHS; icons.ts iconEl lookup; viewer.ts viewerHooks, ratingKey, info panel wiring, meta listener; grid.ts paintTileMeta, tileHooks, media + meta listeners; selectbar.ts selectbarExtras; library.ts sort entries, quick filter & pin buttons, filterTitle spec branch; collections.ts media types + utilities; sidebar.ts userPins/togglePin/pinsWrap + Imports & Keywords rows; albums.ts folder level, smart & folder buttons, ctx entries; main.ts q/imports/keywords routes + registerOrganize; store.ts patchMedia/saveMeta/keywords; tokens.css z layers; index.html parity.css
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

The info panel is built once per viewer & patched per item (setText & keyed chip lists), replacing a panel that was rebuilt w/ replaceChildren on every step. Removed from viewer.ts: `fetchMeta(id)` (cached /media/{id} fetch) & `buildInfo(item)` (rows Filename, Captured, Kind, Dimensions, Size, Duration, Albums, Category) & their two replaceChildren call sites; the panel now reads /media/{id}/details. Edits flow through store.saveMeta, which patches state.byId & emits "meta" w/ patched.ids so the grid repaints only that tile's badge row (paintTileMeta keys the row on its own content to skip no-op writes) & the viewer only its heart. Shortcuts follow Bridge & Photos: 0-5 rating, 6-9 red/yellow/green/blue, X reject, period favorite, in the viewer & on any selection; Cmd/Ctrl-K keywords for the selection, Cmd/Ctrl-Shift-K the Keyword Manager, keyword shortcut letters tag the selection. Extension seams instead of growing core files: viewerHooks (toolbar, keys, location/date editors, onShow), tileHooks.ctx, selectbarExtras, all filled by registerOrganize & later modules. window.prompt is unreliable in Tauri's WKWebView, so promptText is a promise modal. New glyphs live in icons-extra.ts bc theme/icons.js is vendored themeanizor output. Z-index: tokens.css now declares the layer scale; the inherited app.css still holds raw values (debt, recorded in BUILD_NOTES), & parity.css lifts .ctx-menu to --z-menu bc menus opened from a modal rendered under it (90 vs 200). Grid fix found under throttled verification: after invalidateMedia nothing re-fetched the first page (the sentinel observer only fires on intersection changes), so a sort or filter change left the grid empty until a scroll; the grid now loads on the "media" topic.
### src/engine/store.ts + types.ts + ui/components/grid.ts · library pages from the query engine
- refers-to: store.ts loadMore params + fetch, PageState.next, SortOrder, QueryRule/QuerySpec, LEGACY_SPECS, specKey, quickRules, specFor, setQuickFilter, state.quick; types.ts MediaPage.next, FilterName spec union, Media v5 fields, MediaDetails; grid.ts groupOf + ensureDay label arg
- kind: rationale + removed code
- logged: zip v1.22.0 · 2026-10-10

Pages now load from /api/browse with a JSON spec instead of /api/media?filter=, so every view can combine flags, rating, label & keyword quick filters & sort by date taken, date added, name, size or rating. The legacy filter names map to specs (LEGACY_SPECS), so routes & sidebar links are unchanged; custom views register a spec once & key their page by `spec:<json>`. The cursor is opaque ({v,id,k}) bc the sort column varies. Removed from loadMore: `const params = new URLSearchParams({ filter, limit: "400", order: state.sort }); if (page.next) { params.set("before", String(page.next.before)); params.set("before_id", String(page.next.before_id)); }` & the `/media?` fetch. Day sections follow the sort: date-taken sorts group by day, date-added sorts by import day, every other sort is one section, so a name sort is not shredded into day fragments.
### src/engine/theme.ts + src/theme/tokens.css + src/ui/components/settings.ts + src/styles/app.css · liquid glass parity w/ nodemode_dev v8.70.6
- refers-to: theme.ts :: GlassPrefs.ver, DEFAULT_THEME.glass, loadTheme glass merge, applyTheme brightness + sheen + rim lines; tokens.css glass block; settings.ts PRESETS Standard; app.css .pop-surface
- kind: rationale + replaced values
- logged: zip v1.19.0 · 2026-09-18

Reference: nodemode_dev frontend/src/styles/simplicity-overlay.css (the liquid-glass Create UI) & frontend/src/styles/nodes.css (glass-for-real). DAM's glass.css already carries the same three-layer primitive (fill + blur/saturate/brightness + shadow stack; ::before gradient rim through the padding mask; ::after specular sheen w/ the top highlight), so the port is values, not structure. The look is written at runtime by applyTheme from the Window sliders, so parity lands in three places: DEFAULT_THEME.glass now resolves to NodeMode at the default positions (blur 36 = 36px, frost 1.9 = 190% saturate & 1.08 brightness via 0.9 + frost * 0.095, opacity 0.38, gradient 1 = rim 0.32 / 0.07 / white 0.02 & sheen 0.075), tokens.css carries the same numbers plus NodeMode's shadow stack & a 1px rim so first paint equals the runtime values, & saved glass prefs without ver 2 are ignored once (Settings writes in place & presets merge w/ Object.assign, so ver survives normal use & later tuning persists). Popovers take the glass saturate/brightness tokens & the glass shadow; their fill, border & 14px radius stay for legible menus. Not ported: NodeMode's lens distortion (backdrop-filter url(), which WebKit does not render) & the bar ring + top glow (a 1px inset ring on the sidebar/topbar would redraw a line along the window edge, the artifact class of rounds 22 to 58). Verified in headless Chromium at 4x CPU & a slow network w/ an old-recipe pref seeded: first paint 36px, live tokens exactly NodeMode's, CLS 0, no console errors. Replaced values, for restoring the old look: DEFAULT glass { strength 1, blur 22, frost 1.5, tint 0.12, gradient 0.7, opacity 0.16 }; brightness 0.9 + frost * 0.15; sheen 0.08, rim-top 0.22, rim-mid 0.07, rim-bottom accent rgb at 0.16 (all * gradient); tokens glass-bg rgba(23, 17, 12, 0.76), rim 0.38 / 0.11 / 0.15 at 0.5px, sheen 0.085, blur 11px, saturate 235%, brightness 0.94, shadow 0 14px 44px .76 · 0 2px 10px .456 · inset 0 1px 0 .01 · inset 0 0 0 .5px .003 · inset 0 -14px 30px -18px .646; pop-surface saturate(175%) & shadow 0 24px 64px .62 · 0 3px 12px .45; Standard preset = the old DEFAULT.
### repo-wide · rename DAMp to DAM, part 3: copy, events & ids
- refers-to: ui/components/settings.ts Keychain + menu bar copy; ui/components/people.ts banner copy + dam-people-picked (dispatch, add, remove); ui/components/collections.ts shared-albums copy + text/dam-section (set, get); ui/components/search.ts hint; engine/theme.ts dam-vib style id; styles/app.css dam-spin & dam-shimmer keyframes; theme/tokens.css & theme/icons.js pack header; public/DAM-icon.svg ids
- kind: rationale
- logged: zip v1.18.2 · 2026-09-18

Each internal name was renamed at its definition & every use in the same round, so events, drags, animations & SVG references stay connected (checked: the SVG parses w/ 10 ids, 10 references & none unresolved; the built CSS carries the new keyframes). Copy & attribute values only; no DOM behavior changed.
### repo-wide · rename DAMp to DAM, part 2: request headers
- refers-to: src/engine/api.ts authHeaders + api() + apiUpload; src/ui/components/importer.ts device thumb fetch; src/main.ts window-state posts; tests/api.test.ts expectations
- kind: rationale
- logged: zip v1.18.1 · 2026-09-18

x-dam-local & x-dam-vault, renamed w/ the engine & shell in the same round (the engine now answers the old spelling w/ 403). No DOM code touched. Part 3 still owes the UI copy (settings, people, collections, search), the custom event & drag type names, the CSS keyframes & style element id, the SVG ids & the theme pack headers.
### repo-wide · rename DAMp to DAM, part 1: page identity
- refers-to: public/DAM-icon.png + public/DAM-icon.svg (renamed files); index.html title + favicon; public/splash.html title + img; src/ui/components/sidebar.ts side-brand; src/main.ts dam-menu listener; package.json + package-lock.json name
- kind: rationale
- logged: zip v1.18.0 · 2026-09-18

Visible identity only: the icon files were renamed & every reference followed (same pixels & dimensions, so the brand mark keeps its reserved box); the Settings menu event is dam-menu on both sides of the shell bridge in the same round, so the menu item never goes deaf. Static values set at build or mount time; no runtime DOM behavior changed. Part 2 renames the internal names (x-damp-* headers, damp-people-picked, text/damp-section, damp-vib, damp-spin/shimmer keyframes, SVG ids, theme pack headers, UI copy).
### src/ui/components/trash.ts · vaultGate hint copy
- refers-to: trash.ts :: vaultGate :: hint (both branches)
- kind: rationale
- logged: zip v1.17.0 · 2026-09-18

The vault passkey now encrypts Hidden, Recently Deleted & private-album media on disk (engine side), so the setup text says so & warns that a forgotten passkey makes those items unrecoverable, pointing at the Keychain save. Static copy only, set once when the modal opens: no DOM behavior changed. No URL or fetch change was needed anywhere (api.ts, grid.ts, viewer.ts): tag-driven thumb & file loads authorize through the HttpOnly cookie the engine sets on unlock.

### src/ui/components/importer.ts + viewer.ts + grid.ts · device browse grid & Live Photos
- refers-to: browsePanel/openBrowse/pumpThumbs/runDeviceImport; /idevice/contents+thumb+session/close; gen threading; .ptile & .live-chip & .live-btn css; viewer liveHolder/playLive; Media.live_video_id
- kind: explainer
- logged: zip v1.16.0 · 2026-07-31

Photos-model interaction: a ready device row is now a button that opens an in-page contents grid (name, count, Select All/None, Import Selected (n) / Import All, opt-in "Delete from the device after a safe import"). Thumbs stream through a 4-wide fetch pump into object URLs (revoked on close/teardown; a generation token drops stale responses), missing thumbs keep the kind glyph, video tiles carry durations, & selection reuses the sel-dot pattern. The contents generation from the backend threads through import & thumb calls so a stale grid errors w/ guidance instead of importing wrong keys. Import completion w/ deletion on reloads the grid (device contents changed); the roster poll closes the grid if the device vanishes; teardown closes the session unless a job is mid-flight (backend also guards). AFC fallback rows keep the plain Import All button. Live Photos: grid tiles & viewer badge LIVE; the viewer's live-btn plays the companion video in a stacked stage layer (in-place, ended/click/step all stop it, zero rebuild of the img machinery) & the info panel reports Kind: Live Photo.

## Org-navi-map

```
frontend/
├── index.html               shell, loads tokens/glass/app css + main.ts
├── vite.config.ts           127.0.0.1:5173, /api proxy to backend :8000
├── vitest.config.ts         jsdom test environment
├── tsconfig.json            strict + noUnusedLocals/Parameters
├── package.json             v0.1.0, dev deps only (vite/ts/vitest/jsdom)
├── public/
│   ├── DAMp-icon.svg        source monogram artwork (user-provided)
│   └── DAMp-icon.png        canonical app mark (user-provided, verbatim)
├── src/
│   ├── main.ts              hash router, shell mount, route teardown
│   ├── theme/
│   │   ├── tokens.css       vendored kit tokens, accent re-cut to amber
│   │   ├── glass.css        vendored glass panel kit
│   │   ├── icons.js         vendored glyph pack + 14 DAMp glyphs
│   │   └── background.js    vendored interactive background (unused yet)
│   ├── styles/
│   │   └── app.css          app layout, grid, viewer, cards, modals
│   ├── engine/
│   │   ├── types.ts         API payload interfaces
│   │   ├── api.ts           fetch wrapper, local + vault/album tokens
│   │   ├── format.ts        bytes, durations, day/month labels
│   │   └── store.ts         state, pub/sub topics, page caches, actions
│   └── ui/
│       ├── dom.ts           h() builder + delayedIndicator (vendored)
│       ├── icons.ts         iconEl/iconInto wrappers
│       ├── toast.ts         bottom-center toasts
│       ├── modal.ts         modal + text field primitives
│       └── components/
│           ├── sidebar.ts   nav sections, album rows, active highlight
│           ├── library.ts   topbar (seg/zoom/filter menu) + grid mount
│           ├── grid.ts      day-grouped tiles, months/years, sentinel
│           ├── viewer.ts    lightbox, info panel, favorite/trash
│           ├── selectbar.ts multi-select bar, add-to-album w/ unlock
│           ├── collections.ts strips + count cards + empty states
│           ├── albums.ts    album pages, create/unlock/rename flows
│           ├── people.ts    people grid, scan banner, person page
│           ├── trash.ts     vault gate, trash rows, restore/purge
│           ├── dedup.ts     threshold slider, set cards, resolve
│           └── importer.ts  path input, move toggle, job progress
└── tests/                   vitest (format, store, api)
```

## Table of contents

- [src/theme/tokens.css + icons.js](#srctheme)
- [src/engine/api.ts](#srcengineapits)
- [src/engine/store.ts](#srcenginestorets)
- [src/ui/components/grid.ts](#srcuicomponentsgridts)
- [src/ui/components/viewer.ts](#srcuicomponentsviewerts)
- [src/ui/components/albums.ts](#srcuicomponentsalbumsts)
- [src/ui/components/trash.ts](#srcuicomponentstrashts)
- [src/ui/components/selectbar.ts](#srcuicomponentsselectbarts)
- [src/ui/components/collections.ts](#srcuicomponentscollectionsts)
- [src/ui/components/library.ts](#srcuicomponentslibraryts)
- [src/main.ts](#srcmaints)

## public

### public/DAMp-icon.png · canonical mark adoption
- refers-to: public/DAMp-icon.png + src-tauri/icons/icon.png
- kind: removed-code
- logged: v0.2.0 · 2026-07-25

v0.1.0 shipped a Claude-composed `DAMp-appicon.svg` (rounded rect side 696 rx 96 rotated 45, art paths at scale 0.75, two-layer feFlood/feGaussianBlur/feMerge neon) plus a cairosvg-baked `DAMp-appicon-512.png`. Both removed: the user delivered the final refined mark (two-tone gold/orange, glow baked in, 1024 RGBA w/ transparent corners) w/ the instruction to use it verbatim. That PNG is now the single source: web favicon, sidebar brand img, & src-tauri/icons/icon.png (from which `cargo tauri icon` derives the .icns set). The removed SVG's composition math survives in this entry should a scalable variant ever be wanted again.

### src/ui/components/sidebar.ts · brand mark as img
- refers-to: sidebar.ts :: side-brand block
- kind: rationale
- logged: v0.1.0 · 2026-07-25

The brand uses `<img src="/DAMp-appicon.svg">` instead of a glyph: the mark is multi-color w/ its own glow, so it does not belong in the currentColor icon system. Fixed 26px box, no layout shift.

### repo-wide · rename photolakit to DAMp
- refers-to: all frontend files
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Mechanical sweep before first ship: headers x-photolakit-* to x-damp-*, localStorage keys photolakit.zoom/.grouping to damp.*, package name to damp-frontend, kit name to damp-amber, spinner keyframe pl-spin to damp-spin, brand text to DAMp. No behavior change.

### src/ui/components/sidebar.ts · version foot
- refers-to: sidebar.ts :: foot / mountSidebar
- kind: explainer
- logged: v0.2.0 · 2026-07-25

Bottom-of-sidebar `v0.2.0` foot filled from /api/health, satisfying the director gate that the UI version matches tauri.conf.json, Cargo.toml, package.json & the zip suffix. margin-top auto pins it; textContent set once on response, no flash.

### package.json · toolchain security majors
- refers-to: package.json :: devDependencies + package-lock.json
- kind: rationale
- logged: v0.2.1 · 2026-07-25

npm audit flagged 5 advisories rooted in the shipped lockfile pinning vite 5.4.x (high: optimized-deps .map path traversal; launch-editor NTLM disclosure) & vitest 2.1.x (critical: UI server arbitrary file read/execute), plus esbuild/vite-node/@vitest/mocker moderates. Bumped to vite ^8.1.5 / vitest ^4.1.10 / jsdom ^29.1.1 & regenerated the lock; typescript stays ^5 (no advisory, & the 7.x native compiler is a deliberate future migration, not a hotfix). All dev-time only, but the vitest hole is a real dev-machine RCE, so the lockfile ships regenerated & authoritative. Suite & build verified unchanged on the new majors.

### src/engine/theme.ts · derivation model
- refers-to: theme.ts :: applyTheme
- kind: rationale
- logged: v0.3.0 · 2026-07-25

One hex accent drives everything: accent-2 is a 35 percent lighten, glow/soft are alpha rgba of the same channels, so icons (currentColor), the hex background (reads --accent live) & glass rims all follow a single swatch or the custom picker. The six glass sliders map onto the kit tokens · blur & opacity scaled by a master strength, frost to saturate+brightness, tint mixes accent channels into the glass bg rgba, gradient scales sheen & the three rim stops. Values persist in localStorage damp.theme & applyTheme runs at main.ts module top, before first paint, so there is no unthemed flash.

### src/ui/components/settings.ts · settings surface
- refers-to: settings.ts :: openSettings / registerBackground
- kind: explainer
- logged: v0.3.0 · 2026-07-25

Gear in the sidebar foot. Sections: accent (6 swatches + type=color custom), liquid glass sliders, hexagon background toggle (wired to main.ts's mount/dispose via registerBackground), native window translucency toggle (adds html.vibrancy so the shell's UnderWindowBackground material shows through; browser dev stays opaque), library/db/models paths from /health, & the Keychain enable flow (non-darwin shows the Touch ID roadmap note instead).

### src/main.ts · hexagon background config
- refers-to: main.ts :: backgroundControl / mountBackground overrides
- kind: rationale
- logged: v0.3.0 · 2026-07-25

The vendored deduplakit kit module already ships a rounded-hex custom shape & reads --accent live; DAMp mounts it w/ fillCells:false (hollow strokes, per the ask), cell 44, corner 8, lineWidth 1.6, strokeAlpha 0.5, washAlpha 0.04, radius 300 · calm drift w/ pointer-reactive comet trails in the accent color. #app sits at z-index 1 above the fixed z-0 canvas; disable disposes the mount entirely.

### src/styles/app.css · scrollbars & centered empties
- refers-to: app.css :: scrollbar rules / .empty-center
- kind: explainer
- logged: v0.3.0 · 2026-07-25

scrollbar-width:none + webkit display:none globally · wheels, trackpads & keyboard scrolling untouched. Empty cards across pages now sit in .empty-center (flex, 42vh min-height, centered text) instead of hugging the container's top-left.

### src/ui/components/collections.ts · layout persistence
- refers-to: collections.ts :: SECTIONS / layout / /prefs/collections
- kind: rationale
- logged: v0.3.0 · 2026-07-25

Sections became a keyed registry; Customize mode adds drag handles (HTML5 dataTransfer text/damp-section, drop-before semantics) & eye toggles. Order + hidden persist server-side at /prefs/collections rather than localStorage so the arrangement follows the library across browsers & the desktop app.

### src/ui/components/people.ts · select mode & faces strip
- refers-to: people.ts :: selectMode / picked / mergeBtn / loadFaces
- kind: explainer
- logged: v0.3.0 · 2026-07-25

Select toggles card-click into multi-select (accent outline); the action bar offers Merge (keep-which modal, POST /people/merge), Hide (PATCH hidden) & Remove (DELETE, faces unassigned). The person page gained back navigation, dblclick inline rename, & the best-crops strip from /people/{id}/faces w/ per-face unassign · the visible face of the correction loop that trains matching. Marquee drag-select intentionally not in this build; click multi-select shipped instead.

### src/ui/components/grid.ts · hover video previews
- refers-to: grid.ts :: tileFor video branch
- kind: warning-context
- logged: v0.3.0 · 2026-07-25

mouseenter builds a muted looping <video> absolutely positioned over the poster & plays it; mouseleave pauses & removes it. The element is created lazily per hover · never at grid render · so a thousand-tile grid still allocates zero players until pointed at. Range-request streaming makes local playback effectively instant.

### src/theme/background.js · honeycomb extension (vendored file modified)
- refers-to: background.js :: HEX/stepY/centerX/centerY + case "hexes"
- kind: provenance
- logged: v0.4.0 · 2026-07-25

Round 2 exposed that the kit's cells pattern draws square cells; its hexagon custom shape only shapes the pointer-influence falloff. The vendored module is now extended (smallest possible diff, all original patterns intact): a hexes pattern adds offset-row lattice math (vertical step cell x 0.8660254, odd rows shifted half a cell) in both the stamp field & the draw loop, & a pointy-top rounded-hexagon path (six vertices, arcTo corners capped at 0.42R). DAMp mounts pattern hexes, hollow (fillCells false), cell 46, corner 5. Node-side source assertions in the build turn verify the lattice constants & draw mapping are present.

### src/styles/app.css · glass surfaces & text-only day heads
- refers-to: app.css :: .sidebar / .topbar / .day-head
- kind: rationale
- logged: v0.4.0 · 2026-07-25

The sliders drove correct tokens into a UI where almost nothing was glass, so they read as doing nothing. Sidebar & topbars now consume the full stack (glass-bg, backdrop blur/saturate/brightness, glass borders) over the animated background, & theme defaults rose (blur 22, opacity 0.16) so Strength/Blur/Frost/Tint/Gradient/Opacity each visibly transform the app. Day heads: gradient removed per the ask; sticky text + count only, w/ a text shadow for legibility over media.

### src/ui/marquee.ts · drag-select
- refers-to: marquee.ts :: attachMarquee
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Pointer-drag on blank container space (6px threshold so clicks stay clicks) draws a fixed-position rectangle & live-applies intersection against item rects, w/ the pre-drag selection kept as a baseline so marquee adds rather than clobbers. Wired to the Library scroller (store selection) & the People grid (picked set, auto-entering Select mode). Buttons, inputs, video & modal surfaces never start a marquee.

### src/ui/components/people.ts · hardened select + reassign
- refers-to: people.ts :: setSelectMode / sel-dot / reassign block
- kind: explainer
- logged: v0.4.0 · 2026-07-25

Select mode now renders a check dot on every card, whole-card toggling, Select All/None, Esc to exit, & marquee integration. The person page's Reassign faces mode turns the best-crops strip into a picker w/ Move to... (existing person or Create & move), using PATCH /faces/{id}/person; the first move materializes a new person & the rest follow into it.

### theme.ts · tint & frost go opaque
- refers-to: shade() replacing surf(); --vib-body/side/top as rgb() not rgba(); Fade amount bound to winFade (window opacity)
- kind: rationale
- logged: zip v1.14.5 · 2026-07-26

W/ transparency mode gone, background alpha has no meaning: there is nothing behind the page to reveal. Tint & frost therefore became opaque recolouring of the app's own surfaces (tint walks the theme base toward black above 0 & toward warm light below 0; frost lifts toward white; sidebar & topbar derive as 1.7x & 1.35x shades), & the fade is macOS window opacity again, which is the mechanism the user verified. Rule: when a control's medium is removed, re-express the control in the medium that remains rather than leaving it inert.

### settings · one fade, four controls
- refers-to: Window fade section (bgFade/vibTint/winFrost/winBlur relabelled Fade amount/tint/frost/blur); native window opacity retired & pinned to 100
- kind: correction
- logged: zip v1.14.4 · 2026-07-26

Three misreadings in a row, all mine, all from treating an ambiguous phrase as settled instead of restating the target before building. The instruction, read together across turns, was: no macOS transparency feature at all, & the fade (a) affects only the app background & (b) owns tint/frost/blur. Shipping two fades side by side (v1.14.3) was hedging, & forcing translucency on (v1.14.1) was the opposite error. Final shape: one section, Fade amount owns opacity, tint colours the residue, frost whitens it, blur is the behind-window radius; macOS window opacity is never called & is actively zeroed at boot to clear values older builds stored. Rule extracted: when an instruction has been misread twice, write the intended end state in one sentence & build to that sentence, rather than patching the previous interpretation.

### settings · both fades, side by side
- refers-to: winFade slider restored (WINALPHA) next to bgFade; boot sends the saved alpha again
- kind: correction
- logged: zip v1.14.3 · 2026-07-26

I removed the native whole-window fade in v1.14.1 on the reasoning that its scope was wrong, but the user had confirmed it working & relied on it: deleting a functioning control to tidy the model is a regression no matter how clean the replacement looks. Restored w/ identical behaviour (30-100, default off, persisted, re-applied at boot) & placed BELOW the background group w/ a one-sentence note explaining that it composites the finished window & therefore fades content too. Rule extracted, second time this session: never delete a capability the user has confirmed works · deprecate it in place, label it honestly, & let them choose.

### grid.ts · the null root that cached itself
- refers-to: thumbObservers Map; awaitingAttach + sweepAwaiting; scrollerFor; sentinel rebuild
- kind: correction
- logged: zip v1.14.2 · 2026-07-26

The preload was present but self-disabling. observeThumb deferred one rAF, then took img.closest(".view"); tiles are constructed detached & appended in batches, so that lookup often returned null, which created an observer rooted at the VIEWPORT · & a viewport rootMargin cannot see past an inner scroller's clip, so lookahead became zero. The null was then cached in thumbRoot, so every subsequent tile matched it & reused the inert observer: a single early tile disabled preloading for the rest of the session. Fix: a null root is never acceptable, unattached images are queued & retried per frame (40 frames, then loaded so nothing stays blank), observers live in a Map keyed by scroller, & the pagination sentinel rebuilds itself if its host was detached at creation. Rules extracted: never let a fallback value that means "wrong behaviour" be cached as if it were valid; & when an element's ancestor matters, do not assume attachment · wait for it.

### the Window glass group · one axis per idea
- refers-to: bgFade (owns alpha) + vibTint (colour only) + winFrost + winBlur; vibrancy forced true; native whole-window opacity retired & pinned to 100
- kind: correction
- logged: zip v1.14.1 · 2026-07-26

Two overlapping opacity controls (a native whole-window fade & a background paint multiplier) plus a toggle made the section unreadable & let tint magnitude secretly scale alpha. Restructured to one axis per idea: fade = how much background exists, tint = its colour, frost = how white, blur = desktop blur strength. The native fade is retired because NSWindow opacity composites the FINISHED window & therefore can never be background-only · the user's complaint that it faded photos was a property of the primitive, not a bug to tune. Translucency is no longer optional (no checkbox), so the glass path is the only path & saved prefs migrate to it: bgFade = 100 - old winAlpha. Rule extracted: when a user says a control affects too much, check whether the PRIMITIVE can express the scope they want before trying to tune it.

### theme.ts · !important override sheet
- refers-to: injected <style id="damp-vib"> covering html/body/#app/main/.content/.view/.view-pad
- kind: rationale
- logged: zip v1.13.998 · 2026-07-26

Rather than keep auditing stylesheets for an opaque rule I might not find, the vibrancy paint is now emitted into a dedicated style element at !important strength. That is authority above every author rule in the app, so the page cannot be the cause any more · which also makes the native diagnostic conclusive when it says window_opaque=0. Rule: when a cascade bug resists auditing, assert the intended value at an authority level nothing else can reach.

### settings · Match Terminal glass
- refers-to: termBtn preset (tint 49 / transparency 100 / frost 0 / blur 13)
- kind: explainer
- logged: zip v1.13.996 · 2026-07-26

Decoded from the user's shipped nodemode_ai.terminal: BackgroundColor archive contains the literal component string "0 0 0 0.4861924866" & BackgroundBlur 0.261. Our paint alpha = |tint|/100 x transparency/100, so tint 49 + transparency 100 reproduces 0.49 over near-black; blur 13 approximates Terminal's normalized 0.261 on the community-documented ~0-50px compositor scale (approximation noted honestly). The preset also switches translucency on, so it is a single click from any state.

### the material was the mask · terminal model adopted
- refers-to: pushWindow sending {material,blur}; boot terminal-model sync; winBlur default 28 & zero-migration
- kind: correction (arc-closing)
- logged: zip v1.13.994 · 2026-07-26

Three rounds, one arc, closed. v1.13.991 felt right bc NSWindow alpha faded the MATERIAL too; page-space paint (.992/.993) was the right layer but changed almost nothing visually bc the material behind it is itself a dark blurred sheet · lowering page alpha just showed more material. Terminal's recipe: no material at all, CGS radius for softness, own paint for tint. Implemented: vibrancy on -> {material:false, blur:saved} (boot & toggle & slider all send it); vibrancy off -> material restored, radius 0. Stored winBlur 0 migrates to 28 bc 0 predates blur functioning (1 = visually none, an accepted asymmetry, recorded here). Rule extracted: when adjusting a layer produces no visible change, the layer BEHIND it is probably opaque enough to be the real subject.

### theme.ts · the color-mix that painted nothing
- refers-to: precomputed --vib-body/--vib-side/--vib-top rgba; removal of the nested color-mix rules
- kind: correction
- logged: zip v1.13.993 · 2026-07-26

The v1.13.992 surfaces multiplied a percentage by a plain number inside color-mix's percentage slot (calc(var(--vib-alpha) * 1% * var(--win-alpha) / 100)) & fed a var-defaulting-to-var base into a nested color-mix; either alone can invalidate the color, & an invalid component makes the browser drop the WHOLE background declaration silently. Result: zero paint, read by the user as "transparency is gone", w/ frost & the transparency slider dead in the same expression. Removed-code: the three nested color-mix rules. The paint is now one JS function producing plain rgba (base picked by tint sign, frost lifting toward white, alpha = |tint| x survival), & the CSS references single variables w/ safe fallbacks. Rule extracted: when a CSS color expression carries multiple interacting vars, compute it in JS & hand CSS a finished value; a declaration that can fail partially will fail wholly & silently.

### window transparency re-scoped + frost
- refers-to: --win-alpha/--win-frost multipliers in the vibrancy paint; NSWindow-alpha UI retirement; boot alpha 100
- kind: correction
- logged: zip v1.13.992 · 2026-07-26

NSWindow alpha was categorically wrong for "window transparency": it is a whole-layer-tree opacity, so it dimmed photos & panels · the thing the user explicitly did NOT want. Transparency & frost are now pure background paint math: the vibrancy surfaces multiply their alpha by --win-alpha/100 & mix toward white by --win-frost, so only the window background moves & content stays solid. The shell alpha path is retired from the UI but kept in the binary; boot POSTs alpha 100 once so a fade written by v1.13.99/.991 is cleared. Rule: match the control to the layer it should touch · a whole-window primitive cannot express a background-only intent.

### settings + theme · the Window trio
- refers-to: signed vibTint (--vib-base white below zero); winAlpha/winBlur prefs + pushWindow; boot re-apply in main.ts
- kind: rationale
- logged: zip v1.13.99 · 2026-07-26

Zero page-paint is a floor, not a ceiling: the material itself tints, so "more transparent than 0" required inverting the paint · negative tint mixes translucent warm white (#f5f2ec) instead of the theme base, one signed slider, one honest axis. Alpha & blur are not page concepts at all, so they travel the control channel as numbers & the page merely remembers them (prefs) & re-asserts at boot; sliders debounce 80ms so drags cost a trickle of POSTs. The note under the trio says exactly which layer each control touches, bc three transparency-adjacent sliders w/o that sentence would be a riddle.

### grid.ts · observers rooted at the real scroller
- refers-to: ensureThumbObserver(root)/observeThumb/resetThumbLookahead; sentinel root; --vib-alpha/--vib-black split
- kind: correction
- logged: zip v1.13.97 · 2026-07-26

The lookahead I shipped twice was inert: rootMargin expands the ROOT's box only, & w/ the default (viewport) root it cannot see past clipping by the inner .view scroller, so tiles loaded exactly at the visible edge no matter the margin. Both observers now take the .view element as root; thumbnails resolve it at attach time via a one-frame defer (tiles are built detached), & root or zoom changes rebuild the observer over all pending imgs. Rule extracted: an IntersectionObserver's margin is meaningless unless its root is the element that actually scrolls. Tint overdrive: alpha saturates at 100%, so past 100 the tint COLOR walks toward black (two vars, nested color-mix) · same honesty pattern as the Glow overdrive.

### grid lookahead + vibrancy tint + explicit canvas alpha
- refers-to: lookaheadPx/resetThumbLookahead; sentinel margin; --vib-tint & the slider; kit ctx alpha:true + transparent layer styles
- kind: rationale + vendored-kit change
- logged: v1.13.9 · 2026-07-26

Lookahead is now expressed in the unit the user experiences (rows of the current tile size, 13 each way) instead of a fixed pixel guess; zoom changes rebuild the observer so the promise holds at every size. The vibrancy work is honest instrumentation: the kit paints no base sheet (verified; clearRect + pointer-only content), so the shipped changes are (a) explicitness that removes WKWebView's accelerated-canvas ambiguity & (b) a Window tint variable (0-80, all three vibrancy surfaces scale from it) whose zero point makes the page provably paint-free · the user can convict canvas vs OS in seconds. Rule: when a rendering suspicion cannot be reproduced in-container, ship the experiment as a feature.

### src/theme/background.js + settings · Glow & Bloom decoupled
- refers-to: glowWidth in DEFAULT_CONFIG & the lit-pass lineWidth; migrateBg in theme.ts; bgConfig mapping; two slider rows
- kind: rationale + vendored-kit change
- logged: v0.13.94 · 2026-07-26

One slider drove two unrelated quantities (stroke alpha & wash alpha), so neither could be pushed or killed alone. Split: Glow maps 0-100 onto stroke alpha 0-1 (true zero now possible) & 100-200 onto a lit-pass width multiplier up to 2.4x, bc alpha saturates at 1 & honest "stronger" needs a second physical dimension; Bloom maps 0-200 onto wash alpha 0-0.26. The kit edit is ONE line (lit pass lineWidth * glowWidth; the base grid pass at its own assignment is untouched) + a default, recorded here as a vendored extension. migrateBg decomposes the old coupled value into equivalent positions (alpha & wash inverses of the old formulas) so persisted themes render identically before the user ever touches the new sliders.

### src/ui/components/search.ts · the scan card that cannot hide
- refers-to: refreshOcrCard rewrite; /ocr/scan force; settings pane css grid
- kind: correction
- logged: v0.13.9 · 2026-07-26

Two hiding behaviors made the feature look absent: the card keyed on the stale tesseract field (so the bundled model read as missing) & vanished at pending==0 (so post-scan or post-empty-write states offered nothing). Doctrine applied: capability surfaces stay visible w/ state, never disappear. The card now names the engine, scans pending, or force-rescans all (server nulls stored text first · required after earlier engineless builds persisted empty strings). Settings css moved from ad-hoc flex to a 3-col grid w/ a 560px measure; alignment is the presentation fix, not decoration.

### src/engine/prefstore.ts · engine-backed preferences
- refers-to: initPrefs/prefGet/prefSet; theme.ts KEY swap; store hydrateStatePrefs; localStorage removal in settings/search/albums/store
- kind: correction + rationale
- logged: v0.13.7 · 2026-07-26

localStorage silently reset every launch bc the loopback ORIGIN includes the ephemeral port; per-origin storage is the wrong tool under a port that changes. One engine-side document (/prefs/ui) now holds every UI preference; boot awaits a single loopback GET (top-level await) & hydrateStatePrefs() re-reads the store-initialized values, closing the module-eval-before-fetch gap that would otherwise feed defaults. prefSet debounces a whole-document PUT (250ms) so slider drags cost one write. Removed-code: every localStorage call site (theme, zoom/sort/grouping, searchScopes, albumsPage.collapsed, albumSort.{id}, settingsTab). Rule extracted: under dynamic-origin serving, client-side storage is ephemeral by construction; durable state belongs behind the API.

### src/ui/components/grid.ts · viewport thumbs & FLIP removal
- refers-to: ensureThumbObserver/loadThumb; slideOutAndRemove; prune branch
- kind: correction
- logged: v0.13.3 · 2026-07-26

Two scroll-era sins fixed. Loading: every fetched page set 400 img srcs at once, so the network & thumb generator stormed while you scrolled; srcs are now assigned by a shared IntersectionObserver as tiles approach (1100px margin), decode async, fade in on ready · requests scale w/ the viewport, not the page size. Removal: the prune path full-rebuilt every section (the reported flash); now the leaving tile scales/fades out, siblings are FLIP-inverted from measured rects & slide to their new spots, & day counts patch via textContent. The full rebuild survives only for genuine order changes.

### src/ui/components/settings.ts + viewer + vibrancy css
- refers-to: settings-shell nav/panes; resetBtn disabled-not-hidden; cursor scoping; html.vibrancy percentages
- kind: rationale
- logged: v0.13.3 · 2026-07-26

Settings went wide (780px) w/ a left rail bc a single tall scroll had outgrown itself; panes are plain divs toggled by class, last tab in localStorage. The viewer's reset control is disabled-not-hidden (discoverability doctrine), the crosshair belongs to the image only, & absolute stage imgs regained centering via inset:0+margin:auto (the flex parent never applied to absolute children · that was the off-center bug). Vibrancy: the material was on but the page painted over it; html.vibrancy now drops page bg to 46% (sidebar 34%, topbar 30%) · the three numbers to tune if the Terminal match needs adjusting.

### src/ui/components/importer.ts · the dropzone
- refers-to: dropZone/mediaFiles/uploadDropped; api.apiUpload; window drop defaults in main.ts
- kind: explainer
- logged: v0.13.1 · 2026-07-26

Drag depth is counted (enter/leave fire per child) so the highlight cannot flicker; filtering accepts MIME image/* video/* OR a known extension bc HEIC often reports an empty type; apiUpload posts FormData w/ the local header & no manual content-type (the browser owns the boundary). Window-level dragover/drop preventDefault stops a missed drop from navigating the webview to a file URL. Note: this feature exists BECAUSE v0.12.0 disabled the shell's drag-drop handler; w/ it enabled the page never receives File objects.

### src/styles/app.css · pop-surface, the one container recipe
- refers-to: .pop-surface; ctx-menu dedup; class swaps in contextmenu/library/modal/selectbar/viewer/toast
- kind: rationale
- logged: v0.13.0 · 2026-07-26

The Terminal reference decided the recipe: dark ink at 64% + blur (floor 26px, follows the glass slider upward) + saturate + 1px light border + 14px radius + deep double shadow. One class owns it; surfaces keep only their layout. The ctx menu's older bespoke backdrop was REMOVED (quoted in v0.6.0's entry) so there is exactly one glass container truth. Rule: floating surfaces share one recipe class; per-surface CSS may not restate visual identity.

### src/main.ts + settings.ts · background as a themed instrument
- refers-to: bgConfig/backgroundControl.update; ThemePrefs.bg; Effect radius & Bloom sliders; resize nudge in applyTheme
- kind: explainer
- logged: v0.13.0 · 2026-07-26

The kit background already samples --accent per mount & on resize (accentRgb in background.js), so accent-following existed but lagged; applyTheme now dispatches a resize so retinting is instant. Radius maps straight onto cfg.radius; Bloom (0-100) drives strokeAlpha 0.25-1.0 & washAlpha 0.012-0.132 together so one slider means one perceptual thing. Slider drags remount the canvas behind a 140ms debounce: cheap, & the only way to change cfg w/o forking the kit.

### src/ui/components/viewer.ts · box zoom & the self-hiding strip
- refers-to: zoomLayer/zoomBox/applyZoom/resetZoom; showFilmstrip timer; savedScroll
- kind: rationale
- logged: v0.12.0 · 2026-07-26

Zoom is a single transform on a layer wrapping the double-buffered imgs: box selection converts the rect center into untransformed layer space (v = (c - t)/s), scales by min(stageW/w, stageH/h) clamped to 8, & solves t' = -s'v so the box center lands dead center; pans mutate t w/o transition; every media change resets. The strip inverts its old presence model: hidden by default, .visible on hover (held while hovered) or for 1300ms after any sync, w/ opacity+rise transitions so appearing is as quiet as leaving. The viewer also snapshots the underlying .view scrollTop at build & restores it on teardown, closing the jump-to-top on exit.

### src/ui/components/albums.ts · pointer-based reorder
- refers-to: reorderable pointerdown lift/track/commit; main.rs disable_drag_drop_handler
- kind: correction
- logged: v0.12.0 · 2026-07-26

Two rounds of HTML5-drag fixes failed bc the SHELL's drag-drop handler intercepts drag events in the webview before the page sees them; CSS opt-outs could never win. The handler is now disabled on the window, & reorder no longer uses HTML5 DnD at all: pointerdown arms at a 7px lift, elementFromPoint drives live before/after indicators, release commits the order & a capture-phase guard eats the trailing click. Rule extracted: in an embedded webview, interaction features must not depend on machinery the shell can intercept.

### src/main.ts · route scroll memory
- refers-to: scrollMemory/saveScroll/restoreScroll
- kind: explainer
- logged: v0.12.0 · 2026-07-26

Scroll position is saved per route hash on leave & restored after mount w/ a two-frame settle (grids render synchronously from cached pages, so the first frame usually lands; the second corrects if late content shifted). People -> person -> back now returns to the exact tile row.

### src/ui/components/viewer.ts · build-once/patch-forever
- refers-to: build()/update()/showImage double-buffer/stripSlot; removed-code: per-step rebuild
- kind: correction
- logged: v0.11.0 · 2026-07-26

Removed the per-step teardown:

    root.replaceChildren(top, main);  // every arrow/wheel step rebuilt the whole viewer

That one line was the reported flash (full-size img recreated & re-decoded per step) AND the carousel glitch (the persistent filmWrap got re-parented, which resets scrollLeft in WebKit, so the strip re-animated from the left edge on every step). The viewer now builds its chrome once per open; steps swap media through two stacked imgs (back buffer loads the 768 thumb hidden, cross-fades on load, then upgrades src to the original in place, all guarded by a media sequence counter), patch textContent/attrs/disabled states, & call syncFilmstrip only. Buttons read currentId() at click time so persistent handlers stay correct. Doctrine line honored at last: state changes patch nodes, never rebuild live containers.

### src/ui/components/importer.ts · From iPhone section v2, auto-detection
- refers-to: phoneTimer/lastRoster/phoneStatus; /idevice/status detail shape; route teardown clearing the interval
- kind: correction
- logged: zip v1.15.0 · 2026-07-31

Manual-Refresh-only detection read as dead on real hardware, & a hidden section could not say WHY it was hidden. Now: a 3s poll runs while the page is mounted (document.hidden & in-flight guarded, cleared in the route teardown), so a plugged-in iPhone appears on its own like Photos; a roster fingerprint (serial|name|state) gates replaceChildren so unchanged polls re-render nothing (zero-flash doctrine); a persistent status line under the list carries watching/errors/backend reasons instead of one-shot toasts; & on macOS an unsupported engine now SHOWS the section w/ the backend's reason (disabled-with-reason over hidden, same ux doctrine as the trust states). Locked rows & the hint teach the iOS 26 Wired Accessories approval alongside Trust This Computer.

### src/ui/components/importer.ts · From iPhone section
- refers-to: phoneSection/refreshDevices; /idevice endpoints; theme/icons.js device glyph
- kind: explainer
- logged: v0.11.0 · 2026-07-26

Availability-gated section (status endpoint) so browser mode & non-Mac never show a dead feature. Device rows carry the trust-state guidance inline (disabled-with-reason over hidden, per the ux doctrine); import reuses the existing job progress banner & summary refresh. The glyph joined the kit module in its generated format rather than a one-off ad-hoc SVG elsewhere.

### src/ui/components/trash.ts · zero-IPC unlock
- refers-to: vaultGate bio branch; tauri.d.ts deleted
- kind: correction
- logged: v0.10.0 · 2026-07-26

The window.__TAURI__ branch could never execute (remote-origin pages get no IPC) & its catch-all fallback hid that for four versions. vaultGate now makes ONE engine call (POST /vault/bio/unlock) when the shell reports available+stored; everything privileged happens beyond the page. Rule extracted: any fallback that can mask a feature being entirely dead must be able to tell the difference (here the status endpoint distinguishes shell-absent from declined).

### src/ui/components/viewer.ts · wheel gesture latch
- refers-to: buildFilmstrip wheel handler (wheelLatched/wheelQuiet)
- kind: correction
- logged: v0.9.1 · 2026-07-25

The 240ms cool-down (v0.7.0) treated a trackpad flick as an instant, but macOS momentum streams wheel events for 1s+; the cool-down expired mid-tail & each expiry let the decaying deltas step again · the reported full slide. The latch inverts the model: step once at the threshold, then swallow everything until 160ms of silence (each event postpones re-arm), bc a gesture ENDS when its events stop, not when a timer says so. DOM wheel events expose no phase info in WKWebView, so the quiet-timer is the reliable end-of-gesture signal. 160/42 are feel-constants recorded in BUILD_NOTES for tuning on hardware.

### src/ui/components/viewer.ts · windowed filmstrip
- refers-to: filmMaterialize/FILM_STRIDE/FILM_WINDOW; scroll-follow handler; arithmetic centering
- kind: correction
- logged: v0.9.0 · 2026-07-25

The persistent strip (v0.6.0) fixed rebuild-churn but kept a hidden flaw: one eager <img> per item in the whole set. In WKWebView, loading=lazy inside a clipped horizontal scroller is unreliable, & the v0.8.0 cache-version flush turned every request into a generation, so a large set issued hundreds of thumbnail jobs on open · only the first screenful (twelve at 58px stride in a 720px strip) ever behaved. Now: full-width slot buttons preserve geometry; images materialize current+/-24 & follow the pan window; centering is scrollTo(pad + idx*stride + half - viewport/2), deterministic where scrollIntoView was not; the first sync uses behavior auto so opening lands centered w/o a sweep. Rule extracted: a media strip's DOM may scale w/ the set, but its network requests must scale w/ the viewport.

### src/ui/components/grid.ts · selection sync as a shared binder
- refers-to: bindSelectionClasses; wiring in people/hidden/search/albums
- kind: correction
- logged: v0.8.0 · 2026-07-25

The selected outline was applied by a subscription private to the Library grid; tileFor's click calls toggleSelect but deliberately does not touch classes (single source of truth). Every non-Library grid therefore selected invisibly. The sync is now one exported binder (walks .tile[data-id], toggles the class, returns its unsubscribe) mounted beside bindTileSize in all four grids. Pattern note: any behavior tiles need everywhere must live in an exported binder, not inside one page's mount.

### src/ui/components/grid.ts · chunked appends & pinch-open
- refers-to: appendItems (cursor + rAF chunks + fragments); enablePinchOpen; observer rootMargin
- kind: rationale
- logged: v0.7.0 · 2026-07-25

Pagination appended a whole 400-item page w/ one DOM call per tile in a single frame: the reported glitch. Appends now walk a cursor in 80-tile rAF chunks, batching per-day DocumentFragments, & the sentinel prefetches 1600px early so pages land offscreen. Pinch (ctrl+wheel in WKWebView) accumulates a budget & opens the tile under the cursor into the viewer; the viewer stage mirrors it to close. Thresholds (90 budget / 14 close) are feel-checks for the Mac.

### src/ui/components/selectbar.ts · one bar, contextual actions
- refers-to: setSelectbarContext; people.ts person-page registration
- kind: correction
- logged: v0.7.0 · 2026-07-25

v0.6.0 gave the person page its own fixed bottom bar, which stacked onto the global selection bar: the reported overlap. There is exactly one bar now; pages register contextual actions (person page: "Move to person...") while mounted & the registration returns its own teardown. Fixed surfaces that can coexist must share one slot; two fixed bars at one edge is a defect by construction.

### src/styles/app.css · scoped drag opt-out
- refers-to: .tile[draggable=true] rules; albums.ts click guard
- kind: correction
- logged: v0.7.0 · 2026-07-25

The v0.5.0 global `img { -webkit-user-drag: none }` (anti-ghosting) silently disabled HTML5 drag on album tiles in v0.6.0: the "drag does NOT work" report. Draggable tiles opt back in w/ -webkit-user-drag: element & pointer-inert images; a capture-phase click guard eats the click that follows a drop. Lesson recorded: global input-suppression CSS must be re-audited whenever a feature depends on the suppressed input.

### src/ui/zoomctl.ts · one zoom, every grid
- refers-to: zoomctl.ts; store.setZoom clamp 96-512; library/people/hidden/search/albums bindings
- kind: rationale
- logged: v0.6.0 · 2026-07-25

Tile size was a Library-only slider w/ a narrow range. zoomControl() renders the shared control; bindTileSize(grid) subscribes a grid's --tile to the store & returns its unbind for teardown. Pages stay dumb; the store owns the clamp & persistence.

### src/ui/components/albums.ts · manual order as a sort mode
- refers-to: album detail renderItems/sorted; PUT /albums/{id}/order; damp.albumSort.{id}
- kind: explainer
- logged: v0.6.0 · 2026-07-25

Drag-to-arrange only exists in Manual mode: HTML5 drag w/ half-tile before/after indicators, optimistic local reorder, then a single PUT of the full id order (the position column has existed since v0.1; the backend endpoint was the missing half). Newest/Oldest/Name/Size are client-side views that disable dragging; the chosen mode persists per album.

### src/ui/components/viewer.ts · persistent filmstrip
- refers-to: buildFilmstrip/syncFilmstrip/filmIds
- kind: correction
- logged: v0.6.0 · 2026-07-25

The v0.5.0 strip was rebuilt inside every render, so each arrow-step re-created every thumb: scroll position lost, images re-decoded, the glitchiness the feedback named. The strip is now built once per id-set & only the current class + smooth centering change on navigation; pointer drag pans the track; the close path resets the cached strip. Same zero-flash rule the ux doctrine applies to panels, applied to the carousel.

### src/tauri.d.ts + trash.ts · Touch ID before the passkey modal
- refers-to: vaultGate keychain branch; window.__TAURI__.core.invoke("biometric_auth")
- kind: explainer
- logged: v0.6.0 · 2026-07-25

The unlock path never consulted the stored keychain secret, so nothing ever elevated. vaultGate now short-circuits: keychain stored + shell present -> LAContext prompt -> keychain unlock endpoint -> token; anything else falls to the passkey modal. The optional __TAURI__ type is declared once in tauri.d.ts; in the plain browser the branch is skipped entirely.

### src/styles/app.css · native-feel pack & under-glass layout
- refers-to: app.css :: html/body overflow, user-select, .content > .topbar, .film-*
- kind: rationale
- logged: v0.5.0 · 2026-07-25

Per tauri-ux-intuitive: the document itself never scrolls (kills WKWebView rubber-band w/o any Rust), inner scrollers contain overscroll, chrome is unselectable w/ desktop cursor semantics while copyable values stay selectable, & drag-ghosts/search-cancel/autofill chrome are stripped. Topbars became absolute overlays so every page's content scrolls UNDER the token glass (the Photos blur-under), w/ day heads sticking at --topbar-h. The viewer filmstrip's edge caps are thin backdrop-filter strips w/ gradient masks: thumbnails sliding beneath them defocus, which is the carousel effect the feedback named.

### src/ui/contextmenu.ts · in-app right-click
- refers-to: contextmenu.ts + main.ts global handler
- kind: explainer
- logged: v0.5.0 · 2026-07-25

Global contextmenu preventDefault (editable fields exempt so paste survives) plus a positioned glass menu w/ capture-phase dismissal (pointerdown outside, Esc, window blur). Wired to tiles, person cards & album cards w/ the SAME flows the buttons use · the doctrine's rule that right-click offers what the toolbar offers · incl. addToAlbumFlow extracted from the selection bar for single-item reuse.

### src/ui/components/library.ts · marquee no-op correction
- refers-to: library.ts :: enableMarquee(view)
- kind: correction
- logged: v0.5.0 · 2026-07-25

v0.4.0 recorded Library marquee as shipped; it was not. Three coordinated string replaces targeted a variable named scroller that does not exist (the container is view), all missed together, & no compile error surfaced bc the import edit missed too. The wiring is now real, assertion-guarded at edit time, & disposed in teardown. Process note to future turns: any multi-part replace whose parts only make sense together must assert each landed.

## src/theme

### src/theme/tokens.css · accent re-cut
- refers-to: tokens.css :: --accent block
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Theme kit vendored from deduplakit (same owner, themeanizor export). Accent swapped from matrix green #7ee262/#9bef82 to DAMp amber #f0a84b/#f7c274 w/ matching glow/soft rgba values; kit name comments renamed. Everything else (glass, spacing, type) untouched so the two apps stay visually related but distinct.

### src/theme/icons.js · added glyphs
- refers-to: icons.js :: GLYPHS additions before "warn"
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Appended 14 photo-domain glyphs in the kit's exact format (24 viewBox, stroke style, escaped path strings): heart, heartFill, person, people, clock, eye, lock, albums, camera, screenshot, calendar, info, sparkle, dupes. First append shipped double-escaped quotes (`\\"`) that broke the module parse; normalized to the kit's single `\"` escaping and verified via a node import counting 65 glyphs.

## src/engine/api.ts

### src/engine/api.ts · token precedence
- refers-to: api.ts :: authHeaders / api
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Every call carries `x-damp-local: 1`; `x-damp-vault` carries the album token when the call names an albumId and that album was unlocked, else the vault token if present. Album-first matters bc a per-album passkey should keep working even when a vault token exists but the user unlocked w/ the album key. Tokens live in module memory only, on purpose: closing the tab relocks everything, mirroring Photos' behavior.

## src/engine/store.ts

### src/engine/store.ts · topic pub/sub + page caches
- refers-to: store.ts :: on / state.pages / loadMore
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Headless engine layer per architecture rules: plain state + topic listeners, zero DOM. Each filter keeps its own PageState (items, keyset cursor, loading/loaded flags) so switching filters never refetches page one and infinite scroll is per-filter. `loadMore` no-ops while loading or when exhausted, making the IntersectionObserver safe to fire repeatedly. `invalidateMedia` clears page + period caches after imports/restores/resolves, where item sets change server-side.

## src/ui/components/grid.ts

### src/ui/components/grid.ts · append-only patching
- refers-to: grid.ts :: appendItems / ensureDay
- kind: rationale
- logged: v0.1.0 · 2026-07-25

DOM-stability rule applied to the grid: tiles render once into their day section keyed by media id; page growth appends only, selection changes toggle a class, removals delete the one node. Day sections are created on first item w/ a sticky header + live count. Months/Years mode swaps the whole gridWrap (a real mode change, not a refresh) and returning to All rebuilds from cache w/o refetch.

### src/ui/components/grid.ts · thumb ready fade
- refers-to: grid.ts :: loadThumb
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Thumbs start at opacity 0 and fade in on load (error also marks ready to avoid stuck-invisible tiles); combined w/ the fixed aspect-ratio tile box there is zero layout shift and no broken-image flash while scrolling.

## src/ui/components/viewer.ts

### src/ui/components/viewer.ts · thumb-to-full swap
- refers-to: viewer.ts :: render image branch
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Opens instantly w/ the 768 thumb (already cached from the grid) while the original loads in a detached Image; on load the src swaps in place only if the viewer still shows that id. No spinner, no blank stage, no resolution pop-in jump (object-fit contain keeps geometry identical). Videos use the ranged /file endpoint so scrubbing works.

### src/ui/components/viewer.ts · in-viewer trash
- refers-to: viewer.ts :: trashBtn handler
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Trashing inside the viewer splices the id out of the viewer list and clamps the index, so the next item slides in w/o closing; store.trashMedia drops it from grid caches simultaneously.

## src/ui/components/albums.ts

### src/ui/components/albums.ts · unlock flow as a promise
- refers-to: albums.ts :: unlockAlbumFlow
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Unlock is a Promise<boolean> resolved on success or modal dismissal, letting callers (album detail 401 retry, add-to-album 401 retry) await it and re-fire the original request. Dismissal detection rides the backdrop transitionend + removed-from-DOM check to avoid a second close hook.

## src/ui/components/trash.ts

### src/ui/components/trash.ts · vaultGate
- refers-to: trash.ts :: vaultGate
- kind: explainer
- logged: v0.1.0 · 2026-07-25

Reads /vault/status first and presents setup vs unlock in one modal (Set & Unlock for first run). On 401 loading the trash the gate runs, then retries; declining navigates back so the locked page never renders empty behind the modal.

## src/ui/components/selectbar.ts

### src/ui/components/selectbar.ts · selection model
- refers-to: selectbar.ts + grid.ts :: tile-check
- kind: rationale
- logged: v0.1.0 · 2026-07-25

Photos-style: hover reveals a check on every tile; once anything is selected, plain tile clicks toggle selection instead of opening the viewer, so range-collecting is fast. The bar is a fixed bottom overlay w/ count, Add to Album (401-aware via unlockAlbumFlow retry), Delete, Clear; route changes clear selection in syncRoute.

## src/ui/components/collections.ts

### src/ui/components/collections.ts · honest empty states
- refers-to: collections.ts :: Memories/Trips/Shared sections
- kind: rationale
- logged: v0.1.0 · 2026-07-25

The screenshots show Apple's own empty cards; DAMp mirrors the layout but the copy states plainly that Memories/Trips/Sharing are not built yet, rather than implying content will appear. Count cards read from /summary via data-key so one summary refresh patches every number textContent-only.

## src/ui/components/library.ts

### src/ui/components/library.ts · one component, two modes
- refers-to: library.ts :: mountLibrary(isLibraryRoot)
- kind: explainer
- logged: v0.1.0 · 2026-07-25

The Library root gets the full topbar (Years/Months/All segmented control, zoom, filter menu); filter routes (#/f/<name>) reuse the same component w/ title + zoom only, matching how Photos presents pinned collections. The filter menu writes the hash, so filters are deep-linkable and the sidebar highlight follows.

## src/main.ts

### src/main.ts · route teardown
- refers-to: main.ts :: render / teardown
- kind: warning-context
- logged: v0.1.0 · 2026-07-25

Every mount returns a teardown that unsubscribes store listeners and disconnects observers; render always calls the previous teardown before replacing content. Skipping this leaks listeners that keep patching detached DOM after navigation.

## Round 39 · window fade background-only + preload eager + sidebar glass (v1.14.6)

### src/engine/theme.ts · fade replaces winFade/winAlpha/bgFade
- refers-to: theme.ts :: ThemePrefs / loadTheme / applyTheme paint block
- kind: rationale
- logged: v1.14.6 · 2026-07-26

fade (0-100, default 0 = solid) is the background-only control: body paint alpha = 1 - fade, colour from tint (negative paints light) lifted by frost, computed as plain rgba in JS per the round-26 rule. html.vibrancy forced transparent in the injected style so nothing opaque sits behind the transparent webview. Stored winFade (window opacity, 100=off) migrates as its inverse; winAlpha & bgFade dropped (winAlpha was already vestigial, bgFade never consumed).

### src/engine/theme.ts · removed sidebar/topbar from the vib paint
- refers-to: theme.ts :: applyTheme #damp-vib injection
- kind: removed-code
- logged: v1.14.6 · 2026-07-26

```ts
rootStyle.setProperty("--vib-side", shade(1.7));
rootStyle.setProperty("--vib-top", shade(1.35));
// & the injected rules:
html.vibrancy .sidebar { background: ${shade(1.7)} !important; }
html.vibrancy .content > .topbar { background: ${shade(1.35)} !important; }
```
Under the round-38 opaque model these painted the sidebar & topbars solid, killing their liquid glass (backdrop-filter over an opaque background shows nothing). Those surfaces are glass-token panels & must never join the window paint; only body carries the fade.

### src/styles/app.css · sidebar glass restored, stale vib rules removed
- refers-to: app.css :: .sidebar rule / html.vibrancy block
- kind: removed-code
- logged: v1.14.6 · 2026-07-26

```css
/* appended inside .sidebar after the glass declarations · won the cascade */
background: var(--bg-elev);
border-right: 1px solid var(--border);
/* late overrides */
html.vibrancy, html.vibrancy body { background: transparent; }
html.vibrancy .sidebar { background: rgba(14, 13, 10, 0.42); }
html.vibrancy .sidebar { background: var(--vib-side, rgba(10,6,3,0.34)); }
html.vibrancy .content > .topbar { background: var(--vib-top, rgba(10,6,3,0.30)); }
```
All removed: the sidebar & topbars consume --glass-bg + backdrop blur again (Liquid glass sliders consequential), the fixed 0.42 smoke had pinned the sidebar off the tokens, & the transparent-body rule is superseded by the fade paint. New: html.vibrancy background transparent + clip-path inset round 0 0 var(--win-radius) bottom corners (user's macOS 26 draws no rounded clip on transparent windows; titlebar keeps the top; token default 12px).

### src/ui/components/grid.ts · loading eager in loadThumb
- refers-to: grid.ts :: loadThumb
- kind: warning-context
- logged: v1.14.6 · 2026-07-26

Tile imgs carried loading="lazy" AND observer-driven src assignment: WebKit re-defers lazy fetches until near the visual viewport regardless of when src is set, so the 13-row lookahead fired & the browser vetoed it. loadThumb forces img.loading = "eager" · the IntersectionObserver IS the lazy loader; never reintroduce the lazy attribute on observer-managed imgs.

### src/ui/components/settings.ts + src/main.ts · window posts
- refers-to: settings.ts :: pushWindow / winFade slider / reset; main.ts :: boot window post
- kind: explainer
- logged: v1.14.6 · 2026-07-26

/system/window now takes { blur, clear }: blur = CGS desktop radius, clear = shell re-asserts the transparent backdrop. Fade itself is pure page paint so it needs no shell call, but the slider still posts (cheap robustness). Fade slider 0-100 bound to prefs.fade; reset returns it to 0 & refreshes the row; a Shell: diag line (from /system/glass) renders under the fade note.

## Round 40 · deterministic preload lanes + sidebar density (v1.14.7)

### src/ui/components/grid.ts · scroll-window lanes replace the thumb observer
- refers-to: grid.ts :: ThumbLane / laneFor / sweepLane / observeThumb / resetThumbLookahead
- kind: removed-code
- logged: v1.14.7 · 2026-07-26

```ts
const thumbObservers = new Map<Element, IntersectionObserver>();

function ensureThumbObserver(root: Element): IntersectionObserver {
  let observer = thumbObservers.get(root);
  if (!observer) {
    observer = new IntersectionObserver((entries, self) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const img = entry.target as HTMLImageElement;
        self.unobserve(img);
        const src = img.dataset.thumbSrc;
        if (src && !img.getAttribute("src")) img.src = src;
      }
    }, { root, rootMargin: `${lookaheadPx()}px 0px` });
    thumbObservers.set(root, observer);
  }
  return observer;
}

export function resetThumbLookahead(): void {
  for (const observer of thumbObservers.values()) observer.disconnect();
  thumbObservers.clear();
  for (const img of document.querySelectorAll<HTMLImageElement>("img[data-thumb-src]")) {
    if (!img.getAttribute("src")) observeThumb(img);
  }
}
```
Removed after the third on-device failure of the observer path (null root v1.14.2, lazy-attr veto v1.14.6, callback scheduling under momentum scroll v1.14.7). Replacement: per-.view lanes; pending imgs get their offset cached (gBCR relative to root, batched, only when dirty: adoption / zoom / resize / media event) & each passive-scroll rAF loads pending w/ top inside [scrollTop - L, scrollTop + clientHeight + L], L = (zoom + 12) x 13. Undefined tops load immediately (never-blank). Lanes self-delete when their root leaves the DOM. Do NOT reintroduce an observer or the lazy attribute here; the 13-row slack also absorbs small FLIP shifts between dirty marks (bulk removals re-mark via the media event).

### src/engine/theme.ts + src/styles/app.css · --glass-bg-side
- refers-to: theme.ts :: applyTheme glass block; app.css :: .sidebar background
- kind: rationale
- logged: v1.14.7 · 2026-07-26

Sidebar reads 26 percent denser than the app glass by request: sideAlpha = min(0.92, glassAlpha x 1.26), same smoke rgb, emitted as --glass-bg-side & consumed only by .sidebar (fallback var(--glass-bg)). Tracks every Liquid glass slider live. The panel deliberately blurs content passing beneath it (backdrop-filter): the no-blur rule protects content from the WINDOW fade, not from panel glass. The 1.26 factor is the one constant to tune.

## Round 41 · sidebar blur over text, the 12804 workaround (v1.14.8)

### src/styles/app.css + src/engine/theme.ts · parent-background workaround & separate sidebar blur
- refers-to: app.css :: #app / .content / .sidebar backdrop-filter; theme.ts :: --glass-blur-side
- kind: warning-context
- logged: v1.14.8 · 2026-07-26

WebKit defect (tauri issue 12804): in a TRANSPARENT window, backdrop-filter over TEXT adopts the text colour instead of blurring, while images mostly blur · the exact field symptom. Documented fix: the backdrop-filter element's parent must have a background. #app & .content therefore carry rgba(10, 6, 3, 0.02) · do NOT remove these "pointless" backgrounds, they are the workaround · & .sidebar gets translateZ(0) for its own compositing layer. The sidebar's blur is its own token, --glass-blur-side = max(18, glassBlur x 1.26), separate from --glass-blur so the sidebar defocuses content even when the app glass is dialled low. If WebKit ever fixes 12804 these can be revisited, not before.

## Round 42 · side panel system + backdrop escalation (v1.14.9)

### src/engine/theme.ts + src/ui/components/settings.ts · independent side prefs
- refers-to: theme.ts :: ThemePrefs.side / applyTheme side tokens; settings.ts :: Side panel tab
- kind: rationale
- logged: v1.14.9 · 2026-07-26

--glass-bg-side & --glass-blur-side are fed ONLY by prefs.side (opacity 0-100 -> alpha cap 0.98; blur 0-64px), controlled from the dedicated Side panel tab, defaults 58/28. The 1.26x derivation from the app glass is deleted; do not re-couple the panel to --glass-blur or the Liquid glass alpha.

### src/main.ts + src/styles/app.css · fade paint on #app, canvas in #bg-holder
- refers-to: main.ts :: bgHost; app.css :: #app / #bg-holder / .content z-index / html.vibrancy block; theme.ts :: injected vib rules
- kind: warning-context
- logged: v1.14.9 · 2026-07-26

The window-fade paint lives on #app now (body transparent) so the sidebar's PARENT carries a real background: this is the full-strength form of the upstream tauri 12804 workaround for dead backdrop-filter in transparent windows. Consequence handled: the hex canvas would vanish behind #app's paint, so mountBackground targets #bg-holder, inserted as #app's FIRST child (absolute inset 0, z 0, pointer-events none); .content carries z-index 1 to stay above it. Do not move the paint back to body or mount the canvas to body w/o revisiting both. Companions in the same fix: isolation: isolate on #app (backdrop root), translateZ(0) on .content > .view (composited text backing; fixed-position UI all lives on body so the containing-block change is safe), & -webkit-font-smoothing: antialiased on html/body (subpixel AA cannot composite over transparent backings; it is why TEXT specifically punched through the blur).

## Round 43 · prioritized fetch pipeline + collections scoping (v1.14.10)

### src/ui/components/grid.ts · bounded nearest-first scheduler
- refers-to: grid.ts :: MAX_FLIGHT / startLoad / pumpQueue / sweepLane candidates / hookPager
- kind: rationale
- logged: v1.14.10 · 2026-07-26

The preload's real bottleneck was the network, not assignment: ~6 WKWebView loopback connections serve img requests FIFO, so a 13-row burst starves viewport-entering tiles behind stale lookahead. The scheduler bounds in-flight at 14 & keeps ONLY in-window images queued, nearest-first, rebuilt from live distances every sweep (items stay in lane.pending until src is actually set, so priorities track the scroll; scrolled-away entries drop out of the queue). Do not raise MAX_FLIGHT past ~16 or bypass startLoad w/ direct img.src anywhere in grid-adjacent code: one unmanaged burst re-creates the starvation. loadImage(img, src) exists precisely so direct-URL covers (face crops) ride the pipeline. hookPager mirrors the sweep math for loadMore (scroll-driven, sentinel kept as backstop; loadMore self-guards re-entry).

### src/main.ts + src/styles/app.css + collections.ts · Collections-only panel glass & uncapped strips
- refers-to: main.ts :: route-collections toggle; app.css :: .sidebar / html.route-collections .sidebar; collections.ts :: renderPeople / renderRecentDays
- kind: explainer
- logged: v1.14.10 · 2026-07-26

The separate Panel opacity/blur tokens apply only under html.route-collections (router toggles it); the base sidebar uses the plain --glass-bg/--glass-blur everywhere else, per the user's scoping. Strip caps removed (people slice(0,12), recent-days break at 10); safe only bc the scheduler drains strips through the bounded pipeline · restoring caps is never the fix for load pressure, the scheduler is.

## Round 44 · heartbeat, watchdog & preload HUD (v1.14.11)

### src/ui/components/grid.ts · heartbeat + watchdog + HUD
- refers-to: grid.ts :: heartbeat interval / startLoad watchdog / updateHud / setPreloadHud; settings.ts :: App tab hudCheck; main.ts :: boot restore
- kind: rationale
- logged: v1.14.11 · 2026-07-26

Three guarantees added after the fifth field report. Heartbeat: a module-level 300ms interval schedules every lane's sweep & every 7th beat marks lanes dirty (offset re-measure), so the runway fills w/o ANY event hook · do not remove it as "redundant", it is the self-healing floor. Watchdog: startLoad settles exactly once via load, error, or a 12s timeout; w/o it one swallowed event permanently wedges inFlight at MAX_FLIGHT & the whole scheduler dies silently. HUD: sweepLane computes the true loaded runway (distance to the first UNLOADED pending tile above & below the viewport) & updateHud renders pend/q/fly/ahead/behind/avg-load into .preload-hud (fixed, pointer-events none); toggled by setPreloadHud, persisted under pref key preloadHud, restored at boot in main.ts. The HUD line is the debugging contract: read it before touching this system again.

## Round 45 · border removal + decode-before-reveal (v1.14.12)

### src/styles/app.css + grid.ts + main.ts · perimeter clip removed, decode gate, ready signal
- refers-to: app.css :: html.vibrancy / #app border-radius / .sidebar radius; grid.ts :: readyAfterDecode; main.ts :: ready post
- kind: warning-context
- logged: v1.14.12 · 2026-07-26

The html clip-path (round 39) is deleted: a full-perimeter inset mask antialiases along all four edges & can render as a hairline border around the app under a transparent window. Bottom rounding now lives on #app (border-radius + its existing overflow hidden) & .sidebar carries its own bottom-left radius bc fixed elements escape ancestor clips. Do not reintroduce a root clip-path for corners. readyAfterDecode gates the .ready fade behind img.decode() (both load paths), so tiles appear already-painted; keep it ahead of any future fade tweaks. main.ts posts { ready: true } after a double rAF · the shell holds the window invisible until then, so moving or removing that signal reintroduces the launch flash (6s shell failsafe notwithstanding).

## Round 47 · 260-item window, shimmer, top bar glass, presets (v1.14.14)

### src/ui/components/grid.ts · PRELOAD_ITEMS window
- refers-to: grid.ts :: PRELOAD_ITEMS / lookaheadPx(root)
- kind: rationale
- logged: v1.14.14 · 2026-07-26

Lookahead is 130 ITEMS each direction (user-specified 260 window), converted to px per sweep from the root's live column count (floor(width / (zoom + 12))). lookaheadPx takes the root; the one sentinel built before attach falls back to window width harmlessly & is rebuilt w/ the real root a frame later. Change PRELOAD_ITEMS, not the math, to retune.

### src/styles/app.css · shimmer skeleton + topbar tokens; settings.ts presets & top sliders; theme.ts prefs.top
- refers-to: app.css :: damp-shimmer / .topbar tokens / .preset-*; settings.ts :: Top bar section / Saved presets; theme.ts :: prefs.top / --glass-bg-top / --glass-blur-top
- kind: explainer
- logged: v1.14.14 · 2026-07-26

Shimmer rides :has(img:not(.ready)) so it needs no JS & stops exactly at the decode-gated reveal; keep it on the container (the img is opacity 0 while loading, so a background on the img itself would never show). prefs.top defaults (16/22) equal the app glass so the feature ships invisible until touched; tokens fall back to the app glass vars. Presets store [{ name, prefs }] under prefstore key themePresets; Apply deep-copies into the live prefs, commits, pushes window state & closes the modal (slider elements are built once per open, so a fresh open is the honest way to reflect every restored value). Same-name save overwrites by design.

## Round 48 · blank-page elimination (v1.14.15)

### src/styles/app.css + src/ui/components/grid.ts · translateZ scope, seam skeleton, visible shimmer
- refers-to: app.css :: .view transform scope / .thumb-wait / .grid-skeleton; grid.ts :: markWaiting / syncSkeleton / pagerBeat
- kind: warning-context
- logged: v1.14.15 · 2026-07-26

Never re-promote the main scroller to its own composited layer (transform/will-change on .content > .view): WebKit rasterizes big composited layers async & fast scrolling shows literal blank page until the compositor catches up · the round-42 translateZ(0) did exactly that & lives only under html.route-collections now. The seam skeleton (96 .skel-tile cells, display toggled by syncSkeleton from page.loaded/next/loading) must stay AFTER gridWrap & BEFORE sentinel so unfetched territory always shows animated tiles; the pager fires at 2x the preload window from scroll + a 400ms interval (cleared in offs). Shimmer is driven by the JS thumb-wait class (markWaiting on load start, removed in readyAfterDecode) w/ :has as fallback · keep the layered background (sweep over var(--tile-bg)) or the animation becomes invisible on the dark theme again.

## Round 49 · compositor-only shimmer (v1.14.16)

### src/styles/app.css + grid.ts · shimmer via transform, pager via content bottom
- refers-to: app.css :: damp-shimmer ::after overlay; grid.ts :: skeleton 30 cells / hookPager contentBottom
- kind: warning-context
- logged: v1.14.16 · 2026-07-26

HARD RULE, sourced (web.dev "Why are some animations slow?" / "Stick to Compositor-Only Properties", corroborated by Motion Magazine): loading/skeleton animations in this app may only animate transform or opacity. background-position/background/box-shadow/filter sweeps are paint-property animations · at grid scale they saturate the main thread, slow the load pipeline & stall themselves invisible (the round-48 regression). The shimmer is an ::after overlay translated -100 to 100 percent; hosts need position relative + overflow hidden (the shared rule provides both). Pager distance uses gridWrap.offsetTop + offsetHeight, never root.scrollHeight, so seam-skeleton size stays decoupled from prefetch timing.

## Round 50 · render containment (v1.14.17)

### src/styles/app.css · content-visibility on day sections, :has removed
- refers-to: app.css :: .view-pad section containment / .thumb-wait shimmer block
- kind: warning-context
- logged: v1.14.17 · 2026-07-26

Day sections carry content-visibility: auto + contain-intrinsic-size: auto 640px (web.dev/MDN sourced; the auto keyword self-corrects to real heights after first render). Offscreen sections render, paint & composite NOTHING · this is the app's scroll-performance foundation; removing it re-creates the sluggish scroll. Keep sticky elements (sel-bar) OUTSIDE sections (containment breaks sticky inside). The shimmer is class-driven only (.thumb-wait via markWaiting, .skel-tile); :has selectors were removed as redundant & must not return on grid-scale elements.

## Round 51 · resident 1300-window (v1.14.18)

### src/ui/components/grid.ts + app.css · slideWindow / topSpacer / containment removal
- refers-to: grid.ts :: WINDOW_MAX / ADVANCE / slideWindow / dropRange / ensureDayFront / topSpacer; app.css :: .grid-top-spacer
- kind: warning-context
- logged: v1.14.18 · 2026-07-26

CORRECTION on round 50: content-visibility discards & re-rasterizes returning sections, which IS a visible flash on scroll-back · never reintroduce it (or any per-section render discarding) on this grid; the bounded resident window is the scroll-cost mechanism instead. Invariants to preserve: rendered range is [winStart, appendCursor), residency <= WINDOW_MAX (1300), advance drops ADVANCE (1000) from the front & the spacer grows by the MEASURED removed height (px-for-px, so scrollTop needs no compensation); retreat prepends in REVERSE index order (correct final order), shrinks the spacer by measured added height & compensates scrollTop only w/ the positive remainder; tail trim keeps residency bounded after retreat. Lanes deliberately queue EVERY resident pending thumb (nearest-first) · re-adding a distance cutoff breaks the "all 1300 load" contract.

### grid.ts · decode gate removed (v1.14.19)
- refers-to: grid.ts :: readyAfterDecode
- kind: warning-context
- logged: v1.14.19 · 2026-07-26

Never gate image visibility on img.decode() in this grid: WebKit starves decode promises during scrolling & at resident-window scale (~1300 pending) loaded thumbs stay invisible behind the shimmer · the v1.14.18 "no loading while scrolling" field failure. Reveal on load; decoding="async" (attribute) is the only decode control permitted here.

## Round 53 · rollback to the endorsed baseline (v1.14.20)

### src/ui/components/grid.ts + app.css · v1.14.13 grid restored + two scalpels
- refers-to: grid.ts (restored wholesale) :: markWaiting / revealLoaded; app.css :: .thumb-wait block only
- kind: warning-context
- logged: v1.14.20 · 2026-07-27

The user proved w/ screenshots that rounds 47-52's grid layers regressed the app (fast scroll -> viewport inside an empty spacer). grid.ts is the v1.14.13 file from THEIR zip plus exactly: (1) markWaiting/revealLoaded (thumb-wait shimmer, compositor ::after CSS kept), (2) img.decode() gate removed (reveal on load). Treat v1.14.13's pipeline as the protected baseline: do NOT reintroduce DOM windows, skeleton seams, spacers, content-visibility, or reveal gates here w/o the user explicitly reopening the shelved specs & a plan tested against fast-scroll dynamics.

### trash.ts + hidden.ts · vault pages gate before render (v1.14.26)
- refers-to: trash.ts :: mountTrashPage gate / vaultGate fast path; hidden.ts :: vaultOk gate; api.ts :: hasVaultToken
- kind: warning-context
- logged: v1.14.26 · 2026-07-27

Vault pages must NEVER render cached items before this visit's gate resolves: the field bug was render()-then-fetch-then-prompt, showing the previous session's contents behind Touch ID. Invariants: cache discarded at mount, Locked card until vaultGate passes, token + cache cleared in teardown (every entry re-locks), & vaultGate's hasVaultToken fast path exists so in-visit actions do not double-prompt · do not remove it, & do not persist the vault token beyond a visit.

### public/formDAM-icon.svg + src-tauri/icons · the mark in the family colours (v1.27.1)
- refers-to: public/formDAM-icon.svg, public/formDAM-icon.png; src-tauri/icons/icon.png, src-tauri/icons/source/icon.icns; assets/icon_src/gen.py, parts.py, render.mjs
- kind: rationale
- logged: v1.27.1 · 2026-10-20

The mark keeps the shapes of the user's refined icon (the rounded play plate, the M, the dot, the sheen, glint and dot light) and now sits on the family's square tile like the other Form icons, filling about 84 percent of it (86 percent at 64 px and below): the dark gradient squircle with its pink-to-violet bloom, rim and drop shadow, the play plate raised on it as a near-black triangle with its own shadow and a fine top-lit edge, and the M and dot in the family paint (blue, violet, pink, amber) along the original gradient axis. The blurred halo that outlined the M is gone, at the user's request, so its edges stay crisp. The macOS source/icon.icns uses the 824 px tile inside a 1024 canvas with a 100 px margin (the build restores that file over tauri's flattened one); icon.png and the web PNG are full bleed with transparent corners. assets/icon_src/ regenerates every file: `python3 gen.py <mac|full> <full|simple> out.svg`, then `node render.mjs out.svg out.png <size>` (Playwright). The menu bar trayTemplate files are unchanged.

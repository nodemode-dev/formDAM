# src-tauri HASHOUT_LOG · formDAM
current: v1.27.2 · 2026-10-22

### ../setup/build_macos_app · @tauri-apps/cli 2.12.3 through npx, PyInstaller 6.22.3
- refers-to: build_macos_app the prerequisites block and its npx --version line, pip install pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.10, the npx icon line, the two npx build lines
- kind: rationale + replaced code
- logged: v1.28.8 · 2026-11-11

Replaced: cargo tauri --version >/dev/null 2>&1 || { say "Installing tauri-cli"; cargo install tauri-cli --version '^2' --locked; } in the prerequisites, cargo tauri icon, cargo tauri build (twice) and an unpinned pyinstaller. The cargo line took whatever 2.x crates.io had on the day the runner's cargo bin cache was empty (2.12.4 is the newest on 2026-11-11) and compiled it from source, and after that kept whichever version the cache held, so two runs of the same commit could bundle w/ different CLIs. macOS now runs the CLI the way build_linux_app and build_windows_app.bat do, npx --yes @tauri-apps/cli@2.12.3, the same pin (tauri-bundler 2.10.3, the version the symlink and bundle-failure handling above was read against); npm is already a prerequisite and nothing is compiled for it. The icon and build lines still run from the repo root, as the cargo form did (Linux runs its build from src-tauri); the CLI looks for src-tauri/tauri.conf.json under the current folder first. npx needs the npm registry where cargo-tauri was a local binary, so the prerequisites resolve the CLI once w/ --version and stop there w/ an npm message when it cannot be had: a registry failure at the build line would otherwise read as a Rust failure and clear the release cache. PyInstaller is pinned to 6.22.3 and pyinstaller-hooks-contrib to 2026.10, the pair the 1.28.6 macOS run froze the engine w/ (the hooks decide what is collected) and the PyInstaller whose link layout the 1.28.7 change was read against; Windows stays on its own pin, 6.16.0.

### ../setup/package_dmg + ../build_app + ../setup/apply_icon · the app is FormDAM.app everywhere
- refers-to: package_dmg default APP path, the staged app name, the Finder item name in the AppleScript, the header usage lines; build_app the four "$dest/FormDAM.app" lines of the install step; apply_icon default APP and its header
- kind: rationale + replaced code
- logged: v1.28.8 · 2026-11-11

Replaced: formDAM.app in each of those places. productName became FormDAM in 1.28.6 (tauri.conf.json, the window title, the app menu), and build_app and build_macos_app followed for the path tauri writes, but the packager still staged the app into the disk image as formDAM.app, build_app still installed it into Applications under that name, and the packager's default still pointed at a bundle tauri no longer writes. On a case-insensitive volume that only showed as the wrong capital in Finder; on a case-sensitive one setup/package_dmg run by itself stopped at "app not found". apply_icon's default follows the name the app now has once installed, and build_app's install step removes a copy under either name first, so a case-sensitive volume is not left w/ both. The volume name, the DMG file name (formDAM_v<version>.dmg, which build_app reads) and the launcher keep formDAM.

### ../setup/build_macos_app · a failed bundle step is not retried as a Rust failure
- refers-to: build_macos_app STAMP, rust_compiled, bundle_failed, the two "if rust_compiled; then bundle_failed; fi" lines around cargo tauri build
- kind: rationale
- logged: v1.28.7 · 2026-11-11

cargo tauri build compiles, bundles, signs and notarizes in one command and exits 1 for any of them. The script read every exit 1 as a Rust failure: in the 1.28.6 run the notarization refusal was followed by "Rust build failed", cargo clean --release (3.1 GiB), a second four-minute compile, a second notarization upload w/ the same refusal, then "Rust build failed twice" and the rustup update hint. A stamp file is written before the build; when the command fails and either release/formdam-desktop or release/bundle/macos/FormDAM.app is newer than the stamp, Rust compiled (tauri removes and recreates the .app only after a successful compile, before it signs), so the script says the bundle step failed and stops w/o cleaning or rebuilding. find -prune keeps the check to the two paths themselves. When neither is newer the old path runs unchanged: clean once, retry, toolchain report. The same check follows the retry.

### ../setup/build_macos_app · the engine tree carries no symlink into tauri's resource copy
- refers-to: build_macos_app after ENGINE: the find over links outside *.framework (cp -L -p, rm, mv) before the signing branch; after the signing branch the find that removes links inside *.framework, and the --selfcheck run on the placed tree
- kind: rationale
- logged: v1.28.7 · 2026-11-11

The first formcompiler run to reach notarization (1.28.6, macOS arm64, PyInstaller 6.22.3, Python 3.12 framework build) was refused w/ "The signature of the binary is invalid" for exactly two files: formdam-backend/_internal/Python and formdam-backend/_internal/Python.framework/Python. PyInstaller writes both as symlinks: _internal/Python -> Python.framework/Versions/3.12/Python, and inside the framework Python -> Versions/Current/Python, Resources -> Versions/Current/Resources, Versions/Current -> 3.12. The signing loop walks find -type f, so it signed the one real file, Versions/3.12/Python, and codesign signs a framework version's main executable as a bundle: the signature is bound to Versions/3.12/Resources/Info.plist and Versions/3.12/_CodeSignature. tauri copies a folder resource one file at a time: a link to a file ships as a second regular copy of its target, a link to a folder is dropped, a broken link stops the bundle. So the app carried two loose copies of a bundle-signed binary w/ no bundle around them, which is what notarization refused, while Versions/3.12/Python passed in the same run. Now each file link outside a framework becomes a real file before signing, so _internal/Python (the path the PyInstaller bootloader opens, and the @rpath/Python every extension refers to) is signed as a plain Mach-O at its own path like the other libraries. The links inside the framework are removed after signing, so Versions/3.12 is signed in the layout that already passed and the loose Python.framework/Python is no longer shipped; nothing loads through those three links. Then the placed engine runs --selfcheck, since the earlier selfcheck runs on backend/dist before any of this: a tree that cannot start now stops the build before the Rust compile. Folder links and broken links outside a framework are left as tauri always treated them. Not chosen: bundle.macOS.files keeps links but needs a macOS-only resource map; deleting Python.framework whole would save a few MB but ships a layout PyInstaller never produced.

### ../setup/build_linux_app + ../setup/build_windows_app.bat · @tauri-apps/cli pinned to 2.12.3
- refers-to: build_linux_app and build_windows_app.bat, the npx icon and build lines
- kind: rationale + replaced code
- logged: v1.28.3 · 2026-10-30

Replaced: npx --yes @tauri-apps/cli@2, which takes whatever 2.x npm has that day. frontend/package.json and its lock carry no @tauri-apps/cli, so both scripts pin 2.12.3, a CLI that bundles against the tauri 2.11 crates in Cargo.lock. The macOS script still installs tauri-cli ^2 through cargo when cargo-tauri is missing.

### ../setup/build_windows_app.bat · PyInstaller --add-data w/ the Windows separator, PyInstaller pinned
- refers-to: build_windows_app.bat the four --add-data pairs, pip install pyinstaller==6.16.0
- kind: rationale + replaced code
- logged: v1.28.3 · 2026-10-30

Replaced: --add-data "../frontend/dist:frontend_dist", "models:models", "app/data:app/data", "../frontend/package.json:." and an unpinned pyinstaller. ';' is the separator PyInstaller has always accepted on Windows (the colon form is only accepted from 6.x, and a drive-letter path makes it ambiguous), and the paths use backslashes like the rest of the script. Neither requirements file pins PyInstaller and the macOS and Linux scripts install it unpinned, so Windows takes a current 6.x, 6.16.0, and no longer moves to a new major by itself.

### macOS signing under formcompiler · Entitlements.plist, ../setup/build_macos_app engine signing, ../setup/package_dmg keeps tauri's signature
- refers-to: Entitlements.plist com.apple.security.cs.disable-library-validation and com.apple.security.cs.allow-unsigned-executable-memory; build_macos_app ENGINE, ENTITLEMENTS, IDENTITY from APPLE_SIGNING_IDENTITY before the keychain lookup, the Mach-O signing loop over the engine tree; package_dmg ENTITLEMENTS, IDENTITY, SIGNED, REPAIRED and the three signing branches, the closing release hint
- kind: rationale + replaced code
- logged: v1.28.3 · 2026-10-30

Replaced: package_dmg ran codesign --force --deep --options runtime -s "$IDENTITY" over the whole app whenever a Developer ID was in the keychain, and codesign --force --deep -s - otherwise. formcompiler imports the Developer ID before the build and tauri signs the app w/ hardened runtime, Entitlements.plist and a timestamp, then notarizes it; the --deep re-sign dropped the entitlements and the timestamp, so the app lost the photos-library entitlement and failed notarization. package_dmg now keeps a signature that passes codesign --verify --deep --strict, re-signs only when the icon repair changed the bundle (Developer ID w/ --options runtime --timestamp --entitlements, no --deep: the engine lives in Resources, so it is sealed as a resource and keeps its own signature), and signs ad hoc only when the app is unsigned and no identity exists. The icon repair should stay a no-op: build_macos_app copies icons/source/icon.icns into icons/icon.icns before tauri builds. The engine was signed ad hoc once at its top binary; notarization inspects every Mach-O in the bundle, so w/ an identity each Mach-O file in the PyInstaller tree is signed w/ it, hardened runtime, a timestamp and Entitlements.plist, the top binary last. A frozen Python under the hardened runtime loads its own unsigned-by-Apple extension modules and ctypes code, hence the two cs entitlements. The identity comes from APPLE_SIGNING_IDENTITY first (formcompiler's Build env), then the keychain; "-" counts as none.

### tauri.conf.json version from ../frontend/package.json · Cargo.toml and Cargo.lock 1.27.0
- refers-to: tauri.conf.json version; Cargo.toml package version; Cargo.lock formdam-desktop version
- kind: rationale + replaced code
- logged: zip v1.27.0 · 2026-10-20

Replaced: "version": "1.13.9" in tauri.conf.json. Tauri reads the version from the package.json path instead, so the bundle, the About panel, the .deb and the DMG name carry the build version w/o a second copy. Cargo cannot read another file, so the crate version is still a literal; it only names the crate, and a release bump sets it beside package.json.

### device unlock on Windows and Linux · bio_available, bio_evaluate, kc_entry/kc_present/kc_read/kc_write per OS, the engine as a .exe w/o a console, the polkit action
- refers-to: Cargo.toml cfg(windows) windows 0.61 (Foundation, Security_Credentials_UI, Win32_Foundation, Win32_System_WinRT), windows-future 0.2, keyring windows-native; cfg(linux) keyring async-secret-service + async-io + crypto-rust; main.rs KC_LEGACY now macOS-only, POLKIT_ACTION, POLKIT_POLICY, Windows UserConsentVerifier CheckAvailabilityAsync and IUserConsentVerifierInterop RequestVerificationForWindowAsync on the main window's HWND, Linux pkcheck --process pid,start,uid --allow-user-interaction, backend_command EXE_SUFFIX and CREATE_NO_WINDOW; linux/ai.nodemode.formdam.policy; tauri.conf.json bundle.linux.deb.files, bundle.windows.webviewInstallMode, icons/icon.ico
- kind: rationale
- logged: zip v1.26.0 · 2026-10-20

The engine's BIOUNLOCK and KCSTORE control lines are unchanged; only the shell's answer differs per OS. macOS keeps Touch ID (LAContext, biometrics only) and the Keychain via security-framework, untouched. Windows uses Windows Hello through UserConsentVerifier: the Win32 interop form is used because the plain RequestVerificationAsync opens its prompt behind a desktop app's window; Hello accepts face, fingerprint or the Hello PIN, which is the system's own rule. The passkey goes to Windows Credential Manager through keyring. Linux has no single biometric API, so the shell asks polkit to authenticate the user for the ai.nodemode.formdam.unlock action (auth_self, not kept, so every unlock asks): the desktop's polkit agent prompts, and through PAM that is the fingerprint reader when fprintd is enrolled, otherwise the account password. The .deb installs the action file; without it, or without pkcheck, the shell reports unlock as unavailable and the passkey modal stays the only way in. The passkey goes to the Secret Service (GNOME Keyring, KWallet) through keyring's pure-Rust zbus backend, so no libdbus is linked. The engine runs w/o a console window on Windows (CREATE_NO_WINDOW keeps its stdout pipe, which --windowed would not), and the shell finds formdam-backend.exe there.

### formDAM brand pass · productName, crate, engine binary, menus, control-line tag · and ../build_macos_app, ../build_linux_app, ../package_dmg, ../apply_icon
- refers-to: tauri.conf.json productName formDAM, resources binaries/formdam-backend; Cargo.toml and Cargo.lock formdam-desktop (lock entry moved to its sorted place after form_urlencoded so --locked accepts it); capabilities description; main.rs tray-open and tray-quit labels, BIOUNLOCK reason, backend_command formdam-backend and FORMDAM_PORT/FORMDAM_SHELL_KEY, about name, app submenu, window title, spawn and start errors, FORMDAM-CTRL prefix; build scripts pyinstaller --name formdam-backend and the engine tree paths, formDAM.app, the optional formDAM.icon and CFBundleIconName; package_dmg formDAM.app, /Volumes/formDAM, formDAM_v<version>.dmg
- kind: rationale
- logged: zip v1.25.0 · 2026-10-20

The bundle is formDAM.app, its menus, About panel, tray and dialogs say formDAM, and the DMG is formDAM_v<version>.dmg. The engine binary and the crate move to formdam-backend and formdam-desktop so build output names match. The bundle identifier ai.nodemode.dam and the Keychain service ai.nodemode.dam.vault stay: changing either would hide the existing WebKit storage and the stored vault passkey from the new build.

### src/main.rs window URL carries the launch key · and ../DAM_boot, ../DAM_boot.bat do the same for the browser build
- refers-to: main.rs navigate to http://127.0.0.1:{port}/#dam-key={shell_key}; DAM_boot DAM_SHELL_KEY from /dev/urandom, UI_OPEN; DAM_boot.bat key from the venv's python secrets, UI_OPEN
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

The audit showed browser fetch headers can be forged, so the window now proves itself with the shell key: the fragment never reaches a server, the page trades it for an HttpOnly cookie and drops it from the address. The boot scripts make their own key, pass it to the engine and open the browser with it, and print the address for connecting another browser.

### src/main.rs shell_key + ../build_macos_app models and app/data · the shell proves itself to the engine; Look Up data ships
- refers-to: main.rs SHELL_KEY, shell_key, engine_post and engine_get x-dam-shell header, backend_command DAM_SHELL_KEY env; build_macos_app EfficientSAM, YOLOX, BioCLIP and species fetch_model lines, species prepare step after the venv, --add-data app/data:app/data, --collect-all pyzipper and Cryptodome, --hidden-import app.familyserver
- kind: rationale
- logged: zip v1.24.0 · 2026-10-10

With automation access off by default the engine refuses callers that are neither the window nor a token holder, and the shell's own calls (menu-bar import, Keychain unlock results, glass state) are neither. The shell makes 64 hex characters from /dev/urandom once per launch (a RandomState-seeded fallback if that fails), hands them to the engine it spawns as DAM_SHELL_KEY, and sends them as x-dam-shell on every call; a program that did not start the engine never sees the value. Checked by compiling the functions standalone with rustc, since this container has no WebKit for cargo check. The build script fetches the new Clean Up and Look Up models with the same sha256 check, converts the species embeddings once inside the build venv (numpy is only there), and bundles app/data, which the packaged engine never had: offline place names were missing from the Mac app before this.

### ../build_macos_app + ../package_dmg + ../apply_icon · rename DAMp to DAM, part 3
- refers-to: build_macos_app header + Icon Composer hint; package_dmg icon hint + signing & notarizing examples (keychain profile name dam); apply_icon header, default /Applications/DAM.app, repo-root hint, closing hint
- kind: rationale
- logged: zip v1.18.2 · 2026-09-18

Text & defaults only; apply_icon now finds an installed DAM.app w/o arguments. No Rust changed this round.

### src/main.rs · rename DAMp to DAM, part 2: engine contracts
- refers-to: engine_post + engine_get header; backend_command DAM_PORT; control-line filter DAM-CTRL
- kind: rationale
- logged: zip v1.18.1 · 2026-09-18

All three renamed w/ their engine counterparts in the same round: a mismatch would silently break Touch ID, the tray & window control, so they move together or not at all. KC_LEGACY stays for the Keychain migration. Rust compile untested here (Mac check).

### tauri.conf.json + Cargo.toml + src/main.rs + ../build_macos_app + ../package_dmg · rename DAMp to DAM, part 1
- refers-to: productName, identifier ai.nodemode.dam, resources dam-backend; crate dam-desktop (Cargo.lock root renamed by cargo metadata, pins kept); main.rs tray labels + dam-tray id, KC_SERVICE/KC_ACCOUNT/KC_LEGACY, kc_present, kc_read, Touch ID reason, backend_command dam-backend, About + app menu + window title, dam-menu dispatch, engine error texts; build_macos_app engine name, placement, plist string, DAM.icon, DAM.app path; package_dmg defaults, staging name, volume & DMG names
- kind: rationale
- logged: zip v1.18.0 · 2026-09-18

A new identifier gives the app new WebKit storage & new TCC grants (the removable-volume prompt returns once); prefs live in the engine, so nothing user-facing is lost. The Keychain entry moves lazily: kc_present reports either the new or the legacy item, & the first kc_read that misses the new service reads the legacy one, writes it under ai.nodemode.dam.vault & deletes the old item. Because the ad-hoc signature changed, macOS may ask once to allow DAM to read the old item; denying it falls back to the passkey prompt. The engine resource name changes in three places at once (build placement, tauri resources, backend_command) so the bundle can never ship a mismatched path. Rust compile untested here (Mac check).

### Cargo.toml + Cargo.lock + ../build_macos_app · E0463 "can't find crate for zerofrom_derive"
- refers-to: [profile.release.build-override]; Cargo.lock (new, committed); build_macos_app app-bundle step (CARGO_TARGET_DIR, rustflags/wrapper neutralizing, --locked, clean retry, diagnostics) & DMG step output dir
- kind: rationale
- logged: zip v1.17.0 · 2026-09-18

No lockfile existed, so each build resolved the newest crates; the failing Mac build pulled zerofrom-derive 0.1.8 & yoke-derive 0.8.3 (published 2026-09-15) on syn 3.0.6 (2026-09-16). zerofrom was the first crate in the build to load any proc macro. The same set compiles on Linux w/ Rust 1.98.1 & this profile, so the cause is Mac-environment specific & could not be reproduced. Layered response: the lockfile pins the derive chain back (zerofrom-derive 0.1.7, yoke-derive 0.8.2, synstructure 0.13.2, serde_with 3.14.0, displaydoc 0.2.5) & builds use --locked; build-override stops `strip` on proc macros & build scripts (cargo was passing -C strip=symbols to them; they never ship); the target dir moves to src-tauri/target.nosync because the repo lives on ~/Desktop, which iCloud may sync mid-build; inherited RUSTFLAGS & rustc wrappers are neutralized for this build only; a failure triggers one clean + retry, then prints rustc/cargo/config details. syn 3 still enters via serde_derive, thiserror-impl & futures-macro; pinning those too is the next move if the Mac still reports E0463.

## Org-navi-map

```
src-tauri/
├── tauri.conf.json          schema 2, productName DAMp, sidecar bundle
├── Cargo.toml               damp-desktop, shell + dialog plugins, lto
├── build.rs                 stock tauri_build hook
├── capabilities/
│   └── default.json         core + dialog + scoped sidecar execute
├── icons/
│   └── icon.png             1024 RGBA canonical mark (user-provided, verbatim)
└── src/
    └── main.rs              sidecar spawn, port handshake, window, kill-on-exit
```

## Table of contents

- [tauri.conf.json](#tauriconfjson)
- [src/main.rs](#srcmainrs)
- [capabilities/default.json](#capabilitiesdefaultjson)

## tauri.conf.json

### tauri.conf.json · windows empty + csp null
- refers-to: tauri.conf.json :: app.windows / app.security.csp
- kind: rationale
- logged: v0.2.0 · 2026-07-25

Shell + engine shape (deduplakit-proven): no declarative window bc the window can only open after the engine reports its OS-assigned port, so main.rs builds it. csp null is acceptable here bc the page is served from loopback by our own engine & receives zero Tauri APIs; a real CSP becomes mandatory the moment remote content loads. Identifier ai.nodemode.damp is immutable once shipped (names the app-data dir & bundle id).

### tauri.conf.json · externalBin w/o triple
- refers-to: tauri.conf.json :: bundle.externalBin
- kind: explainer
- logged: v0.2.0 · 2026-07-25

`binaries/damp-backend` is listed w/o a target-triple suffix; the bundler resolves `binaries/damp-backend-<host-triple>` at build time. build_macos_app computes the triple from `rustc -Vv` & places the frozen engine accordingly.

## src/main.rs

### src/main.rs · transparency mode removed
- refers-to: deleted transparent(true)+effects from the builder, strip_view_opacity, force_transparency, reassert_transparency, material_config, set_window_material, WINMAT, the diag statics & the glass POST
- kind: correction
- logged: zip v1.14.5 · 2026-07-26

"I can see the border around the full app w/ the hard corners" identified what the user had been calling macOS transparency: not the checkbox, the transparent WINDOW MODE. A transparent window w/ no effect view gets no rounded clip from the system, so the web view painted to the frame edges (square corners) & the window's own transparent margin read as a border. The entire mode is deleted, not disabled: builder flags, view-tree stripping, re-assert schedules, material switching, control kind, counters, imports · so no dead-code warnings remain. What survives is what the user confirmed working: NSWindow opacity as Fade amount, plus the CGS radius as Fade blur. Rule extracted: a visual artifact the user describes precisely (corners, borders) localises the bug faster than any theory · treat those words as coordinates.

### src/main.rs · KVC, not respondsToSelector
- refers-to: setValue:forKey:"drawsBackground" on the web view; KVC_BG diag field
- kind: correction
- logged: zip v1.14.0 · 2026-07-26

The shipped diagnostic returned draws_bg_sel=0 from the user's machine: WKWebView has no setDrawsBackground: method on this WebKit, so guarding that call w/ respondsToSelector skipped it every time · while window_opaque=0 & webviews=1 proved everything else was already right. The property lives as the private _drawsBackground ivar & KVC reaches it (wry does the same), so setValue:forKey: is now called unconditionally on any WKWebView found, after set_effects. Rule extracted: respondsToSelector tests for a METHOD, so it is the wrong guard for a KVC-backed private property · check the mechanism you are actually using. Second rule, earned expensively: ship the measurement early; one line from the user's machine resolved what eight rounds of inference could not.

### src/main.rs · the fix was being undone in the same function
- refers-to: set_window_material order (effects then force_transparency); reassert_transparency; blur-handler re-assert; hud_config removed
- kind: correction (defeated rounds 25-31)
- logged: zip v1.13.999 · 2026-07-26

set_window_material cleared the web view's backdrop & THEN called set_effects, which rebuilds the native view tree; WebKit re-creates its opaque backdrop on that rebuild. Since the page asserts its window mode at every boot, the final act of every launch was to re-opaque the web view · so every transparency mechanism I shipped for six rounds was correct-then-immediately-reverted, which is exactly why the symptom never moved. Inverted the order, added a 120/250/500/1000ms re-assert for asynchronous commits, & re-assert after the CGS blur call as well. The user's own screenshot supplied the decisive evidence: desktop content visible in the sliver between window frame & web view proved the WINDOW was transparent all along. Rules extracted: sequence matters as much as content when native state is involved · always assert derived state AFTER the call that rebuilds the thing it derives from; & a "border" report can be the shape of the bug rather than a decoration.

### src/main.rs · no material, & measure instead of guess
- refers-to: set_effects(None) under vibrancy; STRIPPED/WEBVIEWS/DREW_BG/UNDERPAGE counters; POST /internal/shell/glass
- kind: correction
- logged: zip v1.13.998 · 2026-07-26

The reported border frame identified the effect view as a visible artifact: HudWindow draws an inset edge, & since the page above it was opaque the material only showed at the rim · which also confirmed the window itself composites w/ the desktop. Under vibrancy the effect view is now absent entirely (Terminal's configuration). More importantly this round adds MEASUREMENT: the walker counts layers cleared & web views found, records whether each private selector existed, re-reads isOpaque after setting it, & POSTs the result to the engine for display in Settings. Rule extracted: after two failed remote diagnoses, stop reasoning & ship instrumentation · a single measured line from the user's machine is worth more than any amount of inference.

### src/main.rs · the whole view tree, & the fade restored
- refers-to: strip_view_opacity (recursive, selector-guarded); scheduled re-assert after navigate; WINALPHA re-exposed as Whole-window fade
- kind: correction
- logged: zip v1.13.997 · 2026-07-26

Two lessons, both mine. First: targeting the WKWebView alone was too narrow · wry nests it in wrapper NSViews & any opaque layer in that chain hides the desktop regardless of what the web view is told, so the shell now walks contentView downward clearing layer backgrounds & opacity, w/ the web view's backdrop knobs (setDrawsBackground, _setDrawsBackground, underPageBackgroundColor) applied by capability rather than assumption. Re-asserted on a schedule after navigate bc the backdrop is re-established asynchronously on page commit. Second, & more important as process: the user reported SEVEN times that v1.13.991's NSWindow opacity worked, & I kept replacing it w/ theories instead of keeping it available. It is restored as an explicit Whole-window fade control (labeled as fading all content) so a working capability is never removed again while a replacement is unproven. Rule extracted: when a user reports that a specific build worked, preserve that mechanism as a shipped option until its replacement is confirmed on their machine.

### src/main.rs · navigation was eating the transparency
- refers-to: force_transparency (post-build, post-navigate, per window-mode assert); drawsBackground + underPageBackgroundColor + setOpaque
- kind: correction (root cause of rounds 20-28)
- logged: zip v1.13.996 · 2026-07-26

The whole saga had ONE cause & it was upstream of every CSS & material theory: tauri configures webview transparency at window CREATION, & this app creates the window on splash.html then navigate()s to the engine's loopback URL. Post-navigation the WKWebView draws its own opaque backdrop, so (a) page rgba paint composited onto solid, (b) the NSVisualEffect material behind it was unreachable, & (c) removing the effect view revealed square opaque corners · the webview's backdrop at the frame edges. NSWindow alpha "worked" only bc it fades the entire window irrespective of opacity. force_transparency re-asserts setOpaque(false) + clear window background + drawsBackground=false + underPageBackgroundColor=clear (macOS 12+ paints that BEHIND the page & re-opaques silently), at build, after navigate, & on every page-side window-mode assert so any later reload is covered. Implemented w/ raw class!/msg_send!/sel! so no typed-API signature can break the build & every call sits in unsafe (no unused-unsafe warnings). Terminal's decoded recipe (black 0.486 + blur 0.261, no material) is now a one-click preset. Rules extracted: verify the NATIVE surface is actually transparent before attributing translucency failures to CSS or materials; & any window property set at creation must be re-asserted after navigation.

### src/main.rs · never set_effects(None)
- refers-to: hud_config; set_window_material swapping instead of removing
- kind: correction
- logged: zip v1.13.995 · 2026-07-26

The user's "square corners" was the tell: tauri's macOS effect view carries the clear webview background & the rounded-corner clip, so set_effects(None) un-does transparency itself. Removed-code: the None branch. The material is a MODE w/ two values: standard (vibrancy off) or HudWindow (vibrancy on · the thinnest system blur, letting the desktop through while keeping corners & clear plumbing). Rule: on macOS the effect view is infrastructure, not decoration; swap materials, never remove the view.

### src/main.rs · WINMAT: the material becomes a mode
- refers-to: set_window_material; WINMAT ctrl kind; blur handler purified (radius only)
- kind: correction
- logged: zip v1.13.994 · 2026-07-26

The .992 handover (material off while radius>0) had the right instinct scoped wrong: the material must follow the TRANSLUCENCY MODE, not the blur value, or radius 0 slams a dark sheet back over the user's carefully tinted glass. WINMAT now switches the material as its own control (page decides: off under vibrancy, on otherwise), & WINBLUR is pure radius. Removed-code: the radius-conditional set_effects pair inside the blur handler.

### src/main.rs · material yields to CGS blur
- refers-to: set_window_blur removing set_effects while radius>0, restoring material_config at 0
- kind: rationale
- logged: zip v1.13.992 · 2026-07-26

The CGS background-blur radius from last round almost certainly did nothing bc the NSVisualEffect material was composited in FRONT of it, so the blurred desktop never reached the eye. Blur now does a handover: radius>0 removes the material (set_effects None) leaving CGS as the sole glass; radius==0 restores the Active UnderWindowBackground+Sidebar material. If the desktop still will not blur w/ the material gone, the suspect narrows to the OS declining CGS blur for this window class · the next concrete lever. Rule: two glass systems in the same window fight; pick one at a time.

### package_dmg · sign coherence & the auto-open .DS_Store bug
- refers-to: sign-after-xattr order; ad-hoc vs Developer ID verify; fancy_dmg leaves the window OPEN
- kind: correction
- logged: zip v1.13.991 · 2026-07-26

Two defects the user's log exposed. Signing: the byte-identical fast path signed nothing yet still ran xattr -cr, so the seal no longer matched the bytes, & the verify used --deep --strict which ad-hoc seals always fail (that flag is for authority chains) · so it warned on a fine signature. Fixed by always signing AFTER the strip & choosing the verify that matches the signature type. Auto-open: the arrange script CLOSED the window, persisting a closed state into the volume .DS_Store, so the blessed DMG opened to nothing; leaving it open + update without registering applications + sync before detach persists the open state. Volume name now comes from the live mount (stale "DAMp 1" can't misfire). Rules: never strip xattrs after signing; match the codesign verification to the signature class; & a DMG's window state is whatever Finder last SAVED, so never close it before detach.

### src/main.rs · window alpha & compositor blur
- refers-to: set_window_alpha (objc2-app-kit NSWindow), set_window_blur (SkyLight CGSSetWindowBackgroundBlurRadius via libloading), WINALPHA/WINBLUR ctrl kinds
- kind: rationale
- logged: zip v1.13.99 · 2026-07-26

NSWindow alpha is the only true whole-window fade & lives one msg-send away once ns_window() is cast (objc2-app-kit, NSWindow+NSResponder features per the crate's gating). Blur strength has no public knob, so the decades-old SkyLight symbol is resolved at RUNTIME (never linked): both symbols must resolve or the feature no-ops silently, the Library is kept alive in a OnceLock, & LICENSES.md carries the private-API disclosure incl the App Store prohibition. Both handlers hop to the main thread; values clamp engine-side AND shell-side. Mac checks: objc2-app-kit compile, symbol resolution on macOS 26, & whether CGS blur composes w/ the NSVisualEffect material or wants it removed (set_effects(None) is the follow-up lever if they fight).

### icon forensics + signature order + the modern-icon gate
- refers-to: in-container icns pixel audit; build identity export & verify-only post step; package_dmg diff-gated modify; DAMp.icon -> actool pipeline
- kind: correction + rationale
- logged: zip v1.13.98 · 2026-07-26

The dispute ended w/ pixels: every embedded size has corner alpha 0 (~54% fully transparent), & the uploaded file is byte-identical to the shipped one, so the backing is macOS 26's renderer, which stylizes legacy icns in Get Info too · the earlier Get Info verification claim was wrong & is corrected in every script's output. Removed-code: the post-build cp+adhoc-resign pair (it clobbered tauri's signature; modify-after-sign was the defect behind "showing up unsigned"). Order now: correct icns BEFORE build -> tauri signs (w/ an auto-detected Developer ID when present) -> post steps verify, & only a diff triggers repair+resign. The Tahoe exit is pre-wired: an Icon Composer DAMp.icon in icons/ auto-compiles (actool) into Assets.car + CFBundleIconName at build time. Rules: never modify a bundle after its signature unless prepared to own the resign; & claims about renderer behavior require a pixel-level test, not documentation memory.

### apply_icon + build reunification
- refers-to: apply_icon (new); build_macos_app delegating to package_dmg
- kind: explainer
- logged: zip v1.13.97 · 2026-07-26

The build ends in a DMG again bc that is the flow the user actually lives in; separation survives as delegation (the build calls the packager, so there is exactly one DMG implementation). apply_icon covers the third moment in an icon's life: after install, stamping /Applications/DAMp.app in place (icon filename from the app's own plist, byte-identity verified, ad-hoc re-sign, Finder+Dock nudge, deep iconservices flush printed for the stubborn cache). Three scripts, three moments: build, release, installed.

### package_dmg · release packaging as its own step
- refers-to: package_dmg (new, repo root); build_macos_app DMG stage removed-code
- kind: rationale
- logged: v0.13.95 · 2026-07-26

Build & release are different acts w/ different cadences: you build many times, you package a release once, possibly days later, possibly from an older app. The DMG stage therefore left the build script entirely (removed-code: the fancy_dmg block & staging lines, now living evolved in package_dmg). Two behaviors matter in the packager beyond v0.13.8's race hardening: bless --openfolder restores the auto-open-on-mount that tauri's DMGs had & ours silently lacked (the reported "isn't launching" was a mount w/ no window), & the guarded osascript arranges a real release window (Finder automation may prompt for permission once; denial degrades to auto-open only). Version & icon filename come from the app's OWN Info.plist so the artifact never lies about what it wraps. The macOS 26 legacy-icon backing remains system-drawn; the packager teaches the Get Info verification & the Icon Composer exit instead of pretending.

### src/main.rs · effect state pinned
- refers-to: WindowEffectsConfig state Some(Active), effects [UnderWindowBackground, Sidebar]
- kind: explainer
- logged: v0.13.9 · 2026-07-26

Every other link in the vibrancy chain re-verified (conf macOSPrivateApi true, cargo feature, transparent(true), page translucency, canvas clearRect): the effect STATE was the one under-specified piece, left at follow-focus. Pinned Active w/ a material fallback so the compositor has no discretion. If black persists on macOS 26, the next move is an isolation build (translucent solid page) to split OS-material behavior from app css · recorded so the debugging ladder is explicit.

### build_macos_app · the hdiutil race
- refers-to: fancy_dmg(); .metadata_never_index; device-node detach; direct-UDZO fallback; stale-volume pre-detach
- kind: correction
- logged: v0.13.8 · 2026-07-26

The v0.13.7 DMG stage lost a race on real hardware: convert ran while the RW image was still attached (Spotlight/FSEvents hold new volumes; string-based detach can miss), yielding EAGAIN + a write error reported on the mount. Removed-code: the four-line attach/SetFile/detach/convert sequence. The rewrite treats every transition as contested: index suppression, quiet attach flags, detach by device node w/ retries & force, sync + settles, convert retries, & a guaranteed direct-create fallback. Rule extracted: any script step that mounts a volume must assume the OS also has hands on it & must degrade to a path w/ no mount at all.

### build_macos_app · the icns is law
- refers-to: bundles-app-only + Resources overwrite + ad-hoc resign + hand-built DMG
- kind: rationale
- logged: v0.13.7 · 2026-07-26

Two icon launderers existed: cargo tauri icon regenerates icon.icns from the png (fixed in v0.13.1 by restoring after), & the DMG carried whatever the bundler last wrote. Now the app bundle is built alone, its Resources/icon.icns is overwritten w/ the user's file byte-for-byte, the bundle is ad-hoc re-signed (modifying a signed bundle invalidates the seal), & the DMG is hand-built from THAT app w/ the same icns as .VolumeIcon (SetFile custom-icon flag when available). The script prints the diff invitation so honoring is verifiable, & names the remaining actor honestly: macOS 26 draws a backing behind legacy-format icons in the Dock; only Icon Composer's .icon format removes it, which requires Xcode on the Mac.

### src/main.rs · the tray agent
- refers-to: set_tray/post_import/paths_to_strings; TRAYSET ctrl; close-to-hide; Cargo features tray-icon+image-png; icons/menubar template PNGs
- kind: rationale
- logged: v0.13.3 · 2026-07-26

The user's menubar SVG (white glyph) is rasterized to black+alpha template PNGs so macOS tints it natively. The tray is engine-governed: pref lives server-side, shell asks at startup & obeys TRAYSET control lines, so the page toggles it w/o any page IPC. Dialogs use the callback style (blocking pickers on the main runloop are a hang risk); selections post to /api/import as one multi-root job. While enabled, CloseRequested is prevented & the window hides, which is what makes import-while-closed true; Quit lives in the tray menu & kills the engine first. Compile is a Mac check: tray-icon feature, Image::from_bytes (image-png), & the dialog callback signatures are the risk points.

### src/main.rs · control channel replaces page IPC (research-driven)
- refers-to: handle_ctrl_line/bio_evaluate/kc_*/engine_post; Cargo feature pins; capabilities description
- kind: correction + rationale
- logged: v0.10.0 · 2026-07-26

Removed the page-facing command (& withGlobalTauri):

    #[tauri::command] fn biometric_auth(reason: String) -> Result<bool, String>  // page could never call it

Why it never worked: Tauri injects no IPC into remote-origin windows, & the loopback UI is remote-origin; the tauri-web-content doctrine both states this & forbids granting it. New lane: the stdout the shell already reads doubles as an engine->shell control line (DAMP-CTRL BIOUNLOCK/KCSTORE nonce); the shell answers over loopback HTTP w/ the x-damp-local header. LAContext per docs.rs 0.3.2 (per-attempt context, sendable reply block, context alive through evaluation, feature flags LAContext+block2 & NSString/NSError pinned bc every class is feature-gated). Keychain via security-framework: set_generic_password create-or-update means DAMp OWNS the item -> silent reads thereafter (the CLI-created items' ACL trusting /usr/bin/security was the prompting/"not storing" experience); ItemSearchOptions load_attributes is the no-prompt presence probe used in the startup hello. Trust boundary: page full-trust w/ zero remote code & zero IPC; secrets shell<->engine only.

### src/main.rs · v0.6.0 rewrite: onedir engine, splash handshake, native menu, one command
- refers-to: main.rs (whole file); tauri.conf.json bundle.resources + withGlobalTauri; capabilities/default.json; build_macos_app freeze block
- kind: rationale + removed-code
- logged: v0.6.0 · 2026-07-25

Removed the sidecar spawn (& w/ it tauri-plugin-shell + shell:allow-execute):

    .plugin(tauri_plugin_shell::init())
    // sidecar("damp-backend").env("DAMP_PORT", "0").spawn() via shell plugin

Reasons, in feedback order: (1) --onefile froze the engine into a self-extracting archive; cv2+numpy made every launch pay ~5s of extraction. --onedir ships the tree in Resources/damp-backend & std::process::Command spawns it directly: no extraction, no shell plugin, no shell permission. (2) The window now exists immediately at splash.html (bundled via frontendDist) & window.navigate() hands off when the port line arrives: perceived cold start = splash, not a dead dock icon. (3) Native menu per the menubar doctrine: first submenu is the app menu (About/Settings.../Services/Hide/Quit), predefined Edit items restore Cmd+C/V/X/A in the webview, Window is registered as the NSApp windows menu; Settings... reaches the page w/ window.eval dispatching a damp-menu CustomEvent, keeping IPC one-way. (4) biometric_auth is the single #[tauri::command] (LAContext, biometrics policy, block2 completion into an mpsc w/ a 120s timeout), exposed via withGlobalTauri; the capability file + LICENSES.md name it as the entire page-facing surface. Compile & prompt are Mac-only checks, listed in BUILD_NOTES.

### src/main.rs · port handshake
- refers-to: main.rs :: setup async task
- kind: rationale
- logged: v0.2.0 · 2026-07-25

Engine spawns w/ DAMP_PORT=0 (OS picks a free port); the shell reads BOTH stdout & stderr events bc uvicorn logs its bind line to stderr, regexes `http://127.0.0.1:(port)`, then opens the webview at that external loopback URL sized to 90 percent of the primary monitor (AIR_FALLBACK 1323x860 when no monitor info). On Terminated w/o a port: native dialog, kill child, exit 1, so a crashed engine never leaves a blank hung window.

### src/main.rs · kill on exit
- refers-to: main.rs :: kill_backend / RunEvent::Exit
- kind: warning-context
- logged: v0.2.0 · 2026-07-25

The CommandChild lives in managed state & is killed on RunEvent::Exit & on the failure path. Removing either kill leaves an orphaned damp-backend process after quit; hardware check is `pgrep -f damp-backend` returning nothing.

## src/main.rs (vibrancy)

### src/main.rs · UnderWindowBackground vibrancy
- refers-to: main.rs :: builder transparent/effects + tauri.conf.json macOSPrivateApi + Cargo macos-private-api
- kind: warning-context
- logged: v0.3.0 · 2026-07-25

macOS-only cfg block: transparent(true) + WindowEffectsConfig w/ Effect::UnderWindowBackground gives the real material behind the webview. The config flag & the cargo feature MUST stay paired (mismatch is a build error). The page stays opaque unless the user turns on Settings > Native window translucency (html.vibrancy backgrounds). Untested in this container; on-device checks: the material after `tauri build`, & the known field bug where transparency is lost in some bundled DMG installs · if hit, the opaque fallback is simply the toggle staying off.

## capabilities/default.json

### src/main.rs (vibrancy)

### src/main.rs · UnderWindowBackground vibrancy
- refers-to: main.rs :: builder transparent/effects + tauri.conf.json macOSPrivateApi + Cargo macos-private-api
- kind: warning-context
- logged: v0.3.0 · 2026-07-25

macOS-only cfg block: transparent(true) + WindowEffectsConfig w/ Effect::UnderWindowBackground gives the real material behind the webview. The config flag & the cargo feature MUST stay paired (mismatch is a build error). The page stays opaque unless the user turns on Settings > Native window translucency (html.vibrancy backgrounds). Untested in this container; on-device checks: the material after `tauri build`, & the known field bug where transparency is lost in some bundled DMG installs · if hit, the opaque fallback is simply the toggle staying off.

## capabilities/default.json · minimal surface
- refers-to: capabilities/default.json :: permissions
- kind: rationale
- logged: v0.2.0 · 2026-07-25

Exactly three grants, each mapped in LICENSES.md's capability ledger: core:default (window/event baseline), dialog:default (startup failure message), shell:allow-execute scoped to the one sidecar. Page content gets no IPC at all; the renderer attack surface is the loopback API, which backend/app/security.py hardens directly.

## src/main.rs (window fade v2)

### src/main.rs · clear_webview_backdrop, the background-only fade base
- refers-to: main.rs :: clear_webview_backdrop / WINCLEAR arm / builder .transparent(true) / post-navigate schedule
- kind: rationale
- logged: v1.14.6 · 2026-07-26

The round-34-proven mechanism, minimal form: window built transparent, NSWindow set non-opaque w/ clear background, WKWebView backdrop killed via KVC setValue:forKey:"drawsBackground"=false (the wry-native path; setDrawsBackground: no longer exists as a method, the round-33 finding) w/ a valueForKey read-back into DIAG_KVC, & underPageBackgroundColor cleared behind a respondsToSelector guard. setAlphaValue(1.0) in the same call purges any whole-window fade stored by v1.13.997-v1.14.5. Re-asserted at 50/250/700/1500/3000ms after navigate() bc WebKit re-establishes the opaque backdrop asynchronously on navigation (round-29 finding), & on every WINCLEAR from /system/window. No effect view, no material, no layer walking: those were the corner/border culprits & they stay deleted.

### src/main.rs · removed WINALPHA / set_window_alpha
- refers-to: main.rs :: handle_ctrl_line
- kind: removed-code
- logged: v1.14.6 · 2026-07-26

```rust
"WINALPHA" => {
    if let Ok(alpha) = nonce.parse::<f64>() {
        let _ = HANDLE.get().map(|h| {
            let h2 = h.clone();
            h.run_on_main_thread(move || set_window_alpha(&h2, alpha))
        });
    }
}
```
Plus set_window_alpha (NSWindow setAlphaValue clamp 0.3-1.0). Removed bc NSWindow alpha composites the finished window & can never be scoped to the background; it is the exact "fades everything" defect. Blur keeps using ns_window for windowNumber.

### src/main.rs · glass_diag line
- refers-to: main.rs :: glass_diag + the post-navigate diag post
- kind: explainer
- logged: v1.14.6 · 2026-07-26

win_opaque / webviews / kvc_bg / underpage posted to /api/internal/shell/glass after the re-assert schedule & surfaced in Settings, so any remaining opacity on-device is settled by evidence. Expected healthy line: win_opaque=0 webviews=1 kvc_bg=1 underpage=1.

### src/main.rs · builder mut removed
- refers-to: main.rs :: setup window builder
- kind: explainer
- logged: v1.14.7 · 2026-07-26

let mut builder was never reassigned (the option chain is inline); mut dropped to clear the unused_mut warning reported from the v1.14.6 Mac build.

### src/main.rs · hidden-until-painted reveal + invalidateShadow (v1.14.12)
- refers-to: main.rs :: builder .visible(false) / WINSHOW arm / failsafe thread / clear_webview_backdrop invalidateShadow
- kind: rationale
- logged: v1.14.12 · 2026-07-26

Window created invisible & revealed on WINSHOW (page posts ready after its first painted frame); the arm re-clears the backdrop, shows, focuses & marks SHOWN; a 6s thread shows regardless so a wedged page can never leave the app invisible. invalidateShadow now runs w/ every backdrop clear: on transparent windows macOS keeps a shadow/edge computed from stale content, which reads as a border ring around the whole app · do not remove the call, & keep clear-before-show ordering so first sight is fully composited.

### src/main.rs · reveal at splash paint (v1.14.17)
- refers-to: main.rs :: builder on_page_load / SHOWN / 2s failsafe
- kind: rationale
- logged: v1.14.17 · 2026-07-26

The window shows on the FIRST PageLoadEvent::Finished (the splash), guarded by SHOWN so the later app navigation no-ops. Hidden-until-app-painted (round 45) hid the whole engine cold start (~5-6s of nothing -> the reported 7s launch); revealing at splash paint keeps the anti-flash guarantee (splash paints its own opaque background) while restoring instant perceived launch & the splash animation. WINSHOW remains as polish (backdrop clear + focus + invalidateShadow). Do not move the reveal back behind engine readiness.

### src/main.rs · shadow pulse (v1.14.21)
- refers-to: main.rs :: 10s invalidateShadow loop in the navigate thread
- kind: rationale
- logged: v1.14.21 · 2026-07-27

Transparent-window shadows go stale whenever composited content changes, & the rim reads as a border around the whole app; one-shot invalidation (round 45) is insufficient across a session. The 10s pulse keeps the edge computed from current content · do not remove it as redundant w/ the clear-time invalidation.

### src/main.rs · hasShadow(false), the real border lever (v1.14.22)
- refers-to: main.rs :: clear_webview_backdrop setHasShadow
- kind: warning-context
- logged: v1.14.22 · 2026-07-27

Sourced (ghostty 9611 + Apple docs): on Tahoe the window's styled edge & its drop shadow are the same property, hasShadow · you cannot keep one w/o the other, & invalidateShadow only redraws the edge. setHasShadow(false) is the only supported cure for the border on a titled transparent window. Re-enabling shadow re-enables the border; never reintroduce invalidateShadow loops for this.

### src/main.rs + capabilities · overlay titlebar (v1.14.23)
- refers-to: main.rs :: title_bar_style Overlay / hidden_title; capabilities :: start-dragging; app.css :: all-corner radius / .drag-strip / sidebar padding
- kind: rationale
- logged: v1.14.23 · 2026-07-27

The native titlebar backing draws SQUARE on transparent Tahoe windows & cannot be clipped from the page · Overlay removes the material entirely & the page rounds all four corners (#app border-radius var(--win-radius)). The .drag-strip (data-tauri-drag-region, 30px) is the window's drag surface; removing it strands the window. Sidebar padding-top 44px exists for the floating traffic lights.

### src/main.rs · overlay reverted (v1.14.24)
- refers-to: main.rs :: builder (transparent + visible false only)
- kind: warning-context
- logged: v1.14.24 · 2026-07-27

Never use TitleBarStyle::Overlay or data-tauri-drag-region in this app: the page is served from the engine's loopback URL & has NO Tauri IPC, so drag regions cannot function & removing the native titlebar strands the window. The ghost corner is NOT titlebar material (disproven in the field); current prime suspect is the unshapeable square CGS blur region · resolve via the Fade blur -> 0 discriminator before touching chrome again.

### src/main.rs · shaped blur via effect view (v1.14.25)
- refers-to: main.rs :: set_window_blur (EffectsBuilder UnderWindowBackground / radius 12)
- kind: warning-context
- logged: v1.14.25 · 2026-07-27

CGS background blur is forever square (window bounds) & WAS the ghost corner · never reintroduce it. The shaped replacement is the effect view w/ UnderWindowBackground ONLY (HudWindow draws the round-31 border edge; other materials wash the look), state Active, radius matched to --win-radius, cleared w/ set_effects(None) at blur 0, & clear_webview_backdrop MUST run after every set_effects (round-32 ordering). If --win-radius changes in CSS, change the 12.0 here in the same commit.

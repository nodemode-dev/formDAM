# DAM license ledger

DAM itself is MIT (see LICENSE). Every dependency & binary that enters the tree is classified here before use, per dev-rules licensing policy. Runtime web deps are also tabled in README.md.

## Shipped inside the app bundle (desktop)

| Component | License | Notes |
| --- | --- | --- |
| tauri, tauri-build | MIT OR Apache-2.0 | shell framework |
| tauri-plugin-dialog | MIT OR Apache-2.0 | startup-failure dialog only |
| regex (crate) | MIT OR Apache-2.0 | port handshake parsing |
| objc2, objc2-foundation, objc2-local-authentication, block2 | MIT (Zlib OR Apache-2.0 OR MIT for the framework crate) | LAContext Touch ID prompt, shell-side (macOS only) |
| security-framework | MIT OR Apache-2.0 | native Keychain read/write of the vault passkey, shell-side (macOS only) |
| objc2-app-kit | MIT (Zlib OR Apache-2.0 OR MIT) | NSWindow alpha & window number for the full-window controls (macOS only) |
| libloading | ISC | runtime lookup of the compositor blur symbol (macOS only) |
| ureq, serde_json | MIT OR Apache-2.0 | loopback control-channel client (shell -> engine) |
| Python runtime (frozen) | PSF-2.0 | inside PyInstaller onefile |
| fastapi | MIT | engine |
| uvicorn | BSD-3-Clause | engine server |
| Pillow | MIT-CMU | image decode/thumbs |
| numpy | BSD-3-Clause | embeddings math |
| cryptography | Apache-2.0 OR BSD-3-Clause | vault encryption at rest (X25519, HKDF-SHA256, AES-256-GCM); the wheel bundles OpenSSL 3 (Apache-2.0). Dual license, both options permissive (same class as tauri's MIT OR Apache-2.0): flagged for owner review per policy |
| opencv-python-headless | Apache-2.0 | YuNet/SFace inference |
| pillow-heif | BSD-3-Clause (bindings) | bundles libheif (LGPL-3.0) & codecs as dynamic libs; acceptable under LGPL separability (dynamic link, replaceable); revisit before any store distribution |
| pyobjc-core, pyobjc-framework-Cocoa, pyobjc-framework-ImageCaptureCore, pyobjc-framework-Quartz | MIT | Python bridge to Apple's ImageCaptureCore (the Photos.app device-import framework) for iPhone/iPad import + ImageIO thumbnail encode for the device browse grid; macOS only |
| YuNet model | MIT | bundled via --add-data |
| SFace model | Apache-2.0 | bundled via --add-data |
| DAM icon artwork | user-provided | src-tauri/icons/icon.png, used verbatim |

## Build-time only (never distributed)

| Component | License | Notes |
| --- | --- | --- |
| PyInstaller | GPL-2.0 w/ Bootloader Exception | the exception expressly permits distributing frozen proprietary/MIT apps; PyInstaller itself is not shipped |
| vite, vitest, jsdom | MIT | frontend toolchain |
| typescript | Apache-2.0 | frontend toolchain |
| tauri-cli, Rust toolchain | MIT OR Apache-2.0 | compile only |

## External tier-1 binaries (user-supplied PATH, never bundled)

| Component | License | Decision |
| --- | --- | --- |
| ffmpeg / ffprobe | LGPL/GPL (build-dependent) | called as subprocess on PATH; never copied into the bundle, keeping the .app proprietary-safe & the binary user-replaceable. brew install ffmpeg |
| tesseract | Apache-2.0 | OCR for text search; same tier & reasoning as ffmpeg. brew install tesseract |
| pymobiledevice3 (<8) | GPL-3.0-or-later | REMOVED from the bundle at zip v1.15.0: it had been collected into the frozen engine since v0.11.0 w/o a ledger row, & GPL is banned in anything we distribute. The AFC code path remains as an optional dev fallback that only activates if the user pip-installs the package themselves (never bundled); the native ImageCaptureCore path replaces it |

## Capability ledger (src-tauri/capabilities/default.json)

| Permission | Feature that needs it |
| --- | --- |
| core:default | window + event baseline |
| dialog:default | engine startup-failure dialog |

The engine is spawned Rust-side from bundle resources (std Command), so no shell permission exists. The page receives ZERO Tauri APIs: remote-origin (loopback) content gets no IPC in Tauri by design, & this build does not grant any. Touch ID & Keychain run in the shell, triggered by DAM-CTRL lines the engine prints & answered over loopback HTTP w/ the local header; the passkey never enters the page.


Private-API note: the Window blur control uses CGSSetWindowBackgroundBlurRadius (SkyLight), a private macOS symbol resolved at runtime & a decades-old community staple for adjustable window blur. It is a graceful no-op if the symbol vanishes, & the app must not ship to the Mac App Store w/ it.

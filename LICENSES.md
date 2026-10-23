# formDAM license ledger

formDAM itself is MIT (see LICENSE). Every dependency & binary that enters the tree is classified here before use, per dev-rules licensing policy. Runtime web deps are also tabled in README.md.

## Adobe DNG patent licence

This product includes DNG technology under license by Adobe Systems Incorporated.

formDAM reads DNG files (RAW decoding through rawpy and LibRaw). Adobe's DNG Specification patent licence is worldwide and royalty-free for reading and writing files that comply with the DNG Specification, on condition that distributed products display the notice above prominently; it is shown in Settings > App > About formDAM, under Licences and notices. Adobe may revoke the licence from anyone who, with their affiliates, brings a patent action against Adobe over reading or writing DNG files. Source: the licence text Adobe ships with the DNG SDK (`PATENTS`).

## Trademarks

Adobe, Bridge, Lightroom and Photoshop are either registered trademarks or trademarks of Adobe in the United States and/or other countries. Apple and Photos are trademarks of Apple Inc. formDAM is not affiliated with or endorsed by Adobe or Apple.

## Shipped inside the app bundle (desktop)

| Component | License | Notes |
| --- | --- | --- |
| tauri, tauri-build | MIT OR Apache-2.0 | shell framework |
| tauri-plugin-dialog | MIT OR Apache-2.0 | startup-failure dialog only |
| regex (crate) | MIT OR Apache-2.0 | port handshake parsing |
| objc2, objc2-foundation, objc2-local-authentication, block2 | MIT (Zlib OR Apache-2.0 OR MIT for the framework crate) | LAContext Touch ID prompt, shell-side (macOS only) |
| security-framework | MIT OR Apache-2.0 | native Keychain read/write of the vault passkey, shell-side (macOS only) |
| windows, windows-future | MIT OR Apache-2.0 | Windows Hello prompt (UserConsentVerifier and its Win32 interop), shell-side (Windows only); already in the tree through Tauri |
| keyring | MIT OR Apache-2.0 | vault passkey in Windows Credential Manager (Windows) or the Secret Service (Linux), shell-side; its Linux backend pulls secret-service, zbus and the RustCrypto aes, cbc, hkdf, sha2 crates, all MIT, Apache-2.0 or BSD-2-Clause, audited 2026-10-20 |
| polkit (pkcheck) | system binary, LGPL-2.0+ | called as a subprocess for the Linux unlock prompt, never linked or bundled; the .deb ships only formDAM's own action file |
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
| exifread | BSD-3-Clause | EXIF, GPS & Apple maker-note read (metasvc) |
| rawpy | MIT | RAW decode; the wheel bundles LibRaw (LGPL-2.1 OR CDDL-1.0) as a dynamic lib, same separability reasoning as libheif |
| onnxruntime | MIT | runs the CLIP model for visual search, pets & content labels |
| CLIP ViT-B/32 LAION-2B (onnx-community export of laion/CLIP-ViT-B-32-laion2B-s34B-b79K, int8, revision de693d0) + vocab.json + merges.txt | MIT | fetched by the installers & build script, sha256-pinned, into backend/models; bundled via --add-data like the face models. The BPE tokenizer in services/cliptok.py is written for formDAM against the published vocab & merges |
| GeoNames cities5000, admin1CodesASCII, countryInfo | CC BY 4.0 | backend/app/data/places.json.gz, reduced to name, coordinates, country, admin1 & population; offline reverse geocoding & place search. Attribution: "Place data from GeoNames (geonames.org), CC BY 4.0", shown under the Places page and in README |
| Natural Earth admin-0 countries 1:50m | Public domain | backend/app/data/countries.json.gz, simplified outlines for the Places map & country fallback |
| FormLit (nodemode-ai) | Apache-2.0 | adapted, with a header line naming the source file in each: the rename token engine (services/renamesvc.py, from formlit rename.py), EXIF reading (services/exifmeta.py read_image, from formlit metadata.py read_exif) and XMP build, parse & JPEG embedding (services/xmpsvc.py, from formlit metadata.py & xmpembed.py; changed to formDAM's record shape, a dam: namespace for favorite & edits, GPS & people fields, and no Camera Raw develop mapping). NOTICE obligations satisfied by this row |
| pyobjc-core, pyobjc-framework-Cocoa, pyobjc-framework-ImageCaptureCore, pyobjc-framework-Quartz | MIT | Python bridge to Apple's ImageCaptureCore (the Photos.app device-import framework) for iPhone/iPad import + ImageIO thumbnail encode for the device browse grid; macOS only |
| YuNet model | MIT | bundled via --add-data |
| SFace model | Apache-2.0 | bundled via --add-data |
| pyzipper 0.4.0 | MIT | AES-256 (WinZip AE-2) zip writing and reading for encrypted share packages, services/packagesvc.py |
| pycryptodomex (pyzipper dependency) | BSD-2-Clause and public domain | AES and HMAC under pyzipper |
| LaMa inpainting (opencv/inpainting_lama, inpainting_lama_2025jan.onnx, revision aee6d22) | Apache-2.0 | Clean Up object removal in services/cleanup.py; fetched by the installers & build script, sha256-pinned, into backend/models; bundled via --add-data like the other models. Without it Clean Up falls back to OpenCV Telea |
| EfficientSAM-Ti (opencv/image_segmentation_efficientsam, image_segmentation_efficientsam_ti_2025april.onnx, revision 1e79198) | Apache-2.0 | Clean Up Select Object and distraction outlines in services/cleanmodels.py; sha256-pinned like LaMa |
| BioCLIP image encoder (imageomics/bioclip, MIT; int8 ONNX export Virien/naturdex-bioclip-onnx revision fa3c062, MIT, bioclip_image_int8.onnx) | MIT | Look Up species in services/species.py; sha256-pinned; checked here against the official open_clip weights (cosine 0.91 to 0.99, same top species). Cite: Stevens et al., BioCLIP: A Vision Foundation Model for the Tree of Life, CVPR 2024 |
| BioCLIP species text embeddings (imageomics/bioclip-demo space revision eeb91af, txt_emb_species.npy and .json, 384,490 taxa) | MIT | sha256-pinned download, converted at install to int8 (bioclip_species_int8.npy, about 197 MB) by services/species.py prepare; the fp32 source is deleted |
| Wikidata landmarks, artworks and dishes (backend/app/data/lookup_world.json.gz, built by setup/gen_lookup_data.py via the QLever Wikidata endpoint) | CC0-1.0 | Look Up names, coordinates and artist credits; no attribution required |
| YOLOX-s (opencv/object_detection_yolox, object_detection_yolox_2022nov.onnx, revision 78c368f) | Apache-2.0 | Clean Up distraction suggestions (COCO classes) in services/cleanmodels.py; sha256-pinned like LaMa |
| formDAM icon artwork | user-provided | src-tauri/icons/icon.png, used verbatim |

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

The engine is spawned Rust-side from bundle resources (std Command), so no shell permission exists. The page receives ZERO Tauri APIs: remote-origin (loopback) content gets no IPC in Tauri by design, & this build does not grant any. Touch ID & Keychain run in the shell, triggered by FORMDAM-CTRL lines the engine prints & answered over loopback HTTP w/ the local header; the passkey never enters the page.


Private-API note: the Window blur control uses CGSSetWindowBackgroundBlurRadius (SkyLight), a private macOS symbol resolved at runtime & a decades-old community staple for adjustable window blur. It is a graceful no-op if the symbol vanishes, & the app must not ship to the Mac App Store w/ it.

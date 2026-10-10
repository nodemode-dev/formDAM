# DAM

Open-source, local-first photo library and asset manager in the spirit of Photos.app and Adobe Bridge: a managed or referenced originals store w/ a SQLite catalog, RAW & HEIC, full EXIF, ratings, labels & hierarchical keywords, smart albums, an offline map, places & trips, CLIP visual search, pets & content collections, a non-destructive editor, XMP sidecars, export, print & contact sheets, memories & slideshows, albums & passkey-locked private albums, a 30-day Recently Deleted vault, people recognition across photos & video frames, & the deduplakit visual engine bundled in as the duplicate finder. Everything runs on your machine; the server only accepts loopback connections & no photo, coordinate or query leaves it.

## Quickstart

```
./DAM                  # the master: icon banner, install what is missing (idempotent), boot, opens http://127.0.0.1:5173
setup/DAM_oc_install   # install only: backend venv + pip deps + face & CLIP models (~190 MB, sha256-pinned) + frontend npm install
setup/DAM_boot         # boot only: backend (127.0.0.1:8000) & frontend dev server (127.0.0.1:5173); DAM_OPEN=0 skips the browser
setup/DAM_banner       # the DAM icon as an ASCII banner (NO_COLOR, DAM_BANNER=0 & DAM_BANNER_COLOR honored)
```

Open http://127.0.0.1:5173. The DAM mark lives in `frontend/public/` (source art, composed diamond app icon w/ neon glow, 512 PNG) & doubles as favicon + sidebar brand. Windows: `DAM.bat` does the same, with its steps in `setup\`.

Prefer a single process? Build the UI once (`cd frontend && npm run build`) & the backend serves it at http://127.0.0.1:8000 directly.

ffmpeg on PATH is needed for video thumbnails, video dedup & video face scanning; w/o it photos still work fully.

## Features

- **Import**: paste a folder/file path, browse a folder on disk, or drop files & folders anywhere (onto an album to file them there); files are copied, moved or added in place (referenced), SHA-256 fingerprinted, filed as an import batch, & exact duplicates are skipped at the door. XMP sidecars from Bridge or Lightroom come along (ratings, labels, keywords, IPTC).
- **Formats & metadata**: HEIC/HEIF, 23 camera RAW extensions via LibRaw, video via ffmpeg; EXIF, GPS, lens & exposure, Apple maker notes (Live Photo pairing, bursts, selfies, portraits), QuickTime tags.
- **Library grid**: day-grouped tiles w/ Years / Months / All Photos views, zoom slider, combinable quick filters (media types, rating, label, keyword), eleven sort orders, stacks, Cmd-click & Shift-click selection, infinite scroll via keyset cursors.
- **Viewer**: full-size photos & range-streamed video playback, info panel w/ camera data, location, keywords, people, subjects & recognised text, ratings & labels from the keyboard, download, delete.
- **Organize**: 0-5 stars, seven colour labels, reject, titles, captions & alt text, a hierarchical keyword manager w/ shortcuts, smart albums, album folders, stacks & bursts, pinned views, batch rename w/ tokens, Show in Finder & Edit With.
- **Search**: one search over every text field, dates & places, plus CLIP ("puppies in flowers"), suggestions, Advanced Find (Cmd-F) saved as smart albums.
- **Places**: offline reverse geocoding, an offline map w/ clustered thumbnails, city & country collections, trips, location & date editing singly or in batches.
- **Recognition**: subjects, pets (grouped per animal), content collections (documents, receipts, handwriting, illustrations, QR codes), groups of people.
- **Edit**: non-destructive adjustments (light, colour, B&W, curves, levels, definition, sharpen, noise, vignette), filters, crop & straighten, retouch, markup, copy & paste edits, revert, video trim; RAW develops through the same pipeline.
- **Output**: XMP sidecars, File Info (IPTC) w/ templates, export to JPEG, HEIC, PNG, TIFF or WebP w/ sizing, naming, subfolders & metadata options, print & PDF contact sheets, saved workflows.
- **Curation**: memories (generated or described) w/ generated music, slideshows, compare w/ linked zoom.
- **Libraries**: several libraries, repair, consolidate referenced files.
- **Albums**: create, rename, delete, add/remove via multi-select. Private albums require a passkey (scrypt-hashed) & their items disappear from every general view, incl. People & Duplicates.
- **Vault**: one vault passkey guards Recently Deleted & doubles as the fallback key for private albums w/o their own. Unlocks issue short-lived HMAC tokens; nothing is stored in the browser.
- **Recently Deleted**: trash is a database state, not a file move. Items auto-purge after 30 days (configurable), restore or delete forever any time. Duplicate resolutions land here too, so they are always reversible.
- **People**: YuNet face detection + SFace 128-d embeddings, incremental clustering by cosine similarity. Videos are sampled at the same timestamps the dedup engine uses, so people are found in footage too. Rename clusters as you go.
- **Duplicates**: the bundled deduplakit engine (dual-gradient dHash + confidence-masked DCT pHash + color grid) finds exact & visually-identical sets across photos & videos; resolving keeps the best copy & trashes the rest.
- **Utilities & Collections**: screenshots & screen recordings auto-detected, Recently Saved / Recently Viewed, counts everywhere, honest empty states for what is not built yet.

## macOS desktop app

```
setup/build_macos_app
```

Run on a Mac from the repo root: it fetches the face models, builds the UI, freezes the engine into a single `dam-backend` binary (PyInstaller, selfcheck-gated), generates the icon set from `src-tauri/icons/icon.png`, & produces `DAM.app` + a `.dmg` via Tauri in `src-tauri/target.nosync/release/bundle/`. The bundle is unsigned; first launch is right-click > Open (or clear quarantine w/ `xattr -dr com.apple.quarantine .../DAM.app`). The desktop app stores its library in `~/Library/Application Support/DAM/library` (an older `DAMp` folder is adopted automatically on first launch). ffmpeg stays a user-supplied PATH binary (`brew install ffmpeg`). Licensing decisions live in LICENSES.md.

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `DAM_LIBRARY` | `<repo>/library` | Library root (originals, cache, vault, `dam.db`) |
| `DAM_MODELS` | `backend/models` | Face & CLIP model directory |
| `DAM_CONFIG` | Application Support/DAM, %APPDATA%/DAM or ~/.config/dam | Where the list of known libraries is kept |
| `DAM_FACE_THRESHOLD` | `0.55` | Cosine threshold for person clustering (also adjustable in People) |
| `DAM_TRASH_DAYS` | `30` | Days before trash auto-purges |

The older `DAMP_*` spellings are still read when the `DAM_*` one is unset.

## Layout

```
backend/    FastAPI + SQLite; app/dedup is the vendored deduplakit engine core
frontend/   vanilla TS + Vite; dark themeable UI, inline currentColor SVG icons
library/    created on first run: originals/, cache/, vault/, dam.db
```

## Dependency licenses

| Dependency | License | Where it runs |
| --- | --- | --- |
| fastapi | MIT | backend |
| uvicorn | BSD-3-Clause | backend |
| Pillow | MIT-CMU | backend |
| numpy | BSD-3-Clause | backend |
| opencv-python-headless | Apache-2.0 | backend |
| pillow-heif | BSD-3-Clause (libheif LGPL, dynamic) | backend |
| exifread | BSD-3-Clause | backend |
| rawpy | MIT (LibRaw LGPL-2.1 OR CDDL-1.0, dynamic) | backend |
| onnxruntime | MIT | backend |
| YuNet model (opencv_zoo) | MIT | backend, downloaded at install |
| SFace model (opencv_zoo) | Apache-2.0 | backend, downloaded at install |
| CLIP ViT-B/32 LAION-2B, int8 ONNX | MIT | backend, downloaded at install |
| GeoNames cities5000 (reduced) | CC BY 4.0 | backend/app/data, place names |
| Natural Earth admin-0 | Public domain | backend/app/data, map outlines |

Place data from GeoNames (geonames.org), CC BY 4.0. Country outlines from Natural Earth. Parts of the rename, EXIF and XMP code are adapted from FormLit (Apache-2.0); see LICENSES.md.
| ffmpeg | LGPL/GPL | external PATH binary, called as a subprocess, never bundled |
| vite | MIT | frontend dev/build |
| typescript | Apache-2.0 | frontend dev/build |
| vitest | MIT | frontend tests |
| jsdom | MIT | frontend tests |

Face & CLIP models are fetched by the installer w/ SHA-256 verification bc they are too large to ship in the repo.

DAM itself is MIT licensed (see LICENSE).

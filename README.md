# formDAM

Open-source, local-first photo library and asset manager in the spirit of Photos.app and Adobe Bridge: a managed or referenced originals store w/ a SQLite catalog, RAW & HEIC, full EXIF, ratings, labels & hierarchical keywords, smart albums, an offline map, places & trips, CLIP visual search, pets & content collections, a non-destructive editor, XMP sidecars, export, print & contact sheets, memories & slideshows, albums & passkey-locked private albums, a 30-day Recently Deleted vault, people recognition across photos & video frames, & the deduplakit visual engine bundled in as the duplicate finder. Everything runs on your machine; the engine only accepts loopback connections & no photo, coordinate or query leaves it. Recognition (Look Up, Clean Up, people, search) runs on device w/ permissively licensed models. Sharing is an AES-256 encrypted zip you send yourself, by any means, w/ a password you pass on separately; there is no share server. Sync (through a folder you choose), the family Shared Library (local network only, between formDAM apps holding the same share key) & automation access for scripts, agents & MCP tools are all opt-in & off until you turn them on; even then private, hidden & vaulted items never leave.

## Quickstart

```
./formDAM                  # the master: icon banner, install what is missing (idempotent), boot, opens http://127.0.0.1:5173
./formDAM desktop build    # the desktop app: setup/build_macos_app on macOS, setup/build_linux_app (a .deb) elsewhere
setup/formDAM_oc_install   # install only: backend venv + pip deps + face, CLIP, Clean Up & Look Up models (~650 MB on disk, ~1.2 GB downloaded once, sha256-pinned) + frontend npm install
setup/formDAM_boot         # boot only: backend (127.0.0.1:8000) & frontend dev server (127.0.0.1:5173); FORMDAM_OPEN=0 skips the browser
setup/formDAM_banner       # the formDAM icon as an ASCII banner (NO_COLOR, FORMDAM_BANNER=0 & FORMDAM_BANNER_COLOR honored)
```

`./formDAM` opens the interface at http://127.0.0.1:5173 with a one-time launch key in the address, which connects that browser to the engine; to connect another browser, use the address the boot script prints. A window opened without it shows a "not connected" card, because the engine answers only windows its launcher opened. The formDAM mark lives in `frontend/public/` as `formDAM-icon.svg` & `formDAM-icon.png` (source art, composed diamond app icon w/ neon glow, 512 PNG) & doubles as favicon + sidebar brand. Windows: `formDAM.bat` does the same, with its steps in `setup\`.

Prefer a single process? Build the UI once (`cd frontend && npm run build`) & the backend serves it at http://127.0.0.1:8000 directly.

ffmpeg on PATH is needed for video thumbnails, video dedup & video face scanning; w/o it photos still work fully.

## Features

- **Import**: paste a folder/file path, browse a folder on disk, or drop files & folders anywhere (onto an album to file them there); files are copied, moved or added in place (referenced), SHA-256 fingerprinted, filed as an import batch, & exact duplicates are skipped at the door. XMP sidecars from Bridge or Lightroom come along (ratings, labels, keywords, IPTC).
- **Formats & metadata**: HEIC/HEIF, 23 camera RAW extensions via LibRaw, video via ffmpeg; EXIF, GPS, lens & exposure, Apple maker notes (Live Photo pairing, bursts, selfies, portraits), QuickTime tags.
- **Library grid**: day-grouped tiles w/ Years / Months / All Photos views, zoom slider, combinable quick filters (media types, rating, label, keyword), eleven sort orders, stacks, Cmd-click & Shift-click selection, infinite scroll via keyset cursors.
- **Viewer**: full-size photos & range-streamed video playback, info panel w/ camera data, location, keywords, people, subjects & recognised text, ratings & labels from the keyboard, download, delete.
- **Organize**: 0-5 stars, seven colour labels, reject, titles, captions & alt text, a hierarchical keyword manager w/ shortcuts, smart albums, album folders, stacks & bursts, pinned views, batch rename w/ tokens, Show in Finder & Edit With (a working copy opens in the other app & each save comes back as a revertible edit).
- **Search**: one search over every text field, dates & places, plus CLIP ("puppies in flowers"), suggestions, Advanced Find (Cmd-F) saved as smart albums.
- **Places**: offline reverse geocoding, an offline map w/ clustered thumbnails, city & country collections, trips, location & date editing singly or in batches.
- **Recognition**: subjects, pets (grouped per animal), content collections (documents, receipts, handwriting, illustrations, QR codes), groups of people, & Look Up in the info panel: about 384,000 species of animals, plants & fungi (BioCLIP, named to species, genus or family w/ the scientific name), dog & cat breeds, about 3,700 landmarks (any landmark in range of the photo's location competes, the best-known 1,500 otherwise), about 590 famous artworks w/ their artists, & about 1,200 foods & drinks. Media types include time-lapse, cinematic, spatial, animated & long exposure.
- **Edit**: non-destructive adjustments (light, colour, B&W, curves, levels, definition, sharpen, noise, vignette), filters, crop & straighten, Clean Up (brush, click Select Object or pick from suggested distractions to remove them w/ LaMa; brushing over a face pixelates it), markup, lens corrections, a Live Photo Long Exposure effect, copy & paste edits, revert, video trim; RAW files add a develop section (Kelvin white balance & tint, exposure, highlight recovery, demosaic, noise, fringe).
- **Sharing**: Share as Encrypted Package turns photos or an album into a WinZip AES-256 zip w/ a generated password (or your own of at least 16 characters; zip encryption is guessed quickly offline, so short passwords are refused); file names, metadata & edits are inside the encryption & members carry random names. Location (GPS & place names in EXIF, XMP & IPTC, in edits & Live Photo videos too) is stripped losslessly unless you include it. Opening a package never changes photos you already have; it only adds new ones & links the rest. Send the zip by Mail, Messages, AirDrop or anything else & pass the password on separately; the recipient drops it onto formDAM, enters the password & gets a new album or stack. Shared album packages carry notes both ways & merge back into the same album w/o duplicates. A static web gallery for any host is still available.
- **Sync & Shared Library**: both off by default. Sync keeps this library the same on your other computers through a folder they all see (iCloud Drive, Dropbox, Syncthing, a NAS). The family Shared Library works only on the local network between formDAM apps holding the same share key: peers find each other by an authenticated beacon & exchange signed, encrypted requests on their own port; an app w/ another key, or anything outside private network ranges, is refused. A Both / Personal / Shared switch sits in the filter menu.
- **Privacy**: automation access (scripts, agents, MCP tools) is off by default; Settings > Privacy turns it on & shows a token to give them. Only the app window & the desktop shell reach the engine otherwise: the launcher passes a per-launch key that the window trades for an HttpOnly session cookie, & the key is removed from the engine's environment so programs it starts never see it.
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

Run on a Mac from the repo root: it fetches the face models, builds the UI, freezes the engine into a single `formdam-backend` binary (PyInstaller, selfcheck-gated), generates the icon set from `src-tauri/icons/icon.png`, & produces `formDAM.app` + a `formDAM_v<version>.dmg` via Tauri in `src-tauri/target.nosync/release/bundle/`. The bundle is unsigned; first launch is right-click > Open (or clear quarantine w/ `xattr -dr com.apple.quarantine .../formDAM.app`). The desktop app stores its library in `~/Library/Application Support/DAM/library` (an older `DAMp` folder is adopted automatically on first launch); that data folder keeps its name so existing libraries open unchanged. Engine logs go to `~/Library/Logs/formDAM`. ffmpeg stays a user-supplied PATH binary (`brew install ffmpeg`). Licensing decisions live in LICENSES.md.

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `FORMDAM_LIBRARY` | `<repo>/library` | Library root (originals, cache, vault, `dam.db`) |
| `FORMDAM_MODELS` | `backend/models` | Model directory (face, CLIP, Clean Up, Look Up) |
| `FORMDAM_AUTOMATION` | unset | `1` lets any local caller use the API (the test suite & scripted runs need it); otherwise turn on Automation Access in Settings > Privacy |
| `FORMDAM_SHELL_KEY` | set by the launcher | Per-launch key the desktop shell or `setup/formDAM_boot` passes to the engine; without it the engine makes one & prints the address that connects a window |
| `FORMDAM_CONFIG` | Application Support/DAM, %APPDATA%/DAM or ~/.config/dam | Where the list of known libraries is kept |
| `FORMDAM_FACE_THRESHOLD` | `0.55` | Cosine threshold for person clustering (also adjustable in People) |
| `FORMDAM_TRASH_DAYS` | `30` | Days before trash auto-purges |

The older `DAM_*` and `DAMP_*` spellings are still read, in that order, when the `FORMDAM_*` one is unset (not for `FORMDAM_AUTOMATION`, which only answers to its own name).

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
| LaMa inpainting (opencv/inpainting_lama ONNX) | Apache-2.0 | backend, downloaded at install, Clean Up |
| EfficientSAM-Ti & YOLOX-s (opencv_zoo ONNX) | Apache-2.0 | backend, downloaded at install, Clean Up select & suggestions |
| BioCLIP image encoder (int8 ONNX) & species embeddings | MIT | backend, downloaded at install, Look Up species |
| Wikidata landmarks, artworks & dishes | CC0 | backend/app/data, Look Up |
| pyzipper & pycryptodomex | MIT & BSD-2-Clause / public domain | backend, encrypted packages |
| ffmpeg | LGPL/GPL | external PATH binary, called as a subprocess, never bundled |
| vite | MIT | frontend dev/build |
| typescript | Apache-2.0 | frontend dev/build |
| vitest | MIT | frontend tests |
| jsdom | MIT | frontend tests |

Place data from GeoNames (geonames.org), CC BY 4.0. Country outlines from Natural Earth. Parts of the rename, EXIF and XMP code are adapted from FormLit (Apache-2.0); see LICENSES.md.

Models are fetched by the installer w/ SHA-256 verification bc they are too large to ship in the repo: face (YuNet, SFace, under 40 MB), CLIP (146 MB), Clean Up (LaMa 89 MB, EfficientSAM 47 MB, YOLOX 35 MB) & Look Up (BioCLIP 84 MB plus species embeddings, downloaded once at 850 MB & stored as 192 MB int8). Look Up's landmark, art & food lists are rebuilt w/ `setup/gen_lookup_data.py`.

formDAM itself is MIT licensed (see LICENSE).

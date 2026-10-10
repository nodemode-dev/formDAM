import io
import os
from typing import Optional, Tuple, Union

from PIL import Image, ImageOps

from .. import mediacodecs
from . import rawdev

RAW_EXTS = {
    "dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "rwl", "pef",
    "srw", "x3f", "3fr", "iiq", "erf", "kdc", "dcr", "mos", "mrw",
}
WEB_NATIVE = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "avif"}
FLIP = {3: Image.Transpose.ROTATE_180, 5: Image.Transpose.ROTATE_90, 6: Image.Transpose.ROTATE_270}

Source = Union[str, bytes]


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lstrip(".").lower()


def is_raw(name: str) -> bool:
    return ext_of(name) in RAW_EXTS


def web_native(name: str) -> bool:
    return ext_of(name) in WEB_NATIVE


def rawpy_available() -> bool:
    try:
        import rawpy  # noqa: F401
    except Exception:
        return False
    return True


def _raw_handle(src: Source):
    import rawpy

    return rawpy.imread(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)


def _raw_preview(raw) -> Optional[Image.Image]:
    import rawpy

    try:
        thumb = raw.extract_thumb()
    except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError, Exception):
        return None
    if thumb.format == rawpy.ThumbFormat.JPEG:
        img = Image.open(io.BytesIO(thumb.data))
        img.load()
    elif thumb.format == rawpy.ThumbFormat.BITMAP:
        img = Image.fromarray(thumb.data)
    else:
        return None
    flip = getattr(raw.sizes, "flip", 0)
    if flip in FLIP and (img.width > img.height) == (raw.sizes.width > raw.sizes.height):
        img = img.transpose(FLIP[flip])
    return img.convert("RGB")


def _raw_full(raw, max_long: Optional[int], opts: Optional[dict] = None) -> Image.Image:
    half = bool(max_long) and max_long * 2 <= min(raw.sizes.width, raw.sizes.height)
    if not opts:
        return Image.fromarray(raw.postprocess(use_camera_wb=True, output_bps=8, half_size=half))
    return Image.fromarray(rawdev.develop(raw, opts, half))


def raw_size(src: Source) -> Optional[Tuple[int, int]]:
    if not rawpy_available():
        return None
    try:
        with _raw_handle(src) as raw:
            w, h = raw.sizes.width, raw.sizes.height
            if getattr(raw.sizes, "flip", 0) in (5, 6):
                w, h = h, w
            return w, h
    except Exception:
        return None


def open_image(src: Source, name: str, max_long: Optional[int] = None, develop: bool = False,
               raw_opts: Optional[dict] = None) -> Optional[Image.Image]:
    mediacodecs.register()
    if is_raw(name):
        if not rawpy_available():
            return None
        try:
            with _raw_handle(src) as raw:
                img = None
                if max_long and max_long <= 1600 and not develop and not raw_opts:
                    img = _raw_preview(raw)
                    if img is not None and max(img.size) < max_long * 0.75:
                        img = None
                if img is None:
                    img = _raw_full(raw, max_long, raw_opts)
        except Exception:
            return None
    else:
        try:
            img = Image.open(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
            if max_long:
                img.draft("RGB", (max_long * 2, max_long * 2))
            img = ImageOps.exif_transpose(img)
        except Exception:
            return None
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    if max_long and max(img.size) > max_long:
        img.thumbnail((max_long, max_long), Image.Resampling.LANCZOS)
    return img


def image_size(path: str, name: str) -> Optional[Tuple[int, int]]:
    if is_raw(name):
        return raw_size(path)
    mediacodecs.register()
    try:
        with Image.open(path) as img:
            return ImageOps.exif_transpose(img).size
    except Exception:
        return None

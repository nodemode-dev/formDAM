import os
import re

IMAGE_EXTS = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff",
    "heic": "image/heic", "heif": "image/heif", "avif": "image/avif",
}
VIDEO_EXTS = {
    "mp4": "video/mp4", "mov": "video/quicktime", "m4v": "video/x-m4v", "webm": "video/webm",
    "mkv": "video/x-matroska", "avi": "video/x-msvideo", "mts": "video/mp2t", "3gp": "video/3gpp",
}

SCREENSHOT_NAME = re.compile(r"screen[\s_-]?shot|screenshot", re.IGNORECASE)
SCREENREC_NAME = re.compile(r"screen[\s_-]?record|screenrecording|rpreplay", re.IGNORECASE)


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lstrip(".").lower()


def media_kind(name: str):
    ext = ext_of(name)
    if ext in IMAGE_EXTS:
        return "image", IMAGE_EXTS[ext]
    if ext in VIDEO_EXTS:
        return "video", VIDEO_EXTS[ext]
    return None, None


SCREEN_DIMS = {
    (2560, 1600), (2880, 1800), (3024, 1964), (3456, 2234), (3072, 1920), (3840, 2160),
    (2560, 1440), (1920, 1080), (1470, 956), (1512, 982), (1728, 1117), (1800, 1169),
    (1179, 2556), (1290, 2796), (1170, 2532), (1284, 2778), (1125, 2436), (1242, 2688),
    (828, 1792), (1080, 2340), (1206, 2622), (1320, 2868), (2048, 2732), (1668, 2388),
    (1640, 2360), (1620, 2160), (2064, 2752), (2420, 1668),
}


def looks_screenshot(name: str, mime: str, has_exif_time: bool, width=None, height=None) -> bool:
    if SCREENSHOT_NAME.search(name):
        return True
    if mime != "image/png" or has_exif_time:
        return False
    if not width or not height:
        return False
    return (width, height) in SCREEN_DIMS or (height, width) in SCREEN_DIMS


def looks_screen_recording(name: str, kind: str) -> bool:
    return kind == "video" and bool(SCREENREC_NAME.search(name))

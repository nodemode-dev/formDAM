import re
import struct
from typing import Optional

GPS_TAG = 0x8825
RETIRED_TAG = 0x8826
TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
XMP_GPS = re.compile(rb'(exif:GPS[A-Za-z]+)(="[^"]*"|>[^<]*<)')
XMP_LOC = re.compile(rb'(photoshop:(?:City|State|Country)|Iptc4xmpCore:(?:Location|CountryCode)|Iptc4xmpExt:(?:LocationShown|LocationCreated'
                     rb'|City|Sublocation|ProvinceState|ProvinceCode|CountryName|CountryCode|WorldRegion|LocationName|LocationId'
                     rb'|GPSLatitude|GPSLongitude|GPSAltitude))(="[^"]*"|>[^<]*<)')
IIM_PLACE = {26, 27, 90, 92, 95, 100, 101}


def _iim(buf: bytearray) -> None:
    if bytes(buf[:2]) != b"\xff\xd8":
        return
    pos = 2
    while pos + 4 <= len(buf) and buf[pos] == 0xFF:
        marker = buf[pos + 1]
        if marker in (0xD9, 0xDA):
            return
        length = struct.unpack_from(">H", buf, pos + 2)[0]
        end = min(len(buf), pos + 2 + length)
        if marker == 0xED:
            i = pos + 4
            while i + 5 <= end:
                if buf[i] == 0x1C and buf[i + 1] == 2:
                    size = struct.unpack_from(">H", buf, i + 3)[0]
                    if size & 0x8000:
                        i += 1
                        continue
                    if buf[i + 2] in IIM_PLACE and i + 5 + size <= end:
                        buf[i + 5:i + 5 + size] = b" " * size
                    i += 5 + size
                else:
                    i += 1
        pos += 2 + length


def _png_crcs(buf: bytearray) -> None:
    import zlib

    pos = 8
    while pos + 12 <= len(buf):
        length = struct.unpack_from(">I", buf, pos)[0]
        if pos + 12 + length > len(buf):
            return
        struct.pack_into(">I", buf, pos + 8 + length, zlib.crc32(bytes(buf[pos + 4:pos + 8 + length])) & 0xFFFFFFFF)
        if bytes(buf[pos + 4:pos + 8]) == b"IEND":
            return
        pos += 12 + length


def _blank_tiff(buf: bytearray, start: int) -> bool:
    if start + 8 > len(buf):
        return False
    order = bytes(buf[start:start + 2])
    if order == b"II":
        e = "<"
    elif order == b"MM":
        e = ">"
    else:
        return False
    if struct.unpack_from(e + "H", buf, start + 2)[0] != 42:
        return False
    found = False
    seen = set()
    ifd = struct.unpack_from(e + "I", buf, start + 4)[0]
    while ifd and ifd not in seen and start + ifd + 2 <= len(buf):
        seen.add(ifd)
        base = start + ifd
        count = struct.unpack_from(e + "H", buf, base)[0]
        for i in range(count):
            entry = base + 2 + i * 12
            if entry + 12 > len(buf):
                break
            tag = struct.unpack_from(e + "H", buf, entry)[0]
            if tag == GPS_TAG:
                gps = struct.unpack_from(e + "I", buf, entry + 8)[0]
                _wipe_ifd(buf, start, gps, e)
                struct.pack_into(e + "H", buf, entry, RETIRED_TAG)
                struct.pack_into(e + "I", buf, entry + 8, 0)
                found = True
        nxt = base + 2 + count * 12
        ifd = struct.unpack_from(e + "I", buf, nxt)[0] if nxt + 4 <= len(buf) else 0
    return found


def _wipe_ifd(buf: bytearray, start: int, ifd: int, e: str) -> None:
    base = start + ifd
    if base + 2 > len(buf):
        return
    count = struct.unpack_from(e + "H", buf, base)[0]
    for i in range(count):
        entry = base + 2 + i * 12
        if entry + 12 > len(buf):
            return
        typ = struct.unpack_from(e + "H", buf, entry + 2)[0]
        n = struct.unpack_from(e + "I", buf, entry + 4)[0]
        size = TYPE_SIZES.get(typ, 1) * n
        if size > 4:
            off = start + struct.unpack_from(e + "I", buf, entry + 8)[0]
            if 0 <= off and off + size <= len(buf):
                buf[off:off + size] = bytes(size)
        buf[entry:entry + 12] = bytes(12)


def _png_chunks(buf: bytearray) -> None:
    pos = 8
    while pos + 12 <= len(buf):
        length = struct.unpack_from(">I", buf, pos)[0]
        kind = bytes(buf[pos + 4:pos + 8])
        if kind == b"eXIf":
            _blank_tiff(buf, pos + 8)
            import zlib

            struct.pack_into(">I", buf, pos + 8 + length, zlib.crc32(bytes(buf[pos + 4:pos + 8 + length])) & 0xFFFFFFFF)
        if kind == b"IEND":
            return
        pos += 12 + length


def _riff_chunks(buf: bytearray) -> None:
    pos = 12
    while pos + 8 <= len(buf):
        kind = bytes(buf[pos:pos + 4])
        length = struct.unpack_from("<I", buf, pos + 4)[0]
        if kind == b"EXIF":
            body = pos + 8
            _blank_tiff(buf, body + 6 if bytes(buf[body:body + 4]) == b"Exif" else body)
        pos += 8 + length + (length & 1)


def scrub(data: bytes) -> bytes:
    buf = bytearray(data)
    if bytes(buf[:4]) in (b"II*\x00", b"MM\x00*"):
        _blank_tiff(buf, 0)
    if bytes(buf[:8]) == b"\x89PNG\r\n\x1a\n":
        _png_chunks(buf)
    if bytes(buf[:4]) == b"RIFF" and bytes(buf[8:12]) == b"WEBP":
        _riff_chunks(buf)
    for marker in (b"Exif\x00\x00", b"Exif\x00\x01"):
        pos = buf.find(marker)
        while pos != -1:
            _blank_tiff(buf, pos + 6)
            pos = buf.find(marker, pos + 6)
    _iim(buf)
    out = bytes(buf)
    out = XMP_GPS.sub(lambda m: m.group(1) + _same_len(m.group(2)), out)
    out = XMP_LOC.sub(lambda m: m.group(1) + _same_len(m.group(2)), out)
    if out[:8] == b"\x89PNG\r\n\x1a\n":
        fixed = bytearray(out)
        _png_crcs(fixed)
        out = bytes(fixed)
    return out


def _same_len(value: bytes) -> bytes:
    if value.startswith(b'="'):
        return b'="' + b" " * (len(value) - 3) + b'"'
    return b">" + b" " * (len(value) - 2) + b"<"


def has_gps(path: str) -> Optional[bool]:
    known = False
    try:
        from PIL import Image

        with Image.open(path) as img:
            gps = img.getexif().get_ifd(GPS_TAG)
        known = True
        if gps.get(2) or gps.get(4):
            return True
    except Exception:
        pass
    try:
        import exifread

        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
        known = True
        if any(k.startswith("GPS GPSLatitude") or k.startswith("GPS GPSLongitude") for k in tags):
            return True
    except Exception:
        pass
    if not known:
        return None
    with open(path, "rb") as handle:
        blob = handle.read()
    return bool(re.search(rb'exif:GPSL(?:atitude|ongitude)(="[^" ]|>[^< ])', blob))

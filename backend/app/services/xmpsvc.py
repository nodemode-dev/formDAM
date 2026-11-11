# Adapted from formlit backend/app/services/metadata.py & xmpembed.py (Apache-2.0, nodemode-ai); see LICENSES.md.
import html
import json
import os
import struct
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..db import ex, q, q1
from . import keywordsvc, libraryfs

NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpRights": "http://ns.adobe.com/xap/1.0/rights/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "Iptc4xmpCore": "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/",
    "Iptc4xmpExt": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
    "lr": "http://ns.adobe.com/lightroom/1.0/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "dam": "https://nodemode.ai/ns/formdam/1.0/",
}
for _p, _u in NS.items():
    ET.register_namespace(_p, _u)

FIELDS = ["headline", "creator", "creatorJob", "creatorAddress", "creatorCity", "creatorState", "creatorCountry", "creatorEmail",
          "creatorPhone", "creatorUrl", "copyright", "copyrightStatus", "rightsUsage", "copyrightUrl", "sublocation", "city", "state",
          "country", "isoCountryCode", "jobId", "instructions", "credit", "source", "intellectualGenre", "scene", "subjectCode",
          "event", "personShown", "extendedDescription"]
SIMPLE = {"headline": "photoshop:Headline", "city": "photoshop:City", "state": "photoshop:State", "country": "photoshop:Country",
          "isoCountryCode": "Iptc4xmpCore:CountryCode", "sublocation": "Iptc4xmpCore:Location", "instructions": "photoshop:Instructions",
          "jobId": "photoshop:TransmissionReference", "credit": "photoshop:Credit", "source": "photoshop:Source",
          "creatorJob": "photoshop:AuthorsPosition", "intellectualGenre": "Iptc4xmpCore:IntellectualGenre", "copyrightUrl": "xmpRights:WebStatement"}
ALT = {"title": "dc:title", "caption": "dc:description", "copyright": "dc:rights", "rightsUsage": "xmpRights:UsageTerms",
       "altText": "Iptc4xmpCore:AltTextAccessibility", "extendedDescription": "Iptc4xmpCore:ExtDescrAccessibility", "event": "Iptc4xmpExt:Event"}
BAG = {"scene": "Iptc4xmpCore:Scene", "subjectCode": "Iptc4xmpCore:SubjectCode", "personShown": "Iptc4xmpExt:PersonInImage"}
CONTACT = {"creatorAddress": "CiAdrExtadr", "creatorCity": "CiAdrCity", "creatorState": "CiAdrRegion", "creatorCountry": "CiAdrCtry",
           "creatorEmail": "CiEmailWork", "creatorPhone": "CiTelWork", "creatorUrl": "CiUrlWork"}
XMP_NS = b"http://ns.adobe.com/xap/1.0/\x00"


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _clark(qname: str) -> str:
    prefix, name = qname.split(":")
    return _q(prefix, name)


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _gps(value: float, pos: str, neg: str) -> str:
    v = abs(value)
    deg = int(v)
    return f"{deg},{(v - deg) * 60:.6f}{pos if value >= 0 else neg}"


def iptc_of(row) -> Dict[str, Any]:
    try:
        data = json.loads(row["iptc_json"]) if row["iptc_json"] else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def record_for(media_id: int, include_location: bool = True) -> Optional[Dict[str, Any]]:
    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    if row is None:
        return None
    meta = iptc_of(row)
    meta["title"] = row["title"] or meta.get("title")
    meta["caption"] = row["caption"] or meta.get("caption")
    meta["altText"] = row["alt_text"] or meta.get("altText")
    if include_location and not row["location_hidden"]:
        meta.setdefault("city", row["place"])
        meta.setdefault("state", row["admin"])
        meta.setdefault("country", row["country"])
    else:
        for key in ("sublocation", "city", "state", "country", "isoCountryCode"):
            meta.pop(key, None)
    people = [r["name"] for r in q("""SELECT DISTINCT p.name FROM faces f JOIN people p ON p.id=f.person_id
                                     WHERE f.media_id=? AND p.name IS NOT NULL AND p.hidden=0""", (media_id,))]
    if people and not meta.get("personShown"):
        meta["personShown"] = ", ".join(people)
    rec: Dict[str, Any] = {
        "rating": -1 if row["rejected"] else int(row["rating"] or 0),
        "label": row["label"] or "",
        "meta": {k: v for k, v in meta.items() if v},
        "keywords": keywordsvc.paths_for(media_id),
        "captureTime": datetime.fromtimestamp(row["created_ts"]).strftime("%Y-%m-%dT%H:%M:%S") if row["created_ts"] else None,
        "favorite": bool(row["favorite"]),
        "edit": row["edit_json"],
    }
    if include_location and not row["location_hidden"] and row["lat"] is not None:
        rec["gps"] = (row["lat"], row["lon"])
    return rec


def build_xmp(record: Dict[str, Any]) -> str:
    meta = record.get("meta", {}) or {}
    attrs = [f'xmp:Rating="{int(record.get("rating", 0))}"', f'xmp:MetadataDate="{time.strftime("%Y-%m-%dT%H:%M:%S")}"',
             'xmp:CreatorTool="FormDAM"']
    if record.get("label"):
        attrs.append(f'xmp:Label="{_esc(str(record["label"]).title())}"')
    for key, tag in SIMPLE.items():
        if meta.get(key):
            attrs.append(f'{tag}="{_esc(meta[key])}"')
    status = str(meta.get("copyrightStatus") or "").strip().lower()
    if status in ("copyrighted", "public domain"):
        attrs.append(f'xmpRights:Marked="{"True" if status == "copyrighted" else "False"}"')
    if record.get("captureTime"):
        attrs.append(f'photoshop:DateCreated="{_esc(record["captureTime"])}"')
    if record.get("gps"):
        lat, lon = record["gps"]
        attrs.append(f'exif:GPSLatitude="{_gps(lat, "N", "S")}"')
        attrs.append(f'exif:GPSLongitude="{_gps(lon, "E", "W")}"')
    if record.get("favorite"):
        attrs.append('dam:Favorite="True"')
    if record.get("edit"):
        attrs.append(f'dam:Edit="{_esc(record["edit"])}"')
    children: List[str] = []
    for key, tag in ALT.items():
        if meta.get(key):
            children.append(f'<{tag}><rdf:Alt><rdf:li xml:lang="x-default">{_esc(meta[key])}</rdf:li></rdf:Alt></{tag}>')
    for key, tag in BAG.items():
        items = [s.strip() for s in str(meta.get(key) or "").split(",") if s.strip()]
        if items:
            children.append(f"<{tag}><rdf:Bag>" + "".join(f"<rdf:li>{_esc(s)}</rdf:li>" for s in items) + f"</rdf:Bag></{tag}>")
    contact = "".join(f"<Iptc4xmpCore:{tag}>{_esc(meta[key])}</Iptc4xmpCore:{tag}>" for key, tag in CONTACT.items() if meta.get(key))
    if contact:
        children.append(f'<Iptc4xmpCore:CreatorContactInfo rdf:parseType="Resource">{contact}</Iptc4xmpCore:CreatorContactInfo>')
    if meta.get("creator"):
        children.append(f'<dc:creator><rdf:Seq><rdf:li>{_esc(meta["creator"])}</rdf:li></rdf:Seq></dc:creator>')
    kws = record.get("keywords") or []
    if kws:
        leaves = sorted({k.split("|")[-1] for k in kws})
        children.append("<dc:subject><rdf:Bag>" + "".join(f"<rdf:li>{_esc(k)}</rdf:li>" for k in leaves) + "</rdf:Bag></dc:subject>")
        children.append("<lr:hierarchicalSubject><rdf:Bag>" + "".join(f"<rdf:li>{_esc(k)}</rdf:li>" for k in sorted(kws)) + "</rdf:Bag></lr:hierarchicalSubject>")
    ns = " ".join(f'xmlns:{p}="{u}"' for p, u in NS.items() if p not in ("x", "rdf"))
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="FormDAM"><rdf:RDF xmlns:rdf="{NS["rdf"]}">'
            f'<rdf:Description rdf:about="" {ns} {" ".join(attrs)}>' + "".join(children) + "</rdf:Description></rdf:RDF></x:xmpmeta>\n"
            '<?xpacket end="w"?>\n')


def _alt(el) -> Optional[str]:
    if el is None:
        return None
    li = el.find(f".//{_q('rdf', 'li')}")
    return (li.text or "").strip() if li is not None else (el.text or "").strip() or None


def _bag(el) -> List[str]:
    if el is None:
        return []
    return [(li.text or "").strip() for li in el.iter(_q("rdf", "li")) if (li.text or "").strip()]


_SIMPLE_R = {_clark(v): k for k, v in SIMPLE.items()}
_ALT_R = {_clark(v): k for k, v in ALT.items()}
_BAG_R = {_clark(v): k for k, v in BAG.items()}
_CONTACT_R = {_q("Iptc4xmpCore", v): k for k, v in CONTACT.items()}


def parse_xmp(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    meta: Dict[str, Any] = {}
    for desc in root.iter(_q("rdf", "Description")):
        for k, v in desc.attrib.items():
            if k == _q("xmp", "Rating"):
                try:
                    out["rating"] = max(-1, min(5, int(float(v))))
                except ValueError:
                    pass
            elif k == _q("xmp", "Label"):
                out["label"] = v
            elif k in _SIMPLE_R:
                meta[_SIMPLE_R[k]] = v
            elif k == _q("xmpRights", "Marked"):
                meta["copyrightStatus"] = "Copyrighted" if v.strip().lower() == "true" else "Public Domain"
            elif k == _q("dam", "Favorite"):
                out["favorite"] = v.strip().lower() == "true"
        for child in desc:
            tag = child.tag
            if tag in _ALT_R:
                meta[_ALT_R[tag]] = _alt(child)
            elif tag in _BAG_R:
                meta[_BAG_R[tag]] = ", ".join(_bag(child))
            elif tag in _SIMPLE_R:
                meta[_SIMPLE_R[tag]] = (child.text or "").strip()
            elif tag == _q("Iptc4xmpCore", "CreatorContactInfo"):
                for kk, vv in child.attrib.items():
                    if kk in _CONTACT_R:
                        meta[_CONTACT_R[kk]] = vv
                for sub in child.iter():
                    if sub.tag in _CONTACT_R:
                        meta[_CONTACT_R[sub.tag]] = (sub.text or "").strip()
            elif tag == _q("dc", "creator"):
                names = _bag(child)
                if names:
                    meta["creator"] = ", ".join(names)
            elif tag == _q("dc", "subject"):
                out.setdefault("keywords", _bag(child))
            elif tag == _q("lr", "hierarchicalSubject"):
                out["keywords"] = _bag(child)
            elif tag == _q("xmp", "Rating"):
                try:
                    out["rating"] = int(float(child.text or 0))
                except ValueError:
                    pass
            elif tag == _q("xmp", "Label"):
                out["label"] = (child.text or "").strip()
    if meta:
        out["meta"] = {k: v for k, v in meta.items() if v}
    return out


def sidecar_for(path: str) -> str:
    return os.path.splitext(path)[0] + ".xmp"


def find_sidecar(path: str) -> Optional[str]:
    for candidate in (os.path.splitext(path)[0] + ".xmp", os.path.splitext(path)[0] + ".XMP", path + ".xmp"):
        if os.path.isfile(candidate):
            return candidate
    return None


def apply_record(media_id: int, rec: Dict[str, Any]) -> None:
    meta = dict(rec.get("meta") or {})
    sets, params = [], []
    if "rating" in rec:
        if rec["rating"] < 0:
            sets.append("rejected=1")
        else:
            sets.append("rating=?")
            params.append(int(rec["rating"]))
    label = str(rec.get("label") or "").strip().lower()
    if label in ("red", "orange", "yellow", "green", "blue", "purple", "gray"):
        sets.append("label=?")
        params.append(label)
    for col, key in (("title", "title"), ("caption", "caption"), ("alt_text", "altText")):
        if meta.get(key):
            sets.append(f"{col}=?")
            params.append(meta.pop(key))
    if rec.get("favorite"):
        sets.append("favorite=1")
    row = q1("SELECT iptc_json FROM media WHERE id=?", (media_id,))
    current = iptc_of(row) if row else {}
    current.update({k: v for k, v in meta.items() if k in FIELDS and v})
    sets.append("iptc_json=?")
    params.append(json.dumps(current) if current else None)
    ex(f"UPDATE media SET {', '.join(sets)} WHERE id=?", (*params, media_id))
    if rec.get("keywords"):
        keywordsvc.assign([media_id], [str(k) for k in rec["keywords"]], [])


def import_sidecar(media_id: int, source_path: str, stored_path: Optional[str] = None) -> bool:
    side = find_sidecar(source_path)
    text = None
    if side:
        try:
            with open(side, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = None
    if text is None:
        text = embedded_xmp(stored_path or source_path)
    if not text:
        return False
    rec = parse_xmp(text)
    if not rec:
        return False
    apply_record(media_id, rec)
    return True


def embedded_xmp(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            data = fh.read(4 * 1024 * 1024)
    except OSError:
        return None
    i = data.find(b"<x:xmpmeta")
    if i < 0:
        return None
    j = data.find(b"</x:xmpmeta>", i)
    if j < 0:
        return None
    return data[i:j + len(b"</x:xmpmeta>")].decode("utf-8", errors="replace")


def write_sidecar(media_id: int) -> Optional[str]:
    from .. import vaultcrypt

    row = q1("SELECT * FROM media WHERE id=?", (media_id,))
    if row is None or vaultcrypt.protected(row) or vaultcrypt.is_vaulted(media_id):
        return None
    src = libraryfs.abs_path(row["rel_path"])
    if not os.path.isfile(src):
        return None
    rec = record_for(media_id)
    if rec is None:
        return None
    side = sidecar_for(src)
    stem = os.path.splitext(row["rel_path"])[0]
    pattern = stem.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + ".%"
    for other in q("SELECT rel_path FROM media WHERE id<>? AND rel_path LIKE ? ESCAPE '\\'", (media_id, pattern)):
        if os.path.splitext(other["rel_path"])[0] == stem:
            side = src + ".xmp"
            break
    if os.path.isfile(side):
        try:
            with open(side, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(65536)
        except OSError:
            return None
        if 'x:xmptk="FormDAM"' not in head:
            return None
    tmp = side + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(build_xmp(rec))
    os.replace(tmp, side)
    ex("UPDATE media SET xmp_ts=? WHERE id=?", (time.time(), media_id))
    return side


def pending() -> int:
    return q1("SELECT COUNT(*) AS n FROM media WHERE xmp_ts IS NULL AND trashed_ts IS NULL AND live_of IS NULL")["n"]


def sidecar_job(state: Dict[str, Any]) -> None:
    counts = {"written": 0, "skipped": 0}
    state["counts"] = counts
    for row in q("SELECT id FROM media WHERE xmp_ts IS NULL AND trashed_ts IS NULL AND live_of IS NULL ORDER BY id"):
        try:
            done = write_sidecar(row["id"])
        except OSError:
            done = None
        if done:
            counts["written"] += 1
        else:
            counts["skipped"] += 1
            ex("UPDATE media SET xmp_ts=? WHERE id=?", (time.time(), row["id"]))


def write_jpeg_xmp(path: str, packet: str) -> None:
    raw = packet.encode("utf-8")
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    body = XMP_NS + raw
    if len(body) + 2 > 65535:
        raise ValueError("XMP packet too large for one JPEG segment")
    out = bytearray(b"\xff\xd8")
    i, inserted = 2, False
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xD9, 0xDA):
            break
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + length]
        is_xmp = marker == 0xE1 and seg[4:4 + len(XMP_NS)] == XMP_NS
        if not inserted and marker not in (0xE0, 0xE1):
            out += b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body
            inserted = True
        if not is_xmp:
            out += seg
        i += 2 + length
    if not inserted:
        out += b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body
    out += data[i:]
    tmp = path + ".dam-xmp"
    with open(tmp, "wb") as fh:
        fh.write(bytes(out))
    os.replace(tmp, path)

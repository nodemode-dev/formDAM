import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..config import library_root
from ..db import setting_get

DEFAULT_PORT = 8792
BEACON_PORT = 48792
BEACON_EVERY_S = 20
PEER_TTL_S = 300
SKEW_S = 120
KEY_RE = re.compile(r"^[A-Z2-7]{32}$")
SAFE_FILE = re.compile(r"^\d{8}\.jsonl$")
SAFE_OBJ = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]{1,6}$")
SAFE_DEV = re.compile(r"^[0-9a-f]{32}$")
SAFE_EDIT = re.compile(r"^[\w.-]{1,120}$")

_lock = threading.Lock()
_peers: Dict[str, Dict[str, Any]] = {}
_nonces: Dict[str, float] = {}
_tried: Dict[Tuple[str, str], float] = {}
CONFIRM_EVERY_S = 60
_threads: Dict[str, threading.Thread] = {}
_stop = threading.Event()


def mirror() -> str:
    path = os.path.join(library_root(), "family")
    os.makedirs(path, exist_ok=True)
    return path


def new_key() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def normalize_key(raw: str) -> Optional[str]:
    key = re.sub(r"[^A-Za-z2-7]", "", raw or "").upper()
    return key if KEY_RE.match(key) else None


def pretty_key(key: str) -> str:
    return "-".join(key[i:i + 4] for i in range(0, len(key), 4))


def settings() -> Dict[str, Any]:
    try:
        port = int(setting_get("family_port") or DEFAULT_PORT)
    except ValueError:
        port = DEFAULT_PORT
    key = setting_get("family_key") or ""
    return {"enabled": setting_get("family_enabled") == "1" and bool(key), "port": port, "has_key": bool(key)}


def _key() -> bytes:
    key = setting_get("family_key") or ""
    return base64.b32decode(key) if key else b""


def _derive(label: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"formdam-family-v1", info=label).derive(_key())


def family_id() -> str:
    if not _key():
        return ""
    digest = hmac.new(_derive(b"id"), b"family", hashlib.sha256).hexdigest()[:12].upper()
    return "-".join(digest[i:i + 4] for i in range(0, 12, 4))


def private_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_link_local or (ip.is_private and not ip.is_global and not ip.is_unspecified)


def sign(method: str, path: str, ts: str, nonce: str, device: str) -> str:
    body = "\n".join((method.upper(), path, ts, nonce, device)).encode()
    return hmac.new(_derive(b"auth"), body, hashlib.sha256).hexdigest()


def verify(method: str, path: str, headers: Dict[str, str]) -> Optional[str]:
    device, ts, nonce, sig = (headers.get(k, "") for k in ("x-fam-device", "x-fam-ts", "x-fam-nonce", "x-fam-sig"))
    if not SAFE_DEV.match(device) or not re.match(r"^[0-9a-f]{32}$", nonce):
        return None
    try:
        if abs(time.time() - float(ts)) > SKEW_S:
            return None
    except ValueError:
        return None
    if not hmac.compare_digest(sign(method, path, ts, nonce, device), sig):
        return None
    now = time.time()
    with _lock:
        for old in [n for n, t in _nonces.items() if now - t > SKEW_S * 2]:
            _nonces.pop(old, None)
        if nonce in _nonces:
            return None
        _nonces[nonce] = now
    return device


def seal(data: bytes, path: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(_derive(b"enc")).encrypt(nonce, data, path.encode())


def unseal(blob: bytes, path: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(_derive(b"enc")).decrypt(blob[:12], blob[12:], path.encode())


def bound(path: str, nonce: str) -> str:
    return f"{path}\n{nonce}"


def _request(peer: Dict[str, Any], path: str, timeout: float = 30.0) -> bytes:
    from .syncsvc import device_id

    ts, nonce = f"{time.time():.3f}", secrets.token_hex(16)
    req = urllib.request.Request(f"http://{peer['ip']}:{peer['port']}{path}", headers={
        "x-fam-device": device_id(), "x-fam-ts": ts, "x-fam-nonce": nonce, "x-fam-sig": sign("GET", path, ts, nonce, device_id())})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as res:
        return unseal(res.read(), bound(path, nonce))


def _confirm(ip: str, port: int, dev: str) -> Optional[Dict[str, Any]]:
    try:
        info = json.loads(_request({"ip": ip, "port": port}, "/f/hello", timeout=8).decode())
    except Exception:
        return None
    return info if str(info.get("dev") or "") == dev else None


def _beacon_payload() -> bytes:
    from .syncsvc import device_id, device_name

    ts = f"{time.time():.0f}"
    dev, port = device_id(), str(settings()["port"])
    mac = hmac.new(_derive(b"beacon"), "|".join((dev, port, ts)).encode(), hashlib.sha256).hexdigest()
    return json.dumps({"fam": 1, "dev": dev, "port": port, "ts": ts, "mac": mac, "name": seal(device_name().encode(), "/beacon").hex()}).encode()


def _accept_beacon(data: bytes, ip: str) -> None:
    from .syncsvc import device_id

    if not private_ip(ip):
        return
    try:
        msg = json.loads(data.decode())
        dev, port, ts, mac = str(msg["dev"]), str(msg["port"]), str(msg["ts"]), str(msg["mac"])
        if not SAFE_DEV.match(dev) or dev == device_id() or abs(time.time() - float(ts)) > SKEW_S:
            return
        want = hmac.new(_derive(b"beacon"), "|".join((dev, port, ts)).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, mac):
            return
        name = unseal(bytes.fromhex(str(msg.get("name") or "")), "/beacon").decode()[:60]
        port_n = int(port)
    except Exception:
        return
    now = time.time()
    with _lock:
        known = _peers.get(dev)
        if known is not None and known["ip"] == ip and known["port"] == port_n:
            known["seen"] = now
            return
        if now - _tried.get((dev, ip), 0.0) < CONFIRM_EVERY_S:
            return
        _tried[(dev, ip)] = now
    if _confirm(ip, port_n, dev) is None:
        return
    with _lock:
        _peers[dev] = {"dev": dev, "ip": ip, "port": port_n, "seen": now, "name": name, "manual": False}


def add_manual(address: str) -> Dict[str, Any]:
    host, _, port = address.strip().rpartition(":")
    if not host:
        host, port = address.strip(), str(settings()["port"])
    try:
        ip = socket.gethostbyname(host)
    except OSError as exc:
        raise ValueError("That address cannot be found") from exc
    if not private_ip(ip):
        raise ValueError("Only addresses on your local network can be added")
    peer = {"ip": ip, "port": int(port)}
    info = json.loads(_request(peer, "/f/hello", timeout=8).decode())
    from .syncsvc import device_id

    if not SAFE_DEV.match(str(info.get("dev") or "")) or info["dev"] == device_id():
        raise ValueError("That device did not answer as a formDAM family member")
    with _lock:
        _peers[info["dev"]] = {"dev": info["dev"], "ip": ip, "port": int(port), "seen": time.time(), "name": str(info.get("name") or "")[:60], "manual": True}
    return _peers[info["dev"]]


def peers() -> List[Dict[str, Any]]:
    now = time.time()
    with _lock:
        return [dict(p) for p in _peers.values() if p.get("manual") or now - p["seen"] < PEER_TTL_S]


def _beacon_loop() -> None:
    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while not _stop.is_set():
        try:
            if settings()["enabled"]:
                payload = _beacon_payload()
                for target in _broadcast_targets():
                    try:
                        send.sendto(payload, (target, BEACON_PORT))
                    except OSError:
                        pass
        except Exception:
            pass
        finally:
            from ..db import reset_thread_conn

            reset_thread_conn()
        _stop.wait(BEACON_EVERY_S)


def _broadcast_targets() -> List[str]:
    out = ["255.255.255.255"]
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        ip = probe.getsockname()[0]
        probe.close()
        if private_ip(ip):
            out.append(".".join(ip.split(".")[:3] + ["255"]))
    except OSError:
        pass
    return out


def _listen_loop() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    try:
        sock.bind(("", BEACON_PORT))
    except OSError:
        return
    sock.settimeout(2.0)
    while not _stop.is_set():
        try:
            data, (ip, _) = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            if settings()["enabled"]:
                _accept_beacon(data, ip)
        finally:
            from ..db import reset_thread_conn

            reset_thread_conn()
    sock.close()


def start_discovery() -> None:
    _stop.clear()
    for name, target in (("beacon", _beacon_loop), ("listen", _listen_loop)):
        thread = _threads.get(name)
        if thread is None or not thread.is_alive():
            _threads[name] = threading.Thread(target=target, name=f"formDAM-family-{name}", daemon=True)
            _threads[name].start()


def stop_discovery() -> None:
    _stop.set()
    with _lock:
        _peers.clear()


def fetch(state: Dict[str, Any]) -> Dict[str, int]:
    from .syncsvc import device_id

    counts = {"peers": 0, "files": 0, "objects": 0, "errors": 0}
    base = os.path.join(mirror(), "DAM Sync")
    for peer in peers():
        try:
            listing = json.loads(_request(peer, "/f/journal").decode())
            counts["peers"] += 1
            dev = str(listing.get("dev") or "")
            if not SAFE_DEV.match(dev) or dev != peer.get("dev") or dev == device_id():
                continue
            folder = os.path.join(base, "journal", dev)
            os.makedirs(folder, exist_ok=True)
            for item in listing.get("files", []):
                name, size = str(item.get("name") or ""), int(item.get("size") or 0)
                if not SAFE_FILE.match(name):
                    continue
                local = os.path.join(folder, name)
                if os.path.isfile(local) and os.path.getsize(local) == size:
                    continue
                data = _request(peer, f"/f/journal/{name}")
                _write(local, data)
                counts["files"] += 1
                counts["objects"] += _fetch_objects(peer, base, data)
            with _lock:
                if dev in _peers:
                    _peers[dev]["synced"] = time.time()
        except Exception:
            counts["errors"] += 1
    state.update(counts)
    return counts


def _fetch_objects(peer: Dict[str, Any], base: str, data: bytes) -> int:
    got = 0
    for line in data.decode("utf-8", "ignore").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("op") != "media":
            continue
        wanted = [(rec.get("sha"), rec.get("name"))]
        if isinstance(rec.get("live"), dict):
            wanted.append((rec["live"].get("sha"), rec["live"].get("name")))
        for sha, name in wanted:
            ext = os.path.splitext(str(name or ""))[1].lower()
            key = f"{str(sha or '').lower()}{ext}"
            if not SAFE_OBJ.match(key):
                continue
            local = os.path.join(base, "objects", key[:2], key)
            if os.path.isfile(local):
                continue
            try:
                _write(local, _request(peer, f"/f/object/{key}", timeout=600))
                got += 1
            except Exception:
                continue
        edit = ((rec.get("fields") or {}).get("edit_json") or "")
        try:
            name = os.path.basename(((json.loads(edit) or {}).get("external") or {}).get("file") or "") if edit else ""
        except (ValueError, AttributeError):
            name = ""
        if name and SAFE_EDIT.match(name):
            local = os.path.join(base, "objects", "edits", name)
            if not os.path.isfile(local):
                try:
                    _write(local, _request(peer, f"/f/edit/{name}"))
                except Exception:
                    pass
    return got


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)


def serve_path(kind: str, name: str) -> Optional[str]:
    from .syncsvc import device_id

    base = os.path.join(mirror(), "DAM Sync")
    if kind == "journal" and SAFE_FILE.match(name):
        path = os.path.join(base, "journal", device_id(), name)
    elif kind == "object" and SAFE_OBJ.match(name):
        path = os.path.join(base, "objects", name[:2], name)
    elif kind == "edit" and SAFE_EDIT.match(name):
        path = os.path.join(base, "objects", "edits", name)
    else:
        return None
    return path if os.path.isfile(path) else None


def journal_listing() -> Dict[str, Any]:
    from .syncsvc import device_id

    folder = os.path.join(mirror(), "DAM Sync", "journal", device_id())
    files = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if SAFE_FILE.match(name):
                files.append({"name": name, "size": os.path.getsize(os.path.join(folder, name))})
    return {"dev": device_id(), "files": files}


def endpoint_ready() -> Tuple[bool, str]:
    return settings()["enabled"], family_id()

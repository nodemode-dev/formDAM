import hashlib
import os
import sys
import time
import urllib.request


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: fetch_model.py <models dir> <name> <url> <sha256>")
        return 2
    folder, name, url, sha = sys.argv[1:]
    target = os.path.join(folder, name)
    if os.path.isfile(target) and sha256_of(target) == sha:
        print(f"model ok: {name}")
        return 0
    os.makedirs(folder, exist_ok=True)
    part = target + ".part"
    for attempt in range(5):
        try:
            print(f"downloading {name}")
            urllib.request.urlretrieve(url, part)
            break
        except OSError as exc:
            print(f"retrying {name}: {exc}")
            time.sleep(3)
    else:
        print(f"could not download {name} (network or DNS); run the installer again when the connection is back")
        return 1
    if sha256_of(part) != sha:
        os.remove(part)
        print(f"checksum mismatch for {name}")
        return 1
    os.replace(part, target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

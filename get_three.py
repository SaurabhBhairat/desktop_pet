r"""
get_three.py - downloads the 3D engine (three.js) ONCE, so the dragon can start without internet.

Run it once while you are online:
    .\voice_env\Scripts\python.exe get_three.py

The files go to assets\models\vendor\ (they are not uploaded to GitHub).
After that the dragon uses these local copies and never needs the internet to draw itself.
"""
import sys
import urllib.request
from pathlib import Path

BASE = "https://cdn.jsdelivr.net/npm/three@0.160.0/"
ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "assets" / "models" / "vendor"
FILES = [   # (address on the CDN, where it is saved, smallest believable size in bytes)
    ("build/three.module.js", VENDOR / "three.module.js", 500_000),
    ("examples/jsm/loaders/GLTFLoader.js", VENDOR / "addons" / "loaders" / "GLTFLoader.js", 40_000),
    ("examples/jsm/utils/BufferGeometryUtils.js", VENDOR / "addons" / "utils" / "BufferGeometryUtils.js", 10_000),
]


def download(url, dest, min_size):
    req = urllib.request.Request(url, headers={"User-Agent": "BabyDragon-setup"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if len(data) < min_size or b"export" not in data:
        raise ValueError("the downloaded file does not look right (%d bytes)" % len(data))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)                       # the real file only appears once it is complete
    return len(data)


def main():
    if not (ROOT / "assets" / "models").is_dir():
        sys.exit("Cannot find the folder: %s" % (ROOT / "assets" / "models"))
    failed = False
    for path, dest, min_size in FILES:
        if dest.is_file() and dest.stat().st_size >= min_size:
            print("already there:", dest.relative_to(ROOT))
            continue
        try:
            size = download(BASE + path, dest, min_size)
            print("downloaded: %s (%d KB)" % (dest.relative_to(ROOT), size // 1024))
        except Exception as exc:
            failed = True
            print("FAILED: %s -> %s" % (path, exc))
    if failed:
        sys.exit("Some files failed. Check your internet connection and run this again.")
    print("Done. The dragon can now start without internet.")


if __name__ == "__main__":
    main()

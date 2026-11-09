import argparse
import json
import math
import struct
import sys

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
FLOAT = 5126


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 12:
        sys.exit("File is too small to be a GLB.")
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        sys.exit("Not a binary glTF 2.0 (.glb) file.")
    offset = 12
    gltf, blob = None, b""
    while offset + 8 <= len(data):
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset:offset + chunk_len]
        if len(chunk) != chunk_len:
            sys.exit("GLB contains an incomplete chunk.")
        offset += chunk_len
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8"))
        elif chunk_type == BIN_CHUNK and not blob:
            blob = chunk
    if gltf is None:
        sys.exit("No JSON chunk found in the GLB.")
    return gltf, blob


def write_glb(path, gltf, blob):
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    blob += b"\\x00" * (-len(blob) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<II", len(json_bytes), JSON_CHUNK))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(blob), BIN_CHUNK))
        f.write(blob)


def model_height(gltf):
    lo, hi = math.inf, -math.inf
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            idx = prim.get("attributes", {}).get("POSITION")
            if idx is None:
                continue
            acc = gltf["accessors"][idx]
            if "min" in acc and "max" in acc:
                lo = min(lo, acc["min"][1])
                hi = max(hi, acc["max"][1])
    return (hi - lo) if hi > lo else 1.0


def add_accessor(gltf, blob, values, acc_type, with_bounds=False):
    blob += b"\\x00" * (-len(blob) % 4)
    start = len(blob)
    flat = [x for v in values for x in (v if isinstance(v, (list, tuple)) else [v])]
    blob += struct.pack("<%df" % len(flat), *flat)
    gltf.setdefault("bufferViews", []).append(
        {"buffer": 0, "byteOffset": start, "byteLength": len(flat) * 4}
    )
    acc = {
        "bufferView": len(gltf["bufferViews"]) - 1,
        "componentType": FLOAT,
        "count": len(values),
        "type": acc_type,
    }
    if with_bounds:
        acc["min"] = [min(flat)]
        acc["max"] = [max(flat)]
    gltf.setdefault("accessors", []).append(acc)
    return len(gltf["accessors"]) - 1, blob


def add_idle(gltf, blob, loop_seconds, fps, bob, sway_deg, breath):
    if loop_seconds <= 0 or fps <= 0:
        sys.exit("--seconds and --fps must be greater than zero.")
    height = model_height(gltf)
    frames = int(loop_seconds * fps)
    if frames < 1:
        sys.exit("Loop must contain at least one frame.")
    scene_idx = gltf.get("scene", 0)
    scene = gltf["scenes"][scene_idx]
    nodes = gltf.setdefault("nodes", [])
    nodes.append({"name": "DragonRoot", "children": list(scene["nodes"])})
    root = len(nodes) - 1
    scene["nodes"] = [root]

    times, pos, rot, scl = [], [], [], []
    for i in range(frames + 1):
        t = i / frames
        wave = math.sin(2 * math.pi * t)
        slow = math.cos(2 * math.pi * t)
        times.append(t * loop_seconds)
        pos.append([0.0, bob * height * wave, 0.0])
        a = math.radians(sway_deg) * slow / 2
        rot.append([0.0, math.sin(a), 0.0, math.cos(a)])
        scl.append([1 - breath * 0.5 * wave, 1 + breath * wave, 1 - breath * 0.5 * wave])

    t_acc, blob = add_accessor(gltf, blob, times, "SCALAR", True)
    p_acc, blob = add_accessor(gltf, blob, pos, "VEC3")
    r_acc, blob = add_accessor(gltf, blob, rot, "VEC4")
    s_acc, blob = add_accessor(gltf, blob, scl, "VEC3")
    samplers = [
        {"input": t_acc, "output": p_acc, "interpolation": "LINEAR"},
        {"input": t_acc, "output": r_acc, "interpolation": "LINEAR"},
        {"input": t_acc, "output": s_acc, "interpolation": "LINEAR"},
    ]
    channels = [
        {"sampler": 0, "target": {"node": root, "path": "translation"}},
        {"sampler": 1, "target": {"node": root, "path": "rotation"}},
        {"sampler": 2, "target": {"node": root, "path": "scale"}},
    ]
    gltf.setdefault("animations", []).append(
        {"name": "Idle", "samplers": samplers, "channels": channels}
    )
    total = len(blob) + (-len(blob) % 4)
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = total
        gltf["buffers"][0].pop("uri", None)
    else:
        gltf["buffers"] = [{"byteLength": total}]
    return blob


def main():
    ap = argparse.ArgumentParser(description="Add an idle animation to a GLB.")
    ap.add_argument("input", help="input .glb file")
    ap.add_argument("output", nargs="?", help="output .glb (default: <input>_idle.glb)")
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--bob", type=float, default=0.02)
    ap.add_argument("--sway", type=float, default=4.0)
    ap.add_argument("--breath", type=float, default=0.02)
    args = ap.parse_args()
    out = args.output or (args.input.rsplit(".", 1)[0] + "_idle.glb")
    gltf, blob = read_glb(args.input)
    if gltf.get("animations"):
        print("Note: file already has animations; adding Idle alongside them.")
    blob = add_idle(gltf, blob, args.seconds, args.fps, args.bob, args.sway, args.breath)
    write_glb(out, gltf, blob)
    print("Saved:", out)


if __name__ == "__main__":
    main()

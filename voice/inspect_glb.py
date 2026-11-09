"""
inspect_glb.py - shows what is inside a GLB: skeleton, animations, textures.

    python inspect_glb.py assets\\models\\baby_dragon_idle.glb
"""
import json
import struct
import sys

if len(sys.argv) < 2:
    sys.exit("Usage: python inspect_glb.py path\\to\\model.glb")

with open(sys.argv[1], "rb") as f:
    data = f.read()
magic, version, _ = struct.unpack_from("<4sII", data, 0)
if magic != b"glTF":
    sys.exit("Not a .glb file")
off, g = 12, None
while off < len(data):
    n, t = struct.unpack_from("<II", data, off)
    if t == 0x4E4F534A:
        g = json.loads(data[off + 8: off + 8 + n].decode("utf-8"))
    off += 8 + n

nodes = g.get("nodes", [])
print("Meshes    :", len(g.get("meshes", [])))
print("Materials :", len(g.get("materials", [])))
print("Textures  :", len(g.get("textures", [])), "(0 = no paint, only plain colors)")

skins = g.get("skins", [])
print("Skeletons :", len(skins), "(0 = no bones, legs cannot move)")
for s in skins:
    names = [nodes[j].get("name", "?") for j in s["joints"]]
    print("  bones (%d): %s" % (len(names), ", ".join(names[:60])))

anims = g.get("animations", [])
print("Animations:", len(anims))
for a in anims:
    dur = 0
    for sm in a["samplers"]:
        acc = g["accessors"][sm["input"]]
        if "max" in acc:
            dur = max(dur, acc["max"][0])
    targets = {nodes[c["target"]["node"]].get("name", "?") for c in a["channels"] if "node" in c["target"]}
    print("  '%s'  %.1fs  moves %d parts" % (a.get("name", "?"), dur, len(targets)))
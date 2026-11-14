"""
dragon_window.py - transparent, always-on-top desktop window that shows
your dragon GLB and plays its animations.

Setup (once, inside your dragon_env):
    pip install PySide6

Run:
    python dragon_window.py assets/dragon_idle.glb

Controls:
    Left-drag   move the dragon around the screen
    Right-click menu: change state / quit

Use it from your voice code (same process):
    from dragon_window import DragonWindow
    win = DragonWindow("assets/dragon_idle.glb")
    win.show()
    win.state_requested.emit("listening")   # safe to call from any thread

State names are matched against animation clip names in the GLB
(e.g. a clip called "Idle" or "Talk"). If no clip matches, the dragon
keeps playing whatever clip it has (your "Idle" clip works for all states).
"""
import functools
import http.server
import json
import os
import random
import socketserver
import sys
import threading
import time
from pathlib import Path

try:
    from voice.dragon_brain import DragonBrain       # when started from run_dragon.py
except ImportError:
    from dragon_brain import DragonBrain             # when this file is run directly

try:
    from voice import dragon_settings            # when started from run_dragon.py
except ImportError:
    import dragon_settings                       # when this file is run directly

try:
    from voice import dragon_bubble              # when started from run_dragon.py
except ImportError:
    import dragon_bubble                         # when this file is run directly

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMainWindow, QSystemTrayIcon
from PySide6.QtWebEngineWidgets import QWebEngineView

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "shared" / "settings.json"


def load_dragon_settings():
    """Reads the optional "dragon" section of shared/settings.json (never writes to it).
    cursor_look  (default True)  - turns toward your mouse and reacts when it hovers on it
    cursor_chase (default False) - walks after your mouse along the screen"""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        cfg = data.get("dragon", {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


# Global hotkeys (work from any program). Windows modifiers: Ctrl=0x2, Alt=0x1, Shift=0x4, Win=0x8.
# Plain Ctrl+A / Ctrl+C are Select All / Copy, so they are NOT used here.
HOTKEY_SHOW = (0x2 | 0x1, ord("A"))        # Ctrl + Alt + A  -> bring the dragon back
HOTKEY_HIDE = (0x2 | 0x1, ord("C"))        # Ctrl + Alt + C  -> hide the dragon

# If the dragon stays hidden this long it quits itself to free memory (0 = never).
# Ctrl+Alt+A (the Windows shortcut key) then starts it again.
AUTO_QUIT_MINUTES = 60

STATES = ["idle", "listening", "thinking", "talking", "sleeping"]
WINDOW_SIZE = (170, 200)          # small by default; right-click > Size to change

HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html, body { margin:0; background:transparent; overflow:hidden; }
  canvas { display:block; filter: drop-shadow(0 0 6px rgba(200,140,255,0.85)) drop-shadow(0 0 14px rgba(150,80,255,0.55)); }
  #warn { display:none; position:fixed; left:6px; right:6px; top:38%; padding:6px; font:11px sans-serif; color:#fff;
          background:rgba(60,20,90,0.92); border-radius:8px; text-align:center; }
  #fx { position:fixed; top:5%; right:12%; font-size:26px; pointer-events:none;
        animation: fxbob 2s ease-in-out infinite; }
  @keyframes fxbob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
</style>
<script type="importmap">
{ "imports": {
    "three": "__THREE_URL__",
    "three/addons/": "__ADDONS_URL__"
} }
</script>
</head>
<body>
<div id="fx"></div>
<div id="warn"></div>
<script>setTimeout(function () { if (!window.__dragonReady) { var w = document.getElementById("warn");
  w.textContent = "3D engine missing. Run get_three.py once (needs internet)."; w.style.display = "block"; } }, 8000);</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
window.__dragonReady = true;      // lets the page warn you if the 3D engine could not be loaded

const MODEL_URL = "__MODEL_URL__";

const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.01, 1000);
scene.add(new THREE.HemisphereLight(0xffffff, 0x666688, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(2, 4, 3);
scene.add(sun);

let mixer = null;
let pivot = null, baseHeight = 1, baseY = 0;
let actions = {};
let current = null;
const clock = new THREE.Clock();

// Colors an untextured model by body position: purple body, lilac wings,
// cream belly / horns / claws. Skipped if the mesh already has a texture.
// Tweak the numbers below if a part lands in the wrong place.
function paintDragon(model, box) {
  const size = box.getSize(new THREE.Vector3());
  const cx = (box.min.x + box.max.x) / 2;
  const purple = new THREE.Color(0x7b3fc4);
  const lilac  = new THREE.Color(0xa77be0);
  const cream  = new THREE.Color(0xf3e3c3);
  const v = new THREE.Vector3();
  const n = new THREE.Vector3();
  const c = new THREE.Color();
  const sstep = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const nm = new THREE.Matrix3();
  model.updateMatrixWorld(true);

  model.traverse((o) => {
    if (!o.isMesh || !o.geometry.attributes.position) return;
    if (o.material && o.material.map) return;          // already textured
    const pos = o.geometry.attributes.position;
    const nor = o.geometry.attributes.normal;
    const colors = new Float32Array(pos.count * 3);
    nm.getNormalMatrix(o.matrixWorld);

    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
      const ny = (v.y - box.min.y) / size.y;            // 0 = feet, 1 = top
      const nx = (v.x - cx) / (size.x / 2);             // -1 left .. 1 right
      let nz = 1;
      if (nor) nz = n.fromBufferAttribute(nor, i).applyMatrix3(nm).normalize().z;

      const ax = Math.abs(nx);
      c.copy(purple);
      // wings: soft lilac at the sides, only below head height
      c.lerp(lilac, sstep(0.50, 0.62, ax) * (1 - sstep(0.62, 0.70, ny)));
      // horns / ears: cream on the upper sides of the head, crest stays purple
      c.lerp(cream, sstep(0.28, 0.38, ax) * sstep(0.68, 0.74, ny));
      // claws: just the toe tips
      c.lerp(cream, 1 - sstep(0.02, 0.045, ny));
      // belly: oval patch on the front of the body
      const r = Math.sqrt((nx / 0.26) ** 2 + ((ny - 0.33) / 0.20) ** 2);
      c.lerp(cream, (1 - sstep(0.80, 1.10, r)) * sstep(0.05, 0.25, nz));
      colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b;
    }
    o.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    // Keep the model's own material (it rendered fine) and tint it per vertex.
    const mat = Array.isArray(o.material) ? o.material[0] : o.material;
    const fixed = mat.clone();
    fixed.vertexColors = true;
    fixed.color.set(0xffffff);
    if (fixed.emissive) fixed.emissive.set(0x000000);
    fixed.needsUpdate = true;
    o.material = fixed;
  });
}

// ---- front-projected skin: the reference picture is wrapped onto the model from the front ----
// Put dragon_texture.png next to the .glb. Surfaces facing the viewer show the picture
// (eyes, belly pattern, shading); sides and back keep the painted colours. Delete the PNG to switch it off.
const TEX_U0 = 0, TEX_U1 = 1, TEX_V0 = 0, TEX_V1 = 1;   // which part of the picture covers the model
let texturedMeshes = [];

function applyTexture(model, texture) {
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  model.traverse((o) => {
    if (!o.isMesh || !o.geometry.attributes.position) return;
    const geo = o.geometry;
    geo.computeBoundingBox();
    const b = geo.boundingBox;
    const sx = b.max.x - b.min.x, sy = b.max.y - b.min.y;
    const pos = geo.attributes.position;
    if (!geo.attributes.normal) geo.computeVertexNormals();
    const nor = geo.attributes.normal;
    const uv = new Float32Array(pos.count * 2), face = new Float32Array(pos.count);
    for (let i = 0; i < pos.count; i++) {
      uv[i * 2] = TEX_U0 + (pos.getX(i) - b.min.x) / sx * (TEX_U1 - TEX_U0);
      uv[i * 2 + 1] = TEX_V0 + (pos.getY(i) - b.min.y) / sy * (TEX_V1 - TEX_V0);
      face[i] = smooth(0.15, 0.55, nor.getZ(i));          // 1 = facing the viewer, 0 = side/back
    }
    geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    o.userData.paletteMaterial = o.material;              // kept as a safety net
    const m = o.material.clone();
    m.map = texture;
    if (geo.attributes.color) {                           // blend picture (front) with painted colours (rest)
      geo.setAttribute('aFace', new THREE.BufferAttribute(face, 1));
      m.onBeforeCompile = (shader) => {
        shader.vertexShader = 'attribute float aFace;\\nvarying float vFace;\\n' +
          shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\\n  vFace = aFace;');
        shader.fragmentShader = 'varying float vFace;\\n' +
          shader.fragmentShader.replace('#include <color_fragment>',
            'diffuseColor.rgb = mix(vColor.rgb, diffuseColor.rgb, vFace);')
          .replace('#include <emissivemap_fragment>',
            '#include <emissivemap_fragment>\\n' +
            '  float glowL = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114));\\n' +
            '  totalEmissiveRadiance += diffuseColor.rgb * (0.06 + 0.30 * smoothstep(0.65, 0.95, glowL));');
      };
      m.customProgramCacheKey = () => 'dragon-front-texture';
    }
    m.needsUpdate = true;
    o.material = m;
    texturedMeshes.push(o);
  });
}

// If the blended shader ever fails to compile, fall back to the painted colours instead of a broken dragon.
renderer.debug.onShaderError = () => {
  console.error('texture shader failed - using painted colours');
  for (const o of texturedMeshes) o.material = o.userData.paletteMaterial;
  texturedMeshes = [];
};

new GLTFLoader().load(MODEL_URL, (gltf) => {
  const model = gltf.scene;
  scene.add(model);

  // Auto-fit the camera to the model, whatever its size.
  const box = new THREE.Box3().setFromObject(model);
  try { paintDragon(model, box); } catch (e) { console.error("paint failed", e); }
  try { setupLegs(model); } catch (e) { console.error("legs setup failed", e); }
  new THREE.TextureLoader().load(MODEL_URL.replace(/[^/]*$/, 'dragon_texture.png'),
    (tex) => { try { applyTexture(model, tex); } catch (e) { console.error('texture failed', e); } },
    undefined, () => console.log('no dragon_texture.png next to the model: using painted colours'));
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const dist = Math.max(size.y, size.x) * 2.6;
  camera.position.set(center.x, center.y, center.z + dist);
  camera.lookAt(center);

  // Wrap the model in a pivot at its feet so we can move/turn/squash it
  // without fighting the clip that is stored inside the GLB.
  pivot = new THREE.Group();
  pivot.position.set(center.x, box.min.y, center.z);
  scene.add(pivot);
  pivot.add(model);
  model.position.sub(pivot.position);
  baseHeight = size.y;
  baseY = box.min.y;

  if (gltf.animations.length) {
    mixer = new THREE.AnimationMixer(model);
    for (const clip of gltf.animations) {
      actions[clip.name.toLowerCase()] = mixer.clipAction(clip);
    }
    window.setState("idle");
  }
}, undefined, (err) => console.error("GLB load failed", err));

let wantedState = "idle";
let activity = 'wander';       // wander | fly | sleep | sit   (set by the dragon's brain)
let mood = 'happy';            // happy | excited | curious | bored | sad | sleepy
const walkName = () => Object.keys(actions).find(n => n.includes("walk"));
function play(next) {
  if (!next || next === current) return;
  next.reset().play();
  if (current) current.crossFadeTo(next, 0.3, false);
  current = next;
}
window.setState = (state) => {
  wantedState = state;
  if (!mixer) return;
  if (walkDir !== 0 && walkName()) return;          // keep walking clip while walking
  const names = Object.keys(actions);
  const key = names.find(n => n.includes(state)) ||
              names.find(n => n.includes("idle"));
  if (key) { play(actions[key]); return; }
  // No matching or idle clip (e.g. a model that only has "walk"):
  // stop the clip so the dragon stands in its normal rest pose.
  if (current) { current.fadeOut(0.3); current = null; }
};

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

let walkDir = 0;
// ---- legs begin: fake leg walking + wing flapping for models with no skeleton ----
// Moves the mesh vertices directly: legs swing from the hips, wings flap from the shoulders.
const HIP = 0.27;            // hip height as a fraction of model height
const LEG_SWING = 0.55;      // leg swing (radians)
const LEG_LIFT = 0.035;      // how high a stepping foot lifts (fraction of height)
const WING_ROOT = 0.45;      // where the wings start, as a fraction of the half-width
const WING_Y = 0.48;         // height of the wing joint, fraction of model height
const WING_LO = 0.40;        // wings are only found between these heights (fractions)
const WING_HI = 0.66;
const WING_FLAP = 0.6;       // flap angle (radians)
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
let legMeshes = [];
let legAmp = 0, flapAmp = 0, bodyDirty = false;

function setupLegs(model) {
  legMeshes = [];
  model.traverse((o) => {
    if (!o.isMesh || o.isSkinnedMesh || !o.geometry.attributes.position) return;
    const geo = o.geometry;
    geo.computeBoundingBox();
    const b = geo.boundingBox;
    const size = new THREE.Vector3(); b.getSize(size);
    const pos = geo.attributes.position;
    const orig = pos.array.slice();
    const n = pos.count;
    const cx = (b.min.x + b.max.x) / 2;
    const zc = (b.min.z + b.max.z) / 2;
    const wL = new Float32Array(n), wR = new Float32Array(n);
    const wWL = new Float32Array(n), wWR = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const nx = (orig[i * 3] - cx) / (size.x / 2);
      const ny = (orig[i * 3 + 1] - b.min.y) / size.y;
      const down = 1 - smooth(HIP - 0.14, HIP, ny);      // 1 at the feet, 0 above the hips
      wL[i] = down * smooth(0.04, 0.16, -nx);
      wR[i] = down * smooth(0.04, 0.16, nx);
      const wing = smooth(WING_ROOT, WING_ROOT + 0.25, Math.abs(nx))
                 * smooth(WING_LO, WING_LO + 0.06, ny) * (1 - smooth(WING_HI, WING_HI + 0.08, ny));
      wWL[i] = nx < 0 ? wing : 0;
      wWR[i] = nx > 0 ? wing : 0;
    }
    legMeshes.push({ pos, orig, wL, wR, wWL, wWR, cx, halfW: size.x / 2,
                     hipY: b.min.y + size.y * HIP, wingY: b.min.y + size.y * WING_Y, zc, h: size.y });
  });
}

function updateLegs(dt, time) {
  const legTarget = (walkDir !== 0 && !walkName()) ? 1 : (activity === 'fly' ? 0.25 : 0);
  const flapTarget = activity === 'fly' ? 1 : (beh.name === 'hop' ? 0.7 : 0);
  legAmp += (legTarget - legAmp) * Math.min(1, dt * 8);
  flapAmp += (flapTarget - flapAmp) * Math.min(1, dt * 8);
  if (legAmp < 0.002 && flapAmp < 0.002) {
    if (bodyDirty) {
      for (const m of legMeshes) { m.pos.array.set(m.orig); m.pos.needsUpdate = true; }
      bodyDirty = false;
    }
    return;
  }
  bodyDirty = true;
  const ph = time * 7;
  const aL = Math.sin(ph) * LEG_SWING * legAmp;
  const aR = -aL;
  const liftL = Math.max(0, Math.cos(ph)) * legAmp;
  const liftR = Math.max(0, -Math.cos(ph)) * legAmp;
  const flap = Math.sin(time * 20) * WING_FLAP * flapAmp;
  for (const m of legMeshes) {
    const out = m.pos.array, o = m.orig, n = m.pos.count;
    for (let i = 0; i < n; i++) {
      const wl = m.wL[i], wr = m.wR[i];
      const x = o[i * 3], y = o[i * 3 + 1], z = o[i * 3 + 2];
      if (wl + wr >= 0.001) {                               // a leg vertex
        const a = wl * aL + wr * aR;
        const lift = (wl * liftL + wr * liftR) * LEG_LIFT * m.h;
        const dy = y - m.hipY, dz = z - m.zc;
        const c = Math.cos(a), s = Math.sin(a);
        out[i * 3] = x;
        out[i * 3 + 1] = m.hipY + dy * c - dz * s + lift;
        out[i * 3 + 2] = m.zc + dy * s + dz * c;
        continue;
      }
      const ww = Math.max(m.wWL[i], m.wWR[i]);
      if (ww >= 0.001 && flapAmp >= 0.002) {                // a wing vertex
        const side = m.wWL[i] > m.wWR[i] ? -1 : 1;
        const a = side * flap * ww;
        const px = m.cx + side * WING_ROOT * m.halfW, py = m.wingY;
        const dx = x - px, dy = y - py;
        const c = Math.cos(a), s = Math.sin(a);
        out[i * 3] = px + dx * c - dy * s;
        out[i * 3 + 1] = py + dx * s + dy * c;
        out[i * 3 + 2] = z;
        continue;
      }
      out[i * 3] = x; out[i * 3 + 1] = y; out[i * 3 + 2] = z;
    }
    m.pos.needsUpdate = true;
  }
}
// ---- legs end ----

// ---- Autonomous behaviour: the dragon does things on its own ----                                   // -1 left, 0 still, 1 right
window.setActivity = (a) => { activity = a; };
window.setMood = (m) => { mood = m; };
window.setWalk = (d) => {
  walkDir = d;
  if (!mixer) return;
  const w = walkName();
  if (d !== 0 && w) play(actions[w]);               // real leg animation, if the GLB has one
  else window.setState(wantedState);
};
let beh = { name: 'idle', t: 0, dur: 2, dir: 1 };
const fxEl = document.getElementById('fx');
let fxKey = '';
function setFx(t) { if (t !== fxKey) { fxKey = t; fxEl.textContent = t; } }
let yaw = 0;
// cursor awareness (sent from Python ten times a second)
let curX = 0, curY = 0, curNear = false, curHover = false, hoverPrev = false;
let lookYaw = 0, lookPitch = 0;
window.setCursor = (x, y, near, hover) => { curX = x; curY = y; curNear = near; curHover = hover; };

function nextBehavior() {
  const dir = Math.random() < 0.5 ? -1 : 1;
  // the mood decides how lively it is: [idle, look, hop, wiggle]
  let w = [0.35, 0.25, 0.20, 0.20];
  if (mood === 'excited') w = [0.15, 0.15, 0.40, 0.30];
  else if (mood === 'sad' || mood === 'bored' || mood === 'sleepy') w = [0.70, 0.25, 0.00, 0.05];
  else if (mood === 'curious') w = [0.20, 0.60, 0.10, 0.10];
  let r = Math.random(), k = 0;
  while (k < 3 && r > w[k]) { r -= w[k]; k++; }
  const names = ['idle', 'look', 'hop', 'wiggle'];
  const durs = [2 + Math.random() * 3, 2.5, 0.7, 1.4];
  beh = { name: names[k], t: 0, dur: durs[k], dir };
}

function animateBehavior(dt, time) {
  if (!pivot) return;
  if (wantedState !== 'idle' || activity !== 'wander' || walkDir !== 0) beh = { name: 'idle', t: 0, dur: 1, dir: 1 };  // no random moves while busy/asleep/flying/walking
  // cursor just landed on the dragon: a happy wiggle
  if (curHover && !hoverPrev && activity === 'wander' && wantedState === 'idle') {
    beh = { name: 'wiggle', t: 0, dur: 1.4, dir: 1 };
  }
  hoverPrev = curHover;
  beh.t += dt;
  if (beh.t >= beh.dur) nextBehavior();
  const p = Math.min(1, beh.t / beh.dur);
  let y = 0, sy = 1, sxz = 1, yawOff = 0, roll = 0;

  const breath = Math.sin(time * 2.0) * 0.012;      // always breathing
  sy += breath; sxz -= breath * 0.5;

  if (beh.name === 'look')   yawOff = Math.sin(Math.PI * p) * 0.6 * beh.dir;
  if (beh.name === 'hop')  { y = Math.sin(Math.PI * p) * 0.12 * baseHeight;
                             sy += Math.sin(Math.PI * p) * 0.05; }
  if (beh.name === 'wiggle') { roll = Math.sin(p * Math.PI * 6) * 0.12 * (1 - p);
                               yawOff = Math.sin(p * Math.PI * 4) * 0.25 * (1 - p); }

  // reactions to what the assistant is doing
  if (wantedState === 'listening') {            // attentive: head tilted, a little taller
    roll += 0.07; sy += 0.03;
  } else if (wantedState === 'thinking') {      // slow thoughtful sway
    roll += Math.sin(time * 1.5) * 0.08;
    yawOff += Math.sin(time * 0.8) * 0.2;
  } else if (wantedState === 'talking') {       // lively bounce while speaking
    y += Math.abs(Math.sin(time * 8)) * 0.025 * baseHeight;
    sy += Math.sin(time * 12) * 0.02;
    roll += Math.sin(time * 4) * 0.04;
  }

  // walking: turn toward the direction of travel, with a little step bounce
  yaw += (walkDir * 1.0 - yaw) * Math.min(1, dt * 6);
  if (walkDir !== 0 && !walkName()) {                // fake bounce only when no walk clip
    y += Math.abs(Math.sin(time * 9)) * 0.03 * baseHeight;
    roll += Math.sin(time * 9) * 0.05;
  }

  // body language for what it is doing and how it feels
  let pitch = 0, lift = 0;
  if (activity === 'sleep') {                       // dozing: head down, slow deep breathing
    pitch += 0.32 + Math.sin(time) * 0.02; sy += Math.sin(time * 1.1) * 0.02 - 0.08; sxz += 0.03;
  } else if (activity === 'fly') {                  // hovering with a gentle bob
    lift = (0.10 + Math.sin(time * 2.2) * 0.03) * baseHeight; pitch += 0.12;
  } else if (activity === 'sit') {                  // resting in place
    pitch += 0.15; sy -= 0.03;
  }
  if (mood === 'sad') { pitch += 0.12; sy -= 0.02; }
  else if (mood === 'sleepy' && activity !== 'sleep') pitch += 0.08;
  else if (mood === 'curious') roll += Math.sin(time * 1.2) * 0.06;
  // look toward the mouse when it is near (not while asleep or walking)
  const canLook = activity !== 'sleep' && walkDir === 0 && curNear;
  lookYaw += ((canLook ? curX * 0.7 : 0) - lookYaw) * Math.min(1, dt * 5);
  lookPitch += ((canLook ? curY * 0.08 : 0) - lookPitch) * Math.min(1, dt * 5);
  yawOff += lookYaw; pitch += lookPitch;
  if (canLook) roll += Math.sin(time * 1.2) * 0.03;      // a little curious head tilt
  setFx(activity === 'sleep' ? '\\u{1F4A4}' : mood === 'sad' ? '\\u{1F4A7}' :
        mood === 'excited' ? '\\u2728' : mood === 'bored' ? '\\u{1F4AD}' : '');

  pivot.position.y = baseY + y + lift;
  pivot.rotation.set(pitch, yaw + yawOff, roll);
  pivot.scale.set(sxz, sy, sxz);
  updateLegs(dt, time);
}

// Save battery: draw at 30 frames a second, and not at all while the dragon is hidden.
let paused = false, acc = 0;
const FRAME = 1 / 30;
window.setPaused = (p) => { paused = p; acc = 0; if (!p) clock.getDelta(); };
renderer.setAnimationLoop(() => {
  if (paused) return;
  acc += clock.getDelta();
  if (acc < FRAME - 0.004) return;          // small tolerance so 60 Hz screens really get 30 fps
  const dt = Math.min(acc, 0.1);
  acc = 0;
  if (mixer) mixer.update(dt);
  animateBehavior(dt, clock.elapsedTime);
  renderer.render(scene, camera);
});
</script>
</body></html>
"""


def start_file_server(directory):
    """Serve the project folder on localhost so the page can load the GLB."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=directory)
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class HotkeyListener(QObject):
    """Listens for global hotkeys on Windows (no extra packages) and emits triggered(id)."""
    triggered = Signal(int)

    def __init__(self):
        super().__init__()
        self._thread_id = None

    def start(self, bindings):
        if sys.platform == "win32":
            threading.Thread(target=self._run, args=(bindings,), daemon=True).start()

    def _run(self, bindings):
        try:
            self._listen(bindings)
        except Exception:
            import traceback
            print("Hotkey listener crashed:")
            traceback.print_exc()

    def _listen(self, bindings):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        registered = []
        for hid, (mods, vk) in bindings.items():
            if user32.RegisterHotKey(None, hid, mods | 0x4000, vk):      # 0x4000 = no key repeat
                registered.append(hid)
            else:
                print("Hotkey %d could not be registered (error %d). Another program may use it."
                      % (hid, kernel32.GetLastError()))
        print("Hotkeys listening (ids): %s   [1 = show, 2 = hide]" % registered)
        msg = wintypes.MSG()
        while True:
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got <= 0:
                print("Hotkey listener stopped (GetMessage returned %d)." % got)
                break
            if msg.message == 0x0312:                                    # WM_HOTKEY
                print("Hotkey pressed: id %d" % int(msg.wParam))
                self.triggered.emit(int(msg.wParam))
        for hid in registered:
            user32.UnregisterHotKey(None, hid)

    def stop(self):
        if sys.platform == "win32" and self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)   # WM_QUIT


class DragonWindow(QMainWindow):
    # Emit from any thread: win.state_requested.emit("talking")
    state_requested = Signal(str)
    talk_requested = Signal()          # emitted when you double-click the dragon (voice question)
    say_requested = Signal(str)        # an answer to show in the speech bubble (any thread)
    text_submitted = Signal(str)       # a question typed into the text box

    def __init__(self, glb_path):
        super().__init__()
        glb_path = os.path.abspath(glb_path)
        if not os.path.isfile(glb_path):
            raise FileNotFoundError(glb_path)

        # Serve the GLB's folder; the page fetches the file by name.
        folder = os.path.dirname(glb_path)
        self._server = start_file_server(folder)
        port = self._server.server_address[1]
        model_url = "http://127.0.0.1:%d/%s" % (port, os.path.basename(glb_path))

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(*WINDOW_SIZE)

        self.view = QWebEngineView(self)
        self.view.setAttribute(Qt.WA_TranslucentBackground, True)
        self.view.setStyleSheet("background: transparent;")
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.setCentralWidget(self.view)

        # Use the local copy of three.js when get_three.py has been run (works offline), else the internet copy.
        vendor = os.path.join(folder, "vendor")
        if (os.path.isfile(os.path.join(vendor, "three.module.js"))
                and os.path.isfile(os.path.join(vendor, "addons", "loaders", "GLTFLoader.js"))
                and os.path.isfile(os.path.join(vendor, "addons", "utils", "BufferGeometryUtils.js"))):
            three_url, addons_url = "/vendor/three.module.js", "/vendor/addons/"
            print("3D engine: using the local copy (works offline).")
        else:
            three_url = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
            addons_url = "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
            print("3D engine: using the internet copy. For offline use, run get_three.py once.")
        html = (HTML.replace("__THREE_URL__", three_url).replace("__ADDONS_URL__", addons_url)
                .replace("__MODEL_URL__", model_url))
        self.view.setHtml(html, QUrl("http://127.0.0.1:%d/" % port))

        self.state_requested.connect(self.set_state)

        # The web view's inner widget gets the mouse events, so listen there.
        self._drag_offset = None
        self.view.focusProxy().installEventFilter(self)

        # Wander along the screen on its own (toggle in the right-click menu).
        self._state = "idle"
        self._wander = True
        self._walk_target = None
        self._walk_dir = 0
        self._next_walk_at = time.monotonic() + 5
        self._js_ready = False          # becomes True once the page has finished loading
        self._brain = DragonBrain()     # moods, needs, and what the dragon decides to do
        self._activity = "wander"
        self._ground_y = None
        self._fly_target = None
        self._brain_timer = QTimer(self)
        self._brain_timer.timeout.connect(self._brain_tick)
        self._brain_timer.start(1000)
        self._prefs = dragon_settings.load_prefs()      # saved by the Settings panel
        self._cfg = self._prefs                         # cursor_look / cursor_chase are read from here
        self._settings_dlg = None
        self._chasing = False
        self._hover_secs = 0.0
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._cursor_tick)
        self._cursor_timer.start(100)
        self.talk_requested.connect(self._on_talk)
        self._bubble = None
        self._typebox = None
        self.say_requested.connect(self.show_bubble)

        # Tray icon: hide the dragon and bring it back without any terminal.
        QApplication.instance().setQuitOnLastWindowClosed(False)   # hiding must not end the program
        self._autoquit = QTimer(self)
        self._autoquit.setSingleShot(True)
        self._autoquit.timeout.connect(lambda: self._quit())
        self._told_about_tray = False
        self._tray = None
        self._setup_tray()
        self._hotkeys = HotkeyListener()
        self._hotkeys.triggered.connect(self._on_hotkey)
        self._hotkeys.start({1: HOTKEY_SHOW, 2: HOTKEY_HIDE})
        self.view.loadFinished.connect(self._on_loaded)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._wander_tick)
        self._tick.start(33)

    def _on_loaded(self, ok):
        self._js_ready = bool(ok)
        self._next_walk_at = time.monotonic() + 5
        self._apply_events([("activity", self._brain.activity), ("mood", self._brain.mood)])

    # ---------------- tray icon: show / hide / quit ----------------
    def _make_tray_icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f3e3c3"))                                   # horns
        p.drawEllipse(8, 4, 14, 20)
        p.drawEllipse(42, 4, 14, 20)
        p.setBrush(QColor("#7b3fc4"))                                   # head
        p.drawEllipse(6, 12, 52, 48)
        p.setBrush(QColor("#ffffff"))                                   # eyes
        p.drawEllipse(16, 26, 14, 14)
        p.drawEllipse(34, 26, 14, 14)
        p.setBrush(QColor("#2e8b3a"))
        p.drawEllipse(20, 29, 8, 8)
        p.drawEllipse(38, 29, 8, 8)
        p.setBrush(QColor("#1a1a1a"))
        p.drawEllipse(22, 31, 4, 4)
        p.drawEllipse(40, 31, 4, 4)
        p.end()
        return QIcon(pm)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self._tray.setToolTip("Baby Dragon - click to show/hide. Ctrl+Alt+A show, Ctrl+Alt+C hide")
        menu = QMenu()
        menu.addAction("Show dragon", lambda: self.show_dragon())
        menu.addAction("Hide dragon", lambda: self.hide_dragon())
        menu.addAction("Talk to dragon", lambda: self.talk_requested.emit())
        menu.addAction("Type to dragon...", lambda: self.open_typebox())
        menu.addAction("Settings...", lambda: self.open_settings())
        menu.addSeparator()
        menu.addAction("Quit", lambda: self._quit())
        self._tray_menu = menu                       # keep a reference so it is not garbage collected
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_click)
        self._tray.show()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:      # a single left click toggles
            if self.isVisible():
                self.hide_dragon()
            else:
                self.show_dragon()

    def _on_hotkey(self, hotkey_id):
        print("Hotkey %d reached the dragon window (visible=%s)" % (hotkey_id, self.isVisible()))
        if hotkey_id == 1:
            self.show_dragon()
        elif hotkey_id == 2:
            self.hide_dragon(force=True)             # the hotkey can always bring it back

    def hide_dragon(self, force=False):
        if self._tray is None and not force:         # no tray: only hide if a hotkey can bring it back
            return
        self._close_popups()
        self.hide()
        self._set_sleeping_app(True)
        if AUTO_QUIT_MINUTES > 0:
            self._autoquit.start(int(AUTO_QUIT_MINUTES * 60 * 1000))
        if self._tray is not None and not self._told_about_tray:
            self._told_about_tray = True
            self._tray.showMessage("Baby Dragon", "I'm hiding. Click my tray icon, or press Ctrl+Alt+A, to bring me back.",
                                   QSystemTrayIcon.MessageIcon.Information, 4000)

    def show_dragon(self):
        self.show()
        self.raise_()
        self._autoquit.stop()
        self._set_sleeping_app(False)

    def _set_sleeping_app(self, hidden):
        """While hidden: stop the 3D drawing and all timers so it uses almost no battery."""
        for timer in (self._tick, self._brain_timer, self._cursor_timer):
            if hidden:
                timer.stop()
            else:
                timer.start()
        self._js("window.setPaused && window.setPaused(%s)" % ("true" if hidden else "false"))

    def _quit(self):
        self._close_popups()
        self._hotkeys.stop()
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    def _on_talk(self):
        if not self.isVisible():                     # talking to it brings it back
            self.show_dragon()
        self._interact("talk")

    def _js(self, code):
        self.view.page().runJavaScript(code)

    def _apply_events(self, events):
        for ev in events:
            if ev[0] == "activity":
                self._activity = ev[1]
                self._fly_target = None
                if ev[1] != "wander" and self._walk_target is not None:
                    self._stop_walk()
                self._js("window.setActivity && window.setActivity(%s)" % json.dumps(ev[1]))
            elif ev[0] == "mood":
                self._js("window.setMood && window.setMood(%s)" % json.dumps(ev[1]))
            # ("say", ...) is reserved for the dragon starting a conversation (next step)

    def _cursor_tick(self):
        if not self._js_ready or not self.isVisible():
            return
        look = bool(self._cfg.get("cursor_look", True))
        pos = QCursor.pos()
        c = self.frameGeometry().center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        near = look and (dx * dx + dy * dy) ** 0.5 < 450
        hover = look and self._drag_offset is None and self.frameGeometry().contains(pos)
        if hover:
            self._hover_secs += 0.1
            if self._hover_secs >= 4.0:            # resting the mouse on it counts as attention
                self._hover_secs = 0.0
                self._apply_events(self._brain.on_interaction("hover"))
        else:
            self._hover_secs = 0.0
        self._js("window.setCursor && window.setCursor(%.3f,%.3f,%s,%s)" % (
            max(-1.0, min(1.0, dx / 300.0)), max(-1.0, min(1.0, dy / 300.0)),
            "true" if near else "false", "true" if hover else "false"))

    def _brain_tick(self):
        if self._js_ready and self.isVisible():
            self._apply_events(self._brain.tick(1.0, busy=(self._state != "idle")))

    def show_bubble(self, text):
        """Shows an answer as text next to the dragon (if the settings say so)."""
        if not text or not self.isVisible():
            return
        if not dragon_settings.answer_bubble(self._prefs):
            return
        if self._bubble is None:
            self._bubble = dragon_bubble.BubbleWindow(lambda: self.frameGeometry())
        self._bubble.show_text(text)

    def open_typebox(self):
        if not self.isVisible():
            self.show_dragon()
        if self._typebox is None:
            self._typebox = dragon_bubble.TypeBox(lambda: self.frameGeometry(), self._on_typed)
        self._typebox.open()

    def _on_typed(self, text):
        text = text.strip()
        if text:
            self._interact("talk")
            self.text_submitted.emit(text)

    def _ask(self):
        """Double-click: Type mode opens the text box, otherwise the dragon listens."""
        if self._prefs.get("mode") == "type":
            self.open_typebox()
        else:
            self.talk_requested.emit()

    def _close_popups(self):
        for w in (self._bubble, self._typebox):
            if w is not None:
                w.hide()

    def open_settings(self):
        if self._settings_dlg is None:
            self._settings_dlg = dragon_settings.make_dialog(dict(self._prefs), self._on_prefs_changed)
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _on_prefs_changed(self, new_prefs):
        self._prefs.update(new_prefs)               # same dict object as self._cfg, so it applies at once
        dragon_settings.save_prefs(self._prefs)
        if not self._prefs.get("cursor_chase") and self._chasing:
            self._chasing = False
            self._stop_walk()

    def _interact(self, kind):
        self._apply_events(self._brain.on_interaction(kind))

    def _fly_step(self, geo):
        if self._fly_target is None:
            tx = random.randint(geo.left(), max(geo.left(), geo.right() - self.width()))
            ty = max(geo.top(), self._ground_y - random.randint(150, 320))
            self._fly_target = (tx, ty)
        tx, ty = self._fly_target
        dx, dy = tx - self.x(), ty - self.y()
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 6:
            self._fly_target = None
            return
        step = min(3.0, dist)
        self.move(round(self.x() + dx / dist * step), round(self.y() + dy / dist * step))

    def _land(self):
        dy = self._ground_y - self.y()
        self.move(self.x(), self.y() + max(-4, min(4, dy)))

    def _stop_walk(self):
        self._walk_target = None
        self._walk_dir = 0
        self.view.page().runJavaScript("window.setWalk && window.setWalk(0)")
        self._next_walk_at = time.monotonic() + random.uniform(6, 16)

    def _wander_tick(self):
        if self._drag_offset is not None or not self._js_ready or not self.isVisible():
            return
        if self._ground_y is None:
            self._ground_y = self.y()
        geo = self.screen().availableGeometry()
        if self._activity == "fly":                 # floating around up in the air
            self._fly_step(geo)
            return
        if self.y() != self._ground_y:              # coming back down after a flight
            self._land()
            return
        chase = (bool(self._cfg.get("cursor_chase", False)) and self._wander
                 and self._activity == "wander" and self._state == "idle")
        if chase:                                   # optional: follow the mouse along the screen
            gap = QCursor.pos().x() - self.width() // 2 - self.x()
            if abs(gap) > 50:
                d = 1 if gap > 0 else -1
                if not self._chasing or d != self._walk_dir:
                    self._chasing = True
                    self._walk_target = None
                    self._walk_dir = d
                    self._js("window.setWalk && window.setWalk(%d)" % d)
                self.move(self.x() + 3 * d, self.y())
            elif self._chasing:                     # caught up: stand next to the cursor
                self._chasing = False
                self._stop_walk()
            return
        if self._chasing:                           # chase was switched off mid-run
            self._chasing = False
            self._stop_walk()
        if not self._wander or self._state != "idle" or self._activity != "wander":
            if self._walk_target is not None:
                self._stop_walk()
            return
        now = time.monotonic()
        if self._walk_target is None:
            if now < self._next_walk_at:
                return
            geo = self.screen().availableGeometry()
            target = random.randint(geo.left(), geo.right() - self.width())
            if abs(target - self.x()) < 120:        # too short a trip, try later
                self._next_walk_at = now + 2
                return
            self._walk_target = target
            self._walk_dir = 1 if target > self.x() else -1
            self.view.page().runJavaScript("window.setWalk && window.setWalk(%d)" % self._walk_dir)
            return
        new_x = self.x() + 2 * self._walk_dir
        if (self._walk_dir > 0 and new_x >= self._walk_target) or \
           (self._walk_dir < 0 and new_x <= self._walk_target):
            self._stop_walk()
            return
        self.move(new_x, self.y())

    def _set_wander(self, on):
        self._wander = on

    def set_state(self, state):
        self._state = state
        self.view.page().runJavaScript("window.setState && window.setState(%s)" % json.dumps(state))

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._interact("touch")
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            return True
        if t == QEvent.MouseMove and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            return True
        if t == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self._drag_offset = None
            self._ask()
            return True
        if t == QEvent.MouseButtonRelease:
            if self._drag_offset is not None and self._activity != "fly":
                self._ground_y = self.y()
            self._drag_offset = None
            return False
        if t == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            return True
        return super().eventFilter(obj, event)

    def _show_menu(self, pos):
        menu = QMenu(self)
        for s in STATES:
            menu.addAction(s.capitalize(), lambda s=s: self.set_state(s))
        menu.addSeparator()
        tryit = menu.addMenu("Try (test)")
        for label, act in [("Wander", "wander"), ("Fly", "fly"), ("Sleep", "sleep"), ("Rest (sit)", "sit")]:
            tryit.addAction(label, lambda a=act: self._apply_events(self._brain.force_activity(a)))
        tryit.addSeparator()
        for mood in ["happy", "excited", "curious", "bored", "sad", "sleepy"]:
            tryit.addAction("Feel " + mood, lambda m=mood: self._apply_events(self._brain.force_mood(m)))
        sizes = menu.addMenu("Size")
        for label, w, h in [("Tiny", 120, 140), ("Small", 170, 200),
                            ("Medium", 260, 305), ("Large", 360, 420)]:
            sizes.addAction(label, lambda w=w, h=h: self.resize(w, h))
        menu.addAction("Talk to dragon (voice)", lambda: self.talk_requested.emit())
        menu.addAction("Type to dragon...", lambda: self.open_typebox())
        menu.addAction("Settings...", lambda: self.open_settings())
        wander = menu.addAction("Wander around")
        wander.setCheckable(True)
        wander.setChecked(self._wander)
        wander.triggered.connect(self._set_wander)
        if self._tray is not None:
            menu.addAction("Hide to tray", lambda: self.hide_dragon())
        menu.addAction("Quit", lambda: self._quit())
        menu.exec(pos)


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python dragon_window.py path/to/dragon.glb")
    app = QApplication(sys.argv)
    win = DragonWindow(sys.argv[1])
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
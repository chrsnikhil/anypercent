"""
3D viewer for the P2S panel projects: reads each .3mf (its parts, which filament each part
uses and the filament colours) and writes one self-contained HTML page next to them.

  python make_panel_viewer.py "<folder with the .3mf files>"
"""
import base64
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


def read(path):
    with zipfile.ZipFile(path) as z:
        colours = json.loads(z.read("Metadata/project_settings.config"))["filament_colour"]
        ms = ET.fromstring(z.read("Metadata/model_settings.config"))
        mesh_root = ET.fromstring(z.read("3D/Objects/object_1.model"))
        comps = ET.fromstring(z.read("3D/3dmodel.model"))
    obj = ms.find("object")
    parts = []
    comp_list = comps.findall(".//m:component", NS)
    for part, comp in zip(obj.findall("part"), comp_list):
        meta = {m.get("key"): m.get("value") for m in part.findall("metadata")}
        o = mesh_root.find(f".//m:object[@id='{comp.get('objectid')}']", NS)
        v = np.array([[float(e.get(a)) for a in "xyz"] for e in o.iterfind(".//m:vertex", NS)], np.float32)
        t = np.array([[int(e.get(a)) for a in ("v1", "v2", "v3")] for e in o.iterfind(".//m:triangle", NS)], np.uint32)
        tr = [float(x) for x in comp.get("transform").split()]
        v += np.array(tr[9:12], np.float32)                       # component offset (rotation is identity)
        parts.append({"name": meta.get("name", ""), "colour": colours[int(meta.get("extruder", "1")) - 1],
                      "v": base64.b64encode(v[t].reshape(-1).astype(np.float32).tobytes()).decode()})
    return {"file": os.path.basename(path), "name": obj.find("metadata[@key='name']").get("value"),
            "colours": colours, "parts": parts}


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Any% P2S Panels</title>
<style>
:root{--bg:#f4f1ea;--fg:#1b1f2a;--muted:#6b6f7a;--card:#fffdf8;--line:#e2ddd2}
@media (prefers-color-scheme:dark){:root{--bg:#15171c;--fg:#eceae4;--muted:#9a9ca3;--card:#1e2128;--line:#2c3039}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,Segoe UI,sans-serif}
header{padding:18px 20px 6px}h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:var(--muted)}
#grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px;padding:14px 20px 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card canvas{display:block;width:100%;height:340px;cursor:grab}
.info{padding:10px 14px 12px;border-top:1px solid var(--line)}.info b{font-size:15px}
.file{color:var(--muted);font-size:12px;word-break:break-all}
.sw{display:flex;gap:14px;margin-top:6px;flex-wrap:wrap}.sw span{display:flex;align-items:center;gap:6px;font-size:13px}
.sw i{width:16px;height:16px;border-radius:4px;border:1px solid var(--line);display:inline-block}
@media (max-width:480px){#grid{grid-template-columns:1fr;padding:12px 16px}}
</style></head><body>
<header><h1>Any% rear panels, Bambu Lab P2S</h1>
<p>Geometry and colours read from the .3mf files. Drag to orbit, scroll to zoom, double-click to reset.</p></header>
<div id="grid"></div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const DATA = __DATA__;
const f32 = b64 => { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return new Float32Array(u.buffer); };
for (const p of DATA) {
  const card = document.createElement('div'); card.className = 'card';
  const cv = document.createElement('canvas'); card.appendChild(cv);
  const info = document.createElement('div'); info.className = 'info';
  info.innerHTML = `<b>${p.name.replace('anypercent_panel_', '').replace(/^./, c => c.toUpperCase())} panel</b>
    <div class="file">${p.file}</div><div class="sw">${p.parts.map((q, i) =>
    `<span><i style="background:${q.colour}"></i>AMS ${i + 1}: ${q.name} ${q.colour}</span>`).join('')}</div>`;
  card.appendChild(info); document.getElementById('grid').appendChild(card);

  const r = new THREE.WebGLRenderer({canvas: cv, antialias: true, alpha: true});
  r.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a8a, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.position.set(-120, -160, 260); scene.add(sun);
  const group = new THREE.Group();
  for (const q of p.parts) {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(f32(q.v), 3));
    g.computeVertexNormals();
    group.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({color: q.colour, roughness: 0.55, metalness: 0})));
  }
  const box = new THREE.Box3().setFromObject(group), c = box.getCenter(new THREE.Vector3());
  group.position.sub(c); scene.add(group);
  const cam = new THREE.PerspectiveCamera(35, 1, 1, 3000); cam.up.set(0, 0, 1);
  const home = () => { cam.position.set(0, -210, 260); ctl.target.set(0, 0, 0); ctl.update(); };
  const ctl = new OrbitControls(cam, cv); ctl.enableDamping = true; home();
  cv.addEventListener('dblclick', home);
  const size = () => { const w = cv.clientWidth, h = cv.clientHeight; r.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); };
  new ResizeObserver(size).observe(cv); size();
  r.setAnimationLoop(() => { ctl.update(); r.render(scene, cam); });
}
</script></body></html>
"""


def main():
    folder = sys.argv[1]
    data = [read(p) for p in sorted(glob.glob(os.path.join(folder, "*.3mf")))]
    out = os.path.join(folder, "view_panels_in_3d.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(PAGE.replace("__DATA__", json.dumps(data)))
    for d in data:
        print(f"  {d['name']}: " + ", ".join(f"{q['name']} {q['colour']}" for q in d["parts"]))
    print(out, f"{os.path.getsize(out) / 1048576:.1f} MB")


if __name__ == "__main__":
    main()

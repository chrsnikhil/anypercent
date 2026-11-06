import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import React, { useMemo } from "react";
import { staticFile } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { CameraAt, H, Post, W } from "../../acts/common";
import { applyPose, buildParts, clip, partPose, section } from "../../three/consoleModel";
import { useBuffer } from "../../three/useAsset";
import TL from "../../timeline.json";

/* The console in coloured CAD, assembled, face down, with the Hedera swap plate on its back: black body, white logo.
   The film's meshes carry only the two ETHGlobal plates, so those are hidden and the printed Hedera plate's own STLs
   (prep/sponsors/hedera.py: cad2/stl_extra, moved to the plates' seat) go in their place. A CAD render, labelled so. */

export type PlateAssets = { console: ArrayBuffer; body: ArrayBuffer; logo: ArrayBuffer };

/** Loaded in the act itself (before any canvas mounts): @remotion/three does not redraw for late assets. */
export const usePlateAssets = (): PlateAssets | null => {
  const c = useBuffer(staticFile("console.bin"));
  const b = useBuffer(staticFile("sponsors/hedera/plate_body.stl"));
  const l = useBuffer(staticFile("sponsors/hedera/plate_logo.stl"));
  return c && b && l ? { console: c, body: b, logo: l } : null;
};

const DONE = TL.shots.end[0];                                   // every part fitted
const D2R = Math.PI / 180;
const NO_SCAN = { x: -1000, amt: 0 };

/** The two views: the opener (a three-quarter look down at the plate) and the close (lower, from the other side). */
export const VIEWS = [
  { az: -24, el: 40, r: 425, target: new THREE.Vector3(101, 56, 14), fov: 30 },
  { az: 30, el: 27, r: 360, target: new THREE.Vector3(108, 58, 30), fov: 30 },
];

const edges = (g: THREE.BufferGeometry, col: string, opacity: number) => {
  const e = new THREE.EdgesGeometry(g, 28);
  const lg = new LineSegmentsGeometry();
  lg.setPositions(e.attributes.position.array as Float32Array);
  const m = new LineMaterial({ color: new THREE.Color(col), linewidth: 1.0, transparent: true, opacity, depthWrite: false, worldUnits: false });
  m.resolution.set(W, H);
  const l = new LineSegments2(lg, m);
  l.renderOrder = 3;
  return l;
};

const Scene: React.FC<{ a: PlateAssets; t: number; len: number; view: number }> = ({ a, t, len, view }) => {
  const { gl, scene } = useThree();
  useMemo(() => {                                               // the film's studio light for coloured CAD
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1.0;
  }, [gl, scene]);
  const parts = useMemo(() => buildParts(a.console), [a.console]);
  const poses = useMemo(() => parts.map((p) => partPose(p.meta, DONE)), [parts]);
  const plate = useMemo(() => {
    const ld = new STLLoader();
    const body = ld.parse(a.body), logo = ld.parse(a.logo);
    const g = new THREE.Group();
    // black satin PLA reads grey under a broad highlight: a weak, tighter specular keeps the body black
    const mk = (geo: THREE.BufferGeometry, col: string, rough: number, spec: number, env: number) => {
      const m = new THREE.MeshPhysicalMaterial({ color: new THREE.Color(col), roughness: rough, metalness: 0, specularIntensity: spec, envMapIntensity: env,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      return new THREE.Mesh(geo, m);
    };
    g.add(mk(body, "#060607", 0.36, 0.22, 0.4), mk(logo, "#e2e2df", 0.6, 0.5, 0.6));
    g.add(edges(body, "#3c4046", 0.55), edges(logo, "#9a9ea4", 0.45));
    return g;
  }, [a.body, a.logo]);
  const grid = useMemo(() => {
    const g = new THREE.GridHelper(900, 45, "#8cc8ea", "#8cc8ea");
    g.rotation.x = Math.PI / 2;
    g.position.set(101, 62.5, -4);
    const m = g.material as THREE.Material;
    m.transparent = true;
    m.opacity = 0.07;
    return g;
  }, []);
  clip.constant = 1e5;
  section.constant = 1e5;
  parts.forEach((p, i) => {
    applyPose(p, { ...poses[i], hi: 0 }, NO_SCAN, 0);
    p.group.visible = poses[i].visible && !/^panel_/.test(p.meta.name);   // the ETHGlobal plates make way for Hedera's
  });
  const v = VIEWS[view];
  const r = v.r * (1 - 0.0066 * (t / 60));                      // the locked-off push-in, linear
  const dir = new THREE.Vector3(Math.sin(v.az * D2R) * Math.cos(v.el * D2R), -Math.cos(v.az * D2R) * Math.cos(v.el * D2R), Math.sin(v.el * D2R));
  const pos = v.target.clone().add(dir.multiplyScalar(r));
  const sweep = t / len;                                         // a key light that drags a sheen across the plate
  return (
    <>
      <color attach="background" args={["#030405"]} />
      <CameraAt pos={pos} target={v.target} fov={v.fov} up={new THREE.Vector3(0, 0, 1)} />
      <ambientLight intensity={0.14} />
      <directionalLight position={[-300, -500, 600]} intensity={1.25} color="#fff3e6" />
      <directionalLight position={[500, 600, 160]} intensity={0.9} color="#7cc4ff" />
      <directionalLight position={[-400 + 900 * sweep, 200, 420]} intensity={0.7} color="#ffffff" />
      <primitive object={grid} />
      {parts.map((p) => <primitive key={p.meta.name} object={p.group} />)}
      <primitive object={plate} />
      <Post strength={0.35} radius={0.45} threshold={1.6} dof={{ focus: r, range: 170, blur: 3 }} />
    </>
  );
};

export const Plate: React.FC<{ a: PlateAssets; t: number; len: number; view: number }> = (props) => (
  <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
    <Scene {...props} />
  </ThreeCanvas>
);

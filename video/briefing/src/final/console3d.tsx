import { useThree } from "@react-three/fiber";
import { ThreeCanvas, useOffthreadVideoTexture } from "@remotion/three";
import React, { useLayoutEffect, useMemo } from "react";
import { Sequence, staticFile, useCurrentFrame } from "remotion";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { CameraAt, H, Post, W } from "../acts/common";
import { applyPose, asmMatrix, buildParts, clip, META_, partPose, section } from "../three/consoleModel";
import { useBuffer } from "../three/useAsset";
import TLJ from "../timeline.json";
import { lerp } from "../util";

/* The Any% handheld in 3D (the film's CAD, src/three/consoleModel.ts), face up, every part home, its screen playing a
   real console recording (record.py) as a video texture. The final film's through-line: each sponsor section opens on
   it, then cuts to the flat recording. */

const POSE_F = TLJ.shots.end[0];                                   // the assembly film's end shot: assembled and flipped face up
const D2R = Math.PI / 180;
const SCREEN_C = new THREE.Vector3(101, 82, 44);                    // the screen's centre after the flip (console.json screen)
const orbit = (az: number, el: number, r: number, target: THREE.Vector3) =>
  target.clone().add(new THREE.Vector3(Math.sin(az * D2R) * Math.cos(el * D2R), -Math.cos(az * D2R) * Math.cos(el * D2R), Math.sin(el * D2R)).multiplyScalar(r));

const Pool: React.FC = () => {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `varying vec2 vUv;
      void main(){ vec2 d = (vUv - 0.5) * 2.0; float r2 = dot(d, d);
        vec3 c = vec3(0.05, 0.06, 0.08) * exp(-r2 * 4.0); gl_FragColor = vec4(c, 1.0); }`,
  }), []);
  return <mesh material={mat} position={[101, 62.5, -2]}><planeGeometry args={[900, 700]} /></mesh>;
};

export type Orbit = { az: [number, number]; el: [number, number]; r: [number, number]; shift?: [number, number, number] };

const Scene: React.FC<{ cbuf: ArrayBuffer; tex: THREE.Texture; k: number; o: Orbit }> = ({ cbuf, tex, k, o }) => {
  const { gl, scene, advance } = useThree();
  useMemo(() => {
    const pm = new THREE.PMREMGenerator(gl);
    scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 0.9;
  }, [gl, scene]);
  const parts = useMemo(() => buildParts(cbuf), [cbuf]);
  const poses = useMemo(() => parts.map((p) => partPose(p.meta, POSE_F)), [parts]);
  const screen = useMemo(() => {
    const [x0, x1, y0, y1] = META_.screen.rect;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, y1 - y0), new THREE.MeshBasicMaterial({ toneMapped: false }));
    m.position.set((x0 + x1) / 2, (y0 + y1) / 2, META_.screen.glassZ - 0.35);
    m.rotation.y = Math.PI;
    m.renderOrder = 6;
    return m;
  }, []);
  const asm = useMemo(() => {
    const g = new THREE.Group();
    g.matrixAutoUpdate = false;
    parts.forEach((p) => g.add(p.group));
    g.add(screen);
    return g;
  }, [parts, screen]);
  clip.constant = 1e5;
  section.constant = 1e5;
  parts.forEach((p, i) => applyPose(p, { ...poses[i], hi: 0, heat: 0 }, { x: -1000, amt: 0 }, 0));
  asm.matrix.copy(asmMatrix(POSE_F));
  asm.matrixWorldNeedsUpdate = true;
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = screen.material as THREE.MeshBasicMaterial;
  if (mat.map !== tex) { mat.map = tex; mat.needsUpdate = true; }
  useLayoutEffect(() => { advance(performance.now()); }, [tex, advance]);   // a new screen frame: draw again
  const target = SCREEN_C.clone().add(new THREE.Vector3(...(o.shift ?? [0, 0, 0])));
  const pos = orbit(lerp(o.az[0], o.az[1], k), lerp(o.el[0], o.el[1], k), lerp(o.r[0], o.r[1], k), target);
  return (
    <>
      <color attach="background" args={["#040506"]} />
      <CameraAt pos={pos} target={target} fov={30} up={new THREE.Vector3(0, 0, 1)} />
      <ambientLight intensity={0.22} />
      <directionalLight position={[-300, -500, 600]} intensity={1.3} color="#fff3e6" />
      <directionalLight position={[500, 600, 160]} intensity={0.9} color="#7cc4ff" />
      <directionalLight position={[101, 900, 420]} intensity={0.5} color="#ffb070" />
      <primitive object={asm} />
      <Pool />
      <Post strength={0.3} radius={0.45} threshold={1.6} dof={{ focus: pos.distanceTo(SCREEN_C), range: 160, blur: 3 }} />
    </>
  );
};

const Inner: React.FC<{ src: string; cbuf: ArrayBuffer; k: number; o: Orbit }> = ({ src, cbuf, k, o }) => {
  const tex = useOffthreadVideoTexture({ src: staticFile(src) });
  if (!tex) return null;
  return (
    <ThreeCanvas width={W} height={H} gl={{ antialias: true, preserveDrawingBuffer: true }} style={{ position: "absolute", inset: 0 }}>
      <Scene cbuf={cbuf} tex={tex} k={k} o={o} />
    </ThreeCanvas>
  );
};

/** t: the shot's frame, len: its length (the orbit runs linearly across it); the screen plays `src` from `from` s. */
export const Console3D: React.FC<{ t: number; len: number; src: string; from: number; o: Orbit }> = ({ t, len, src, from, o }) => {
  const cbuf = useBuffer(staticFile("console.bin"));
  if (!cbuf) return null;
  return (
    <Sequence from={-Math.round(from * 60)} layout="none">
      <Inner src={src} cbuf={cbuf} k={Math.min(1, t / len)} o={o} />
    </Sequence>
  );
};

/* Every 3D shot the film uses, pre-rendered once as its own clip (public/final/c3d/<id>.mp4) so the full film needs no
   WebGL: the Root registers FinalC3D-<id> for each. FinalDemo plays the clips; LIVE_3D switches back to live scenes. */
export type Shot3D = { id: string; src: string; from: number; len: number; o: Orbit };
export const SHOTS_3D: Shot3D[] = [
  { id: "s4", src: "final/rec/record_book.mp4", from: 0.2, len: 240, o: { az: [-26, -14], el: [40, 46], r: [430, 360] } },
  { id: "s5", src: "final/rec/record_book.mp4", from: 5.6, len: 150, o: { az: [-20, -10], el: [50, 56], r: [380, 330] } },
  { id: "s9", src: "final/rec/sample_board.mp4", from: 10.8, len: 170, o: { az: [-6, 4], el: [52, 58], r: [390, 340] } },
  { id: "s9b", src: "final/rec/humans_only.mp4", from: 3.6, len: 170, o: { az: [-6, 4], el: [52, 58], r: [390, 340] } },   // SAFE: the board, not a pre-switch card
  { id: "s14", src: "final/rec/scout_pick_try1.mp4", from: 3.2, len: 150, o: { az: [-14, -4], el: [52, 58], r: [370, 320] } },
  { id: "s22", src: "final/rec/humans_only.mp4", from: 4.0, len: 540, o: { az: [-24, -16], el: [50, 55], r: [520, 470], shift: [85, -40, 0] } },
];
export const shot3D = (id: string) => SHOTS_3D.find((s) => s.id === id)!;

/** One pre-render composition: the shot's own frame drives the orbit. */
export const Console3DShot: React.FC<{ id: string }> = ({ id }) => {
  const s = shot3D(id);
  return <Console3D t={useCurrentFrame()} len={s.len} src={s.src} from={s.from} o={s.o} />;
};

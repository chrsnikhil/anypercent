import * as THREE from "three";
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js";

/** Light shafts in screen space: the bright pixels are smeared toward a light's point on screen, each step a little
    dimmer (the GPU Gems 3 volumetric-light-scattering post). center is in UV; amount 0 turns the pass into a copy. */
export class RaysPass extends Pass {
  q: FullScreenQuad;
  m: THREE.ShaderMaterial;
  constructor() {
    super();
    this.m = new THREE.ShaderMaterial({
      uniforms: { tColor: { value: null }, uCenter: { value: new THREE.Vector2(0.5, 0.5) }, uAmount: { value: 0 },
        uThreshold: { value: 0.35 }, uDecay: { value: 0.955 }, uDensity: { value: 0.85 }, uTint: { value: new THREE.Color(1, 0.85, 0.65) } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: /* glsl */ `
        uniform sampler2D tColor; uniform vec2 uCenter; uniform float uAmount, uThreshold, uDecay, uDensity; uniform vec3 uTint;
        varying vec2 vUv;
        void main() {
          vec3 col = min(max(texture2D(tColor, vUv).rgb, vec3(0.0)), vec3(65000.0));
          if (uAmount < 0.001) { gl_FragColor = vec4(col, 1.0); return; }
          vec2 step = (vUv - uCenter) * uDensity / 48.0;
          vec2 uv = vUv;
          float w = 1.0;
          vec3 acc = vec3(0.0);
          for (int i = 0; i < 48; i++) {
            uv -= step;
            vec3 s = min(max(texture2D(tColor, clamp(uv, vec2(0.001), vec2(0.999))).rgb, vec3(0.0)), vec3(65000.0));
            acc += max(s - uThreshold, vec3(0.0)) * w;
            w *= uDecay;
          }
          gl_FragColor = vec4(col + acc / 48.0 * uAmount * uTint, 1.0);
        }`,
    });
    this.q = new FullScreenQuad(this.m);
  }
  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    this.m.uniforms.tColor.value = readBuffer.texture;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.q.render(renderer);
  }
}

/** A world point on screen, as the rays' center (UV), and how much to show them: none when the light is behind. */
export const raysAt = (cam: THREE.Camera, world: THREE.Vector3) => {
  const v = world.clone().applyMatrix4(cam.matrixWorldInverse);
  if (v.z > -1) return { center: new THREE.Vector2(0.5, 0.5), visible: 0 };
  const p = world.clone().project(cam);
  const uv = new THREE.Vector2((p.x + 1) / 2, (p.y + 1) / 2);
  const off = Math.max(0, Math.max(Math.abs(p.x), Math.abs(p.y)) - 1);   // fades as the light leaves the frame
  return { center: uv, visible: Math.max(0, 1 - off * 1.5) };
};

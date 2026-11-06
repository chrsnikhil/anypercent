import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";
import * as THREE from "three";

const textures = new Map<string, Promise<THREE.Texture>>();

/** A texture loaded once per tab; rendering waits for it. */
export const useTexture = (url: string, srgb = true) => {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  const [handle] = useState(() => delayRender("texture " + url));
  useEffect(() => {
    if (!textures.has(url)) {
      textures.set(url, new Promise((res, rej) => new THREE.TextureLoader().load(url, res, undefined, rej)));
    }
    textures.get(url)!.then((t) => {
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 8;
      setTex(t);
      continueRender(handle);
    }).catch((e) => cancelRender(e));
  }, [url, handle, srgb]);
  return tex;
};

const buffers = new Map<string, Promise<ArrayBuffer>>();

export const useBuffer = (url: string) => {
  const [buf, setBuf] = useState<ArrayBuffer | null>(null);
  const [handle] = useState(() => delayRender("buffer " + url));
  useEffect(() => {
    if (!buffers.has(url)) buffers.set(url, fetch(url).then((r) => r.arrayBuffer()));
    buffers.get(url)!.then((b) => { setBuf(b); continueRender(handle); }).catch((e) => cancelRender(e));
  }, [url, handle]);
  return buf;
};

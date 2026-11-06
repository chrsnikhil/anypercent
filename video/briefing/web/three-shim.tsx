/* "@remotion/three" for the browser build: the same ThreeCanvas, drawn at window.__ANY_DPR of its size (the page's
   FULL / FAST quality switch; the post-processing follows the renderer's pixel ratio). web/build.mjs points every
   import of "@remotion/three" here, and this file's import of "remotion-three-real" at the package itself. */
import React from "react";
import { ThreeCanvas as Real } from "remotion-three-real";

export * from "remotion-three-real";

export const ThreeCanvas: typeof Real = (props) => (
  <Real {...props} dpr={(window as unknown as { __ANY_DPR?: number }).__ANY_DPR ?? 1} />
);

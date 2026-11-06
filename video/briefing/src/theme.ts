import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";
import T from "./timeline.json";

export const TL = T;
export const W = T.width;
export const H = T.height;

// One cool base, one accent (Spov: "a minimised colour palette with accent colours").
export const C = {
  bg: "#02060a",
  ink: "#d6eefc",      // ice: text, lines
  line: "#8cc8ea",     // steel blue: secondary lines
  dim: "#4f7a94",      // tertiary text, ghosts
  faint: "rgba(140, 200, 234, 0.16)",
  accent: "#ffb23f",   // amber: the target, the active part, the objective
  alert: "#ff5a3c",    // red: classification only
};

export const FONT = {
  head: "Barlow Condensed",
  mono: "Share Tech Mono",
  ui: "Space Mono",      // the dossier's screen type
  sub: "Barlow",         // the dossier's subtitles
};

for (const [file, weight] of [["Medium", "500"], ["SemiBold", "600"], ["Bold", "700"]]) {
  loadFont({ family: FONT.head, url: staticFile(`fonts/BarlowCondensed-${file}.ttf`), weight });
}
loadFont({ family: FONT.mono, url: staticFile("fonts/ShareTechMono-Regular.ttf"), weight: "400" });
loadFont({ family: FONT.ui, url: staticFile("fonts/SpaceMono-Regular.ttf"), weight: "400" });
loadFont({ family: FONT.ui, url: staticFile("fonts/SpaceMono-Bold.ttf"), weight: "700" });
loadFont({ family: FONT.sub, url: staticFile("fonts/Barlow-Medium.ttf"), weight: "500" });
loadFont({ family: FONT.sub, url: staticFile("fonts/Barlow-SemiBold.ttf"), weight: "600" });

export const glow = (color: string, px = 8) => `0 0 ${px}px ${color}, 0 0 ${px * 2.5}px ${color}55`;

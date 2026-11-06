import { Player, PlayerRef } from "@remotion/player";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Cut, Film, filmFrames } from "./Film";

/* The page around the live film: the whole window is the film. No timeline and no control bar. A start screen picks
   the cut (browsers only play sound after a click) and asks for real fullscreen; Space pauses, F toggles fullscreen,
   M mutes; the cursor hides while the film plays. */

const FPS = 60;
const POSTER = Math.round(17.6 * FPS);                               // behind the start screen: the cold open's PROVE IT.
const CUTS: { id: Cut; name: string; note: string }[] = [
  { id: "full", name: "DIRECTOR'S CUT", note: "the whole briefing, case files included" },
  { id: "sub", name: "SUBMISSION CUT", note: "the ETHGlobal cut, under four minutes" },
];
/** For a judge checking claims: what on screen comes from the real tools, and what is a picture of an idea (STORY.md). */
const REAL: [string, string][] = [
  ["Real", "Game footage: the shipped ROMs played on their recorded routes. The input ribbon: that run's real buttons."],
  ["Real", "731 bytes, 4,950 frames, fingerprints 94853AFC = 94853AFC, byte 381 flipped -> F40E69F2 REJECTED: arcade_replay on the real log."],
  ["Real", "The checker's terminal output, times and sizes, for all five games. The seed A6E97EC9 from a seeded run's header."],
  ["Real", "PB and its line: the launcher's own code, on a second, scripted run that hesitates before the line (0.77 s off)."],
  ["Real", "The console: its CAD, 59 parts. The launcher on its screen."],
  ["Picture", "The canyon of timers, the VOID wave, the dice, the melting clock, the x-ray twin replaying on a screen."],
  ["Not yet", "World ID, Hedera, Arkiv: built at ETHGlobal Mumbai, after this film; shown as targets, never as working."],
];
const clock = (frames: number) => {
  const s = Math.floor(frames / FPS);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/** A deep link: #submission, or #t=SECONDS[&cut=sub] opens the film paused on that moment, with no menu over it (and
    lets a headless browser take a screenshot of any frame, for checking the page against the MP4). */
const LINK = new URLSearchParams(location.hash.slice(1));
const AT = LINK.has("t") ? Math.round(Number(LINK.get("t")) * FPS) : null;

/** FULL draws the 3D at full size; FAST at 60 % (web/three-shim.tsx), for machines that drop frames. Remembered. */
type Quality = "full" | "fast";
const DPR: Record<Quality, number> = { full: 1, fast: 0.6 };
const chosenQuality = (): Quality | null => {
  if (LINK.get("q") === "fast" || LINK.get("q") === "full") return LINK.get("q") as Quality;
  try { const q = localStorage.getItem("anypercent-quality"); return q === "fast" || q === "full" ? q : null; } catch { return null; }
};

const fullscreen = (on: boolean) => {
  try {
    if (on && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => { /* refused: the window is enough */ });
    if (!on && document.fullscreenElement) document.exitFullscreen?.().catch(() => { /* already out */ });
  } catch { /* no fullscreen in this frame */ }
};

type Mode = "menu" | "playing" | "paused" | "ended";

const App: React.FC = () => {
  const [cut, setCut] = useState<Cut>(() => (location.hash === "#submission" || LINK.get("cut") === "sub" ? "sub" : "full"));
  const [mode, setMode] = useState<Mode>(AT !== null ? "paused" : "menu");
  const [quality, setQuality] = useState<Quality>(() => chosenQuality() ?? "full");
  const [note, setNote] = useState<string | null>(null);     // a brief notice (quality, sound), fades by itself
  const [idle, setIdle] = useState(false);                     // hide the cursor while the film plays
  const manual = useRef(chosenQuality() !== null);
  const resume = useRef<{ frame: number; play: boolean } | null>(null);   // carry on after a cut or quality switch
  const ref = useRef<PlayerRef>(null);
  (window as unknown as { __ANY_DPR?: number }).__ANY_DPR = DPR[quality];
  const total = filmFrames(cut);

  const say = useCallback((t: string) => {
    setNote(t);
    window.setTimeout(() => setNote((n) => (n === t ? null : n)), 3500);
  }, []);
  const start = (c: Cut) => {
    fullscreen(true);
    if (c !== cut) {
      resume.current = { frame: 0, play: true };
      setCut(c);
    } else {
      ref.current?.seekTo(0);
      ref.current?.play();
    }
    setMode("playing");
  };
  const pause = () => { ref.current?.pause(); setMode("paused"); };
  const play = () => { ref.current?.play(); setMode("playing"); };
  const setQ = (q: Quality, why?: string) => {
    if (q === quality) return;
    resume.current = { frame: ref.current ? ref.current.getCurrentFrame() : 0, play: mode === "playing" };
    setQuality(q);
    say(why ?? `3D QUALITY: ${q === "full" ? "FULL" : "FAST"}`);
  };

  // deep links and the automated checks: #t= paused on a frame, #play=1 starts muted, #bench=N counts frames drawn
  useEffect(() => {
    const p = ref.current;
    if (!p) return;
    if (AT !== null) p.seekTo(AT);
    if (LINK.has("play")) { p.mute(); p.play(); setMode("playing"); }
    if (LINK.has("bench")) {
      let n = 0;
      const count = () => { n++; };
      p.mute();
      p.addEventListener("frameupdate", count);
      p.play();
      setTimeout(() => {
        p.pause();
        p.removeEventListener("frameupdate", count);
        const line = `BENCH t=${LINK.get("t")} cut=${LINK.get("cut") ?? "full"} fps=${(n / Number(LINK.get("bench"))).toFixed(1)}`;
        (window as unknown as { __BENCH?: string }).__BENCH = line;
        console.log(line);
      }, Number(LINK.get("bench")) * 1000);
    }
  }, []);

  // a new player (after a cut or quality switch) picks up where it should; AUTO quality watches the frame rate
  useEffect(() => {
    const p = ref.current;
    if (!p) return;
    if (resume.current !== null) {
      p.seekTo(resume.current.frame);
      if (resume.current.play) p.play();
      resume.current = null;
    }
    let drawn = 0, low = 0;
    const on = () => { drawn++; };
    const ended = () => { setMode("ended"); fullscreen(false); };
    // two 2-second windows in a row under 70 % of the frames -> FAST, once, unless the viewer chose a quality
    const watch = setInterval(() => {
      const slow = p.isPlaying() && drawn < 0.7 * FPS * 2;
      drawn = 0;
      low = slow ? low + 1 : 0;
      if (low >= 2 && quality === "full" && !manual.current && !LINK.has("bench")) {
        resume.current = { frame: p.getCurrentFrame(), play: true };
        setQuality("fast");
        say("3D QUALITY: FAST // THIS MACHINE WAS DROPPING FRAMES");
      }
    }, 2000);
    p.addEventListener("frameupdate", on);
    p.addEventListener("ended", ended);
    return () => { clearInterval(watch); p.removeEventListener("frameupdate", on); p.removeEventListener("ended", ended); };
  }, [cut, quality, say]);

  // keys: Space pause / play, F fullscreen, M sound, Q 3D quality
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        if (mode === "playing") pause();
        else if (mode === "paused") play();
        else start(cut);
      } else if (e.key === "f" || e.key === "F") {
        fullscreen(!document.fullscreenElement);
      } else if (e.key === "m" || e.key === "M") {
        const p = ref.current;
        if (!p) return;
        if (p.isMuted()) { p.unmute(); say("SOUND ON"); } else { p.mute(); say("SOUND OFF"); }
      } else if (e.key === "q" || e.key === "Q") {
        manual.current = true;
        const q: Quality = quality === "full" ? "fast" : "full";
        try { localStorage.setItem("anypercent-quality", q); } catch { /* private window: not remembered */ }
        setQ(q);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  // the cursor hides two seconds after it last moved, while the film plays
  useEffect(() => {
    let t = 0;
    const move = () => { setIdle(false); window.clearTimeout(t); t = window.setTimeout(() => setIdle(true), 2000); };
    window.addEventListener("mousemove", move);
    move();
    return () => { window.removeEventListener("mousemove", move); window.clearTimeout(t); };
  }, []);

  return (
    <div className={mode === "playing" && idle ? "stage hide-cursor" : "stage"} onClick={() => { if (mode === "playing") pause(); }}>
      <Player key={`${cut}-${quality}`} ref={ref} component={Film} inputProps={{ cut }} durationInFrames={total} fps={FPS}
        compositionWidth={1920} compositionHeight={1080} controls={false} clickToPlay={false} initialFrame={AT ?? POSTER}
        style={{ width: "100vw", height: "100vh", background: "#000" }} acknowledgeRemotionLicense />
      {mode === "menu" || mode === "ended" ? (
        <div className="menu" onClick={(e) => e.stopPropagation()}>
          <div className="brand">ANY%</div>
          <div className="where">{mode === "ended" ? "END OF BRIEFING" : "ETHGLOBAL MUMBAI '26 // THE FILM, DRAWN LIVE IN YOUR BROWSER"}</div>
          <div className="cuts">
            {CUTS.map((c) => (
              <button key={c.id} className="cut" onClick={() => start(c.id)}>
                <span className="tri" />
                <b>{mode === "ended" && c.id === cut ? "PLAY AGAIN" : c.name}</b>
                <span>{clock(filmFrames(c.id))} // {c.note}</span>
              </button>
            ))}
          </div>
          <div className="keys">SPACE PAUSE // F FULLSCREEN // M SOUND // Q 3D QUALITY</div>
          <details className="real">
            <summary>WHAT IS REAL ON SCREEN</summary>
            <dl>
              {REAL.map(([k, v], i) => (
                <div key={i} className={k === "Real" ? "r" : k === "Picture" ? "p" : "n"}><dt>{k.toUpperCase()}</dt><dd>{v}</dd></div>
              ))}
            </dl>
          </details>
        </div>
      ) : null}
      {mode === "paused" && AT === null ? (
        <div className="pause" onClick={(e) => e.stopPropagation()}>
          <div className="label">PAUSED</div>
          <div className="row">
            <button onClick={play}>RESUME</button>
            <button onClick={() => { ref.current?.seekTo(0); play(); }}>RESTART</button>
            <button onClick={() => { setMode("menu"); fullscreen(false); }}>MENU</button>
          </div>
        </div>
      ) : null}
      {note ? <div className="note">{note}</div> : null}
    </div>
  );
};

createRoot(document.getElementById("root")!).render(<App />);

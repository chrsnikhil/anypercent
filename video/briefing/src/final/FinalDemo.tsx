import React from "react";
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, Series, staticFile, useCurrentFrame } from "remotion";
import { BAR, Bars, H, Line, Mono, MW, Stamp, W } from "../acts/common";
import { FONT } from "../theme";
import { easeOutExpo, prog } from "../util";
import { Console3D, shot3D } from "./console3d";
import { isLive, pick, SAFE, Slot, Take, TakeOr, TAKES } from "./takes";
import { Board, ConsolePH, CutFlash, Flip, lines, PhonePH, Screen, sec, Slate2, Tag, TermPH, Todo, TOP, Url, Vignette, Web, WebPH } from "./kit";
import { ArkivFlow, Card2, HcsPanel, ModelCode, PayFlow, Pointer, Quote, RecCrop, Row2, Subs2 } from "./kit2";
import HCS from "./hcs_messages.json";
import SC from "./scenes.json";

/* FinalDemo: the 3:58 ETHGlobal submission (video/final/SCRIPT.md, 22 scenes). Reused acts play from their own
   renders (out/*_raw.mov, transcoded into public/final/acts); real console takes (record.py) are punched in on the card
   that matters; the Any% handheld in 3D opens each section with its screen playing that section's take; everything not
   shot yet is a placeholder that says so (TODO(live) in the top bar, PLACEHOLDER on the plate). Rounds 2-3: the 3D shots play pre-rendered clips; every take not shot yet is a slot in takes.tsx. */

export const FINAL_LEN = SC.scenes.reduce((a, s) => a + s.len, 0);
const SOUND = true;                                                      // public/final/audio/final_demo.wav (prep/sponsors/final_demo.py)

/* the real HCS messages (video/final/web/hcs_messages.json: the mirror node, decoded) */
type Msg = { seq: number; body: Record<string, unknown> };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const msg = (n: number) => (HCS as Msg[]).find((m) => m.seq === n)!.body as Record<string, any>;
const INTENT = msg(12), RECEIPT = msg(13), LISTING = msg(14);

type Meta = { from: number; tag: string; todo?: string; take?: Take | Take[]; liveTag?: string; safeTag?: string }[];
const allLive = (t?: Take | Take[]) => !!t && (Array.isArray(t) ? t.every((k) => isLive(k)) : isLive(t));
/** One scene's chrome: picture, then subtitles, bars, and the source tag / TODO for the sub-shot on screen. */
const Shell: React.FC<{ f: number; meta: Meta; ls?: Line[]; cuts?: number[]; children: React.ReactNode }> = ({ f, meta, ls = [], cuts = [], children }) => {
  const m = [...meta].reverse().find((q) => f >= q.from) ?? meta[0];
  const c = [0, ...cuts].find((k) => f >= k && f < k + 3);
  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {children}
      <Subs2 f={f} lines={ls} />
      {c !== undefined ? <CutFlash f={f - c} /> : null}
      <Bars />
      {m.tag ? <Tag text={allLive(m.take) ? (m.liveTag ?? m.tag) : SAFE && m.safeTag ? m.safeTag : m.tag} /> : null}
      {m.todo && !SAFE && !allLive(m.take) ? <Todo text={m.todo} /> : null}
    </AbsoluteFill>
  );
};

/** A sub-shot window inside a scene: children only for [a, b), with the local frame; videos inside start at `a`. */
const Win: React.FC<{ f: number; a: number; b: number; children: (t: number) => React.ReactNode }> = ({ f, a, b, children }) => b <= a ? null : (
  <Sequence from={a} durationInFrames={b - a} layout="none">{f >= a && f < b ? children(f - a) : null}</Sequence>
);

/** A 3D console shot: the pre-rendered clip (public/final/c3d/<id>.mp4, FinalC3D-<id>), or the live scene. */
const LIVE_3D = false;
const C3D: React.FC<{ id: string; t: number }> = ({ id, t }) => {
  const s3 = shot3D(id);
  return LIVE_3D ? <Console3D t={t} len={s3.len} src={s3.src} from={s3.from} o={s3.o} />
    : <OffthreadVideo src={staticFile(`final/c3d/${id}.mp4`)} muted style={{ width: "100%", height: "100%" }} />;
};
/** A console take in the console's frame, for slots whose placeholder was a punch-in on a stand-in recording. */
const LiveScreen: React.FC<{ take: Take }> = ({ take }) => (
  <Screen x={PX} y={PY + 20} w={1150}><TakeOr take={take}>{null}</TakeOr></Screen>
);

/* layout: the picture left, the card column right */
const PX = 70, PY = TOP + 30, CX = 1290, CW = 560;
/* console takes (800 x 480) and the regions worth a punch-in */
const REC = { book: "final/rec/record_book.mp4", humans: "final/rec/humans_only.mp4", scout: "final/rec/scout_pick_try1.mp4", sample: "final/rec/sample_board.mp4" };
type Rect = [number, number, number, number];
const CROP: Record<string, Rect> = {
  card: [190, 34, 600, 252],                                             // the right-hand card (book, scout, records)
  board: [186, 70, 612, 238],                                            // the board's table and its legend
};

/* ---------------- 1. A race, and a ghost ---------------- */
const RACE_W = Math.round(844 * 1.5), RACE_X = (W - RACE_W) / 2, RS = RACE_W / 960;
/** The cyan ghost's place in the race render (window A, from 64.0 s), measured from its pixels and smoothed. */
const GHOST: [number, number, number][] = [[0.0, 620, 316], [0.25, 599, 314], [0.5, 568, 310], [0.75, 551, 309], [1.0, 545, 308], [1.25, 538, 308], [1.5, 528, 309],
  [1.75, 504, 312], [2.0, 449, 318], [2.25, 381, 325], [2.5, 351, 328], [2.75, 335, 328], [3.0, 308, 328], [3.25, 287, 322], [3.5, 335, 313], [3.75, 414, 299],
  [4.0, 469, 291], [4.25, 483, 283], [4.5, 468, 277], [4.75, 417, 277], [5.0, 364, 279], [5.25, 378, 278], [5.5, 435, 273], [5.75, 490, 268], [6.0, 505, 263],
  [6.25, 513, 261], [6.5, 489, 263], [6.75, 468, 265], [7.0, 473, 265], [7.25, 535, 272], [7.5, 648, 288], [7.75, 704, 300]];
const ghostAt = (t: number) => {
  const i = Math.max(0, Math.min(GHOST.length - 2, Math.floor(t / 0.25)));
  const [t0, x0, y0] = GHOST[i], [, x1, y1] = GHOST[i + 1];
  const k = Math.max(0, Math.min(1, (t - t0) / 0.25));
  return [x0 + (x1 - x0) * k, y0 + (y1 - y0) * k];
};
const Race: React.FC<{ from: number; f: number; duck?: (f: number) => boolean; children?: React.ReactNode }> = ({ from, f, duck, children }) => (
  <div style={{ position: "absolute", left: RACE_X, top: BAR, width: RACE_W, height: 844, overflow: "hidden",
    transform: `scale(${1 + 0.0066 * (f / 60)})`, transformOrigin: "50% 40%" }}>
    <OffthreadVideo src={staticFile("final/race/race1.mp4")} toneMapped={false} trimBefore={sec(from)} volume={(vf) => (duck && duck(vf) ? 0.3 : 0.7)}
      style={{ width: "100%", height: "100%", imageRendering: "pixelated" }} />
    {children}
  </div>
);
const L1 = lines(8, [[0.5, "MARINE DRIVE GP. Three laps against the clock."], [4.0, "The cyan kart is a ghost: another run, alongside."]]);
const S1: React.FC<{ f: number }> = ({ f }) => {
  const [gx, gy] = ghostAt(f / 60);
  return (
    <Shell f={f} meta={[{ from: 0, tag: "REPLAY OF A REAL RUN: ANY-6PS 1:46.90, BOT-A2'S GHOST ALONGSIDE" }]} ls={L1}>
      <Board f={f} />
      <Race from={64.0} f={f} duck={(vf) => L1.some((l) => vf >= l.at && vf < l.at + l.len)}>
        <Pointer f={f} at={sec(3.7)} x={gx * RS} y={gy * RS} label="GHOST" dx={120} dy={-120} />
      </Race>
      <Vignette k={0.45} />
      <Card2 f={f} at={16} x={18} y={TOP + 20} w={RACE_X - 34} h={226} head="REAL RUN">
        <Row2 k="BY" v="ANY-6PS" s={26} />
        <Row2 k="TIME" v="1:46.90" c={MW.amber} s={26} />
        <Mono s={20} c={MW.dim}>FROM ITS LOG</Mono>
      </Card2>
      <Card2 f={f} at={250} x={RACE_X + RACE_W + 16} y={TOP + 20} w={RACE_X - 34} h={226} head="GHOST" accent={MW.blue} headCol={MW.blue}>
        <Row2 k="RUN" v="BOT-A2" s={26} />
        <Row2 k="TIME" v="1:43.93" c={MW.amber} s={26} />
        <Mono s={20} c={MW.dim}>BY A PROGRAM</Mono>
      </Card2>
    </Shell>
  );
};

/* ---------------- 2. What a speedrun is (Primer) ---------------- */
const Act: React.FC<{ file: string; from: number }> = ({ file, from }) => (
  <OffthreadVideo src={staticFile(`final/acts/${file}`)} trimBefore={from} muted style={{ width: "100%", height: "100%" }} />
);
const S2: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} meta={[{ from: 0, tag: "EARLIER FILM (EXAMPLE LEADERBOARD)" }]}>
    <Act file="primer.mp4" from={0} />
  </Shell>
);

/* ---------------- 3. Why a video is not proof (BreaksSub) ---------------- */
const BREAKS = [[50, 400], [430, 780], [810, 1160], [1190, 1340]] as const;
const S3: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} meta={[{ from: 0, tag: "EARLIER FILM" }]}>
    <Series>
      {BREAKS.map(([a, b]) => (
        <Series.Sequence key={a} durationInFrames={b - a}><Act file="breaks_sub.mp4" from={a} /></Series.Sequence>
      ))}
    </Series>
    <Card2 f={f} at={sec(1.0)} out={sec(5.5)} x={W - 640} y={BAR + 26} w={590} h={110} head="TODAY">
      <Mono s={28} c={MW.text} w={700}>MODERATORS WATCH THE FOOTAGE</Mono>
    </Card2>
    <Card2 f={f} at={sec(12.5)} out={sec(17.0)} x={W - 640} y={BAR + 150} w={590} h={146} head="ALSO" accent={MW.red} headCol={MW.red}>
      <Mono s={28} c={MW.text} w={700}>{"TOOL-ASSISTED INPUTS,\nPASSED OFF AS HUMAN"}</Mono>
    </Card2>
  </Shell>
);

/* ---------------- 4. Any%: check the run, not the video ---------------- */
const S4: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[240]}
    meta={[{ from: 0, tag: "CAD RENDER + CONSOLE SCREEN (UI): HOME", todo: "HAND-1", take: TAKES.HAND1, liveTag: "THE HANDHELD (HAND)" }, { from: 240, tag: "TERMINAL", todo: "TERM-1 REPLAY + ONE BYTE", take: TAKES.TERM1, safeTag: "REPLAY OF A REAL RUN, FROM ITS INPUT LOG" }]}
    ls={lines(13, [[0.4, "Any%: a handheld that checks the run, not a video."], [4.4, "Every run is its input log. Our checker replays it."], [8.8, "One byte changed: the replay disagrees. It doesn't count."]])}>
    <Win f={f} a={0} b={240}>{(t) => (
      <>
        <AbsoluteFill><TakeOr take={TAKES.HAND1} keep><C3D id="s4" t={t} /></TakeOr></AbsoluteFill>
        <Card2 f={t} at={20} x={CX} y={PY} w={CW} h={226} head="ANY% // THE HANDHELD">
          <Row2 k="COMPUTE" v="RASPBERRY PI 3B+" />
          <Row2 k="SCREEN" v="5 IN, 800 x 480" />
          <Row2 k="INPUT" v="DUALSENSE (BT)" />
        </Card2>
      </>
    )}</Win>
    <Win f={f} a={240} b={780}>{(t) => (
      <>
        <Board f={t} />
        <Slot take={TAKES.TERM1} x={PX} y={PY} w={1180} h={560} safe={<OffthreadVideo src={staticFile("final/race/race1.mp4")} toneMapped={false} trimBefore={sec(20)} muted style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />}><TermPH f={t} id="TERM-1" x={0} y={0} w={1180} h={560} lines={[
          { t: "$ ./arcade_replay run.acl", at: 4 },
          { t: 'expect  "hash_matches":true   6414 frames', at: 70, c: MW.green },
          { t: "$ ...b[400]^=1...   # change one byte", at: 130 },
          { t: "$ cmp -l run.acl tampered.acl", at: 200 },
          { t: "expect  one line", at: 250 },
          { t: "$ ./arcade_replay tampered.acl", at: 290 },
          { t: 'expect  "hash_matches":false', at: 370, c: MW.red },
        ]} /></Slot>
        <Card2 f={t} at={14} x={CX} y={PY} w={CW} h={226} head="THE RUN = ITS INPUT LOG">
          <Row2 k="FILE" v="MDGP.acl" />
          <Row2 k="FRAMES" v="6414" c={MW.amber} />
          <Row2 k="TIME" v="1:46.90" />
        </Card2>
        {t >= 380 && (!SAFE || isLive(TAKES.TERM1)) ? <Stamp f={t} at={380} text="DOESN'T COUNT" col={MW.red} x={CX + CW / 2} y={PY + 380} s={60} /> : null}
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 5. World: consoles exclusive to humans ---------------- */
const PostCard: React.FC<{ t: number; at: number }> = ({ t, at }) => (
  <Card2 f={t} at={at} x={CX} y={PY} w={CW} h={290} head="TO POST A RUN">
    <Row2 k="A CONSOLE" v="LINKED TO A BOOK" />
    <Row2 k="A BOOK" v="NEEDS A WORLD ID" />
    <Row2 k="CREDENTIAL" v="ORB" c={MW.amber} />
    <Row2 k="PER HUMAN" v="ONE BOOK" />
  </Card2>
);
const S5: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[60, 210, 420]}
    meta={[{ from: 0, tag: "" }, { from: 60, tag: "CAD RENDER + CONSOLE SCREEN (UI): MY RECORD BOOK" }, { from: 210, tag: "CONSOLE SCREEN (UI): MY RECORD BOOK" },
      { from: 420, tag: "CONSOLE SCREEN (UI)", todo: "UI-4a FRESH CONSOLE", take: TAKES.UI4A, safeTag: "CONSOLE SCREEN (UI): MY RECORD BOOK" }]}
    ls={lines(10, [[1.1, "Any% consoles are exclusive to humans."], [3.4, "Only a World ID-linked console can post a run."], [6.8, "World doesn't show who held the controller."]])}>
    <Win f={f} a={0} b={60}>{(t) => <Slate2 f={t} part="WORLD // IDKIT" title="CONSOLES FOR HUMANS" num="01" />}</Win>
    <Win f={f} a={60} b={210}>{(t) => <C3D id="s5" t={t} />}</Win>
    <Win f={f} a={210} b={420}>{(t) => (
      <>
        <Board f={t} />
        <RecCrop file={REC.book} from={6.3} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} />
        <PostCard t={t} at={10} />
      </>
    )}</Win>
    <Win f={f} a={420} b={600}>{(t) => (
      <>
        <Board f={t} />
        {SAFE && !isLive(TAKES.UI4A) ? <RecCrop file={REC.book} from={8.4} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t + 210} hold /> : null}
        <Screen x={PX} y={PY + 20} w={SAFE && !isLive(TAKES.UI4A) ? 0 : 900}>
          <TakeOr take={TAKES.UI4A}><ConsolePH f={t} id="UI-4a" title="Record book needed" rows={[["How", "World App > IDKit"], ["Needed for", "buying, listing ghosts"]]} accent={MW.amber} /></TakeOr>
        </Screen>
        <PostCard t={t} at={-100} />
        <Card2 f={t} at={6} x={CX} y={PY + 310} w={CW} h={120} head="NOT CLAIMED" accent={MW.faint} headCol={MW.dim}>
          <Mono s={27} c={MW.text} w={700}>WHO HELD THE CONTROLLER</Mono>
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 6. World: one human, one book ---------------- */
const SPW = 1100, SPY = TOP + 20;
const S6: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[480]}
    meta={[{ from: 0, tag: "CONSOLE SCREEN (UI): EARLIER MOCK FRAMES", todo: "UI-4b + PHONE-1", take: [TAKES.UI4B, TAKES.PHONE1], liveTag: "CONSOLE SCREEN (UI) + WORLD APP (PHONE)", safeTag: "CONSOLE SCREEN (UI): MY RECORD BOOK" }, { from: 480, tag: "CONSOLE SCREEN (UI): THE BOARD, HUMANS ONLY" }]}
    ls={lines(11, [[0.4, "One human, one record book (Orb credential)."], [4.8, "Same person, second sign-up: Already registered."], [8.2, "No second book, on any console."]])}>
    <Board f={f} />
    <Win f={f} a={0} b={480}>{(t) => (
      <>
        {SAFE && !isLive(TAKES.UI4B) ? (
          <>
            <RecCrop file={REC.book} from={8.0} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} hold />
            <Card2 f={t} at={14} x={CX} y={PY} w={CW} h={226} head="ONE HUMAN, ONE BOOK">
              <Row2 k="WORLD ID" v="ORB" c={MW.amber} />
              <Row2 k="SECOND BOOK" v="REFUSED" />
              <Row2 k="RUNS" v="ON THIS BOOK" />
            </Card2>
          </>
        ) : null}
        <Screen x={PX} y={SPY} w={SAFE && !isLive(TAKES.UI4B) ? 0 : SPW}>
          <TakeOr take={TAKES.UI4B}>{t < 250 ? <Flip f={t} dir="sponsors/world/id_scan" count={120} /> : <Flip f={t - 250} dir="sponsors/world/id_dup" count={120} />}</TakeOr>
        </Screen>
        <Slot take={TAKES.PHONE1} x={1290} y={SPY} w={311} h={660}><PhonePH f={t} id="PHONE-1" x={0} y={0} h={660} title="World App" text="Scans the fresh console's QR. Its own answer, unedited: <take>" button="<take>" /></Slot>
      </>
    )}</Win>
    <Win f={f} a={480} b={660}>{(t) => (
      <>
        <RecCrop file={REC.humans} from={5.9} crop={CROP.board} x={PX} y={PY + 30} w={1180} f={t} />
        <Card2 f={t} at={10} x={CX} y={PY} w={CW} h={226} head="THE BOARD // HUMANS">
          <Row2 k="HUMAN" v="1 BOOK" c={MW.green} />
          <Row2 k="BOT" v="6 RUNS" c={MW.amber} />
          <Row2 k="SQUARE" v="HUMANS ONLY" />
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 7. World: every listing, approved ---------------- */
const S7: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[480]}
    meta={[{ from: 0, tag: "WORLD APP (PHONE) + HEDERA HCS #14 (REAL TEXT)", todo: "PHONE-2", take: TAKES.PHONE2, safeTag: "HEDERA HCS #14: THE APPROVED TEXT (REAL)" }, { from: 480, tag: "CONSOLE SCREEN (UI)", todo: "UI-6 RECORDING, LISTING", take: TAKES.UI6B, safeTag: "HEDERA MIRROR NODE, DECODED (WEB): LISTING #14" }]}
    ls={lines(14, [[0.4, "Every listing is approved in World App."], [4.8, "It shows the exact text: game, time, price, payee."], [9.5, "One approval, one listing."]])}>
    <Board f={f} />
    <Win f={f} a={0} b={480}>{(t) => (
      <>
        <Slot take={TAKES.PHONE2} x={PX} y={SPY} w={311} h={660}><PhonePH f={t} id="PHONE-2" x={0} y={0} h={660} title="List a ghost" text="<take: World App shows the text on the right, then Approve>" /></Slot>
        <Quote f={t} at={20} x={pick(440, PX)} y={PY} w={pick(1410, 1780)} head="APPROVED IN WORLD APP, WORD FOR WORD (HCS LISTING #14)" text={String(LISTING.action)}
          foot="topic 0.0.11332437 // the listing's own message" />
        <Card2 f={t} at={120} x={pick(440, PX)} y={PY + 330} w={pick(1410, 1780)} h={150} head="WHAT THE OWNER READS BEFORE APPROVING">
          <div style={{ display: "flex", gap: 56 }}>
            {[["GAME", "MARINE DRIVE GP"], ["TIME", "1:43.75"], ["PRICE", "0.10 USDC"], ["PAYEE", "0.0.9473064"]].map(([k, v]) => (
              <div key={k}><Mono s={22} c={MW.dim}>{k}</Mono><Mono s={30} c={k === "PAYEE" ? MW.amber : MW.text} w={700}>{v}</Mono></div>
            ))}
          </div>
        </Card2>
      </>
    )}</Win>
    <Win f={f} a={480} b={840}>{(t) => (
      <>
        <Board f={t} />
        {SAFE && !isLive(TAKES.UI6B) ? (
          <HcsPanel f={t} x={PX} y={PY} w={1180} h={420} head="HCS #14  LISTING" sub="topic 0.0.11332437"
            rows={[["book", String(LISTING.book)], ["game", `${LISTING.game}, ${LISTING.frames} frames (1:43.75)`], ["price", `${LISTING.price} USDC`], ["pay_to", String(LISTING.pay_to), MW.amber]]} />
        ) : null}
        <Screen x={PX} y={PY + 20} w={SAFE && !isLive(TAKES.UI6B) ? 0 : 1000}>
          <TakeOr take={TAKES.UI6B}>{t < 150 ? <ConsolePH f={t} id="UI-6" title="Recording on Hedera" rows={[["Approved", "in World App"]]} />
            : <ConsolePH f={t - 150} id="UI-6" title="Listing on Arkiv" rows={[["Recorded", "Hedera LISTING #<take>"], ["Ends", "in 7 days"]]} />}</TakeOr>
        </Screen>
        <Card2 f={t} at={14} x={CX} y={PY} w={CW} h={226} head="ONE APPROVAL">
          <Row2 k="LISTINGS" v="ONE" />
          <Row2 k="ON HEDERA" v="ITS MESSAGE" />
          <Row2 k="ENDS" v="IN 7 DAYS" c={MW.amber} />
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 8. World: the link names the console's wallet ---------------- */
const S8: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[300]}
    meta={[{ from: 0, tag: "TERMINAL + WORLD APP (PHONE)", todo: "TERM-6 + PHONE-3", take: [TAKES.TERM6, TAKES.PHONE3], safeTag: "CONSOLE SCREEN (UI): MY RECORD BOOK" }, { from: 300, tag: "CONSOLE SCREEN (UI): MY RECORD BOOK", todo: "UI-3b THE WALLET LINE", take: TAKES.UI3B }]}
    ls={lines(8, [[0.4, "Each console is linked to one book."], [3.6, pick("The approval names the console's own Arkiv wallet.", "Linking a console takes the owner's approval.")]])}>
    <Board f={f} />
    <Win f={f} a={0} b={300}>{(t) => (
      <>
        {SAFE && !isLive(TAKES.TERM6) ? <RecCrop file={REC.book} from={8.0} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} hold /> : null}
        <Slot take={TAKES.TERM6} x={PX} y={SPY} w={1140} h={660}><TermPH f={t} id="TERM-6" x={0} y={0} w={1140} h={660} lines={[
          { t: "$ npm run console:link -- --console C-QP6P", at: 4 },
          { t: "      --book ANY-6PS", at: 60 },
          { t: "expect  the exact World App text, naming the wallet", at: 110 },
          { t: "expect  a terminal QR, the stages, done", at: 140 },
        ]} /></Slot>
        <Slot take={TAKES.PHONE3} x={1290} y={SPY} w={311} h={660}><PhonePH f={t} id="PHONE-3" x={0} y={0} h={660} title="Link a console"
          text="Link console C-QP6P (wallet <take: 0x....>) to record book ANY-6PS: PB on it spends this book's coach budget" /></Slot>
      </>
    )}</Win>
    <Win f={f} a={300} b={480}>{(t) => (
      <>
        {isLive(TAKES.UI3B) ? <LiveScreen take={TAKES.UI3B} /> : <RecCrop file={REC.book} from={7.0} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} />}
        <Card2 f={t} at={10} x={CX} y={PY} w={CW} h={226} head="ONE CONSOLE, ONE BOOK">
          <Row2 k="CONSOLE" v="C-QP6P" />
          <Row2 k="BOOK" v="ANY-6PS" />
          {SAFE ? <Row2 k="LINK" v="OWNER APPROVES" /> : <Row2 k="ITS WALLET" v="<take>" c={MW.amber} />}
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 9-13. Arkiv ---------------- */
const SMALL = { x: PX, y: PY + 10, w: 520, h: 520 };
const S9: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[60, 230]}
    meta={[{ from: 0, tag: "" }, { from: 60, tag: "CAD RENDER + CONSOLE SCREEN (UI): PRE-SWITCH CARD", safeTag: "CAD RENDER + CONSOLE SCREEN (UI): THE BOARD" }, { from: 230, tag: "DIAGRAM + ARKIV EXPLORER (WEB)", todo: "WEB-6 THE CONSOLE'S TX", take: TAKES.WEB6, safeTag: "DIAGRAM: HOW A RUN REACHES THE BOARD" }]}
    ls={lines(11, pick<[number, string][]>([[1.3, "The console's own Arkiv wallet signs its run."], [5.5, "The record lives under that wallet, read-only."], [8.5, "Arkiv Rabdi testnet."]],
      [[1.3, "On Arkiv, every run is a public record."], [5.5, "Rows are read-only once written."], [8.5, "Arkiv Rabdi testnet."]]))}>
    <Win f={f} a={0} b={60}>{(t) => <Slate2 f={t} part="ARKIV" title="THE CONSOLE OWNS THE RECORD" num="02" />}</Win>
    <Win f={f} a={60} b={230}>{(t) => <C3D id={pick("s9", "s9b")} t={t} />}</Win>
    <Win f={f} a={230} b={660}>{(t) => (
      <>
        <Board f={t} />
        <Slot take={TAKES.WEB6} {...SMALL}><WebPH f={t} id="WEB-6" url="rabdi.explorer.arkiv.network/tx/<take>" head="The console's tx" x={0} y={0} w={SMALL.w} h={SMALL.h}
          rows={[["From", "<take: console>"], ["Creates", "run + listing"], ["Chain", "7794095"]]} /></Slot>
        <ArkivFlow f={t} x={610} y={PY + 10} beat="sign" />
      </>
    )}</Win>
  </Shell>
);

const S10: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[360]}
    meta={[{ from: 0, tag: "DIAGRAM + ARKIV EXPLORER (WEB)", todo: "WEB-7 THE STAMP ENTITY", take: TAKES.WEB7, safeTag: "DIAGRAM: HOW A RUN REACHES THE BOARD" }, { from: 360, tag: "CONSOLE SCREEN (UI): THE BOARD", todo: "UI-2 AFTER THE SWITCH", take: TAKES.UI2A }]}
    ls={lines(11, [[0.4, "Our server checks it: the checker replays the log."], [4.3, pick("Then it writes a separate stamp.", "Only runs that replay reach the board.")], [7.6, pick("The board ranks stamped runs only.", "The board, read straight from Arkiv.")]])}>
    <Board f={f} />
    <Win f={f} a={0} b={360}>{(t) => (
      <>
        <Slot take={TAKES.WEB7} {...SMALL}><WebPH f={t} id="WEB-7" url="rabdi.explorer.arkiv.network/entity/<take>" head="The stamp" x={0} y={0} w={SMALL.w} h={SMALL.h}
          rows={[["Creator", "0x3d32...3f63"], ["run", "<take: run key>"], ["console", "<take: wallet>"], ["frames", "<take>"]]} /></Slot>
        <ArkivFlow f={t} x={610} y={PY + 10} beat="stamp" />
      </>
    )}</Win>
    <Win f={f} a={360} b={660}>{(t) => (
      <>
        <Board f={t} />
        {isLive(TAKES.UI2A) ? <LiveScreen take={TAKES.UI2A} /> : <RecCrop file={REC.humans} from={3.6} crop={CROP.board} x={PX} y={PY + 30} w={1180} f={t} />}
        <Card2 f={t} at={14} x={CX} y={PY} w={CW} h={180} head="THE BOARD">
          <Row2 k="RANKS" v={pick("STAMPED RUNS", "REPLAYED RUNS")} c={MW.amber} />
          <Row2 k="TIERS" v="HUMAN // BOT" />
        </Card2>
      </>
    )}</Win>
  </Shell>
);

const S11: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} meta={[{ from: 0, tag: "DIAGRAM + ARKIV EXPLORER (WEB)", todo: "WEB-8 RUN + STAMP", take: TAKES.WEB8, safeTag: "ARKIV EXPLORER (WEB): A REAL TX, READ-ONLY ROWS" }]}
    ls={lines(9, [[0.4, pick("Our server decides what counts.", "Each row records the wallet that wrote it.")], [3.6, pick("It can't change, delete or own your record.", "Rows are read-only: no edits in place.")]])}>
    <Board f={f} />
    <Slot take={TAKES.WEB8} {...SMALL}><WebPH f={f} id="WEB-8" url="rabdi.explorer.arkiv.network/entity/<take>" head="Run vs stamp" x={0} y={0} w={SMALL.w} h={SMALL.h}
      rows={[["Run owner", "<take: console>"], ["Stamp by", "0x3d32...3f63"], ["Flags", "readonly"]]} /></Slot>
    {SAFE && !isLive(TAKES.WEB8) ? (
      <>
        <Web f={f} src="final/web/arkiv_bot_batch_tx.png" focus={[40, 180, 1520, 520]} to={[0, TOP + 54, W, 620]} />
        <Url f={f} at={4} text="rabdi.explorer.arkiv.network/tx/0x0afdc18b...1981b31b2" x={60} y={TOP + 2} s={22} />
      </>
    ) : <ArkivFlow f={f} x={610} y={PY + 10} beat="own" />}
    <Card2 f={f} at={sec(3.6)} x={610} y={PY + 540} w={1240} h={110} head="WHY IT CAN'T" accent={MW.amber} headCol={MW.amber} out={SAFE && !isLive(TAKES.WEB8) ? -1 : 1e9}>
      <Mono s={26} c={MW.text} w={700}>ARKIV'S RULES: ROWS READ-ONLY; ONLY THE OWNER DELETES</Mono>
    </Card2>
  </Shell>
);

const S12: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[240, 450]}
    meta={[{ from: 0, tag: "PUBLIC WEB BOARD (WEB): PRE-SWITCH STILL", todo: "WEB-9 STAMP-READING BOARD", take: TAKES.WEB9A, liveTag: "PUBLIC WEB BOARD (WEB)", safeTag: "PUBLIC WEB BOARD (WEB)" }, { from: 240, tag: "DIAGRAM + TERMINAL", todo: "TERM-2 README QUERY", take: TAKES.TERM2, safeTag: "DIAGRAM: WHO READS THE BOARD" },
      { from: 450, tag: "TERMINAL: THE REPO'S arkiv/ (REAL LISTING, TYPESET)", todo: "WEB-10a FILES NEED THE STAMP UPDATE", take: TAKES.WEB10A, liveTag: "GITHUB (WEB)" }]}
    ls={lines(9, [[0.4, "Anyone can query the records. No key."], [4.6, "And replay any log they hold."]])}>
    <Board f={f} />
    <Win f={f} a={0} b={240}>{(t) => (
      <>
        <Slot take={TAKES.WEB9A} x={0} y={TOP + 54} w={W} h={790} keep><Web f={t} src="final/web/public_board.png" focus={[380, 80, 840, 330]} to={[0, 0, W, 790]} /></Slot>
        <Url f={t} at={4} text="chrsnikhil.github.io/anypercent" x={60} y={TOP + 2} s={26} />
      </>
    )}</Win>
    <Win f={f} a={240} b={450}>{(t) => (
      <>
        <Slot take={TAKES.TERM2} {...SMALL}><TermPH f={t} id="TERM-2" x={0} y={0} w={SMALL.w} h={SMALL.h} lines={[{ t: "$ curl -s <README", at: 4 }, { t: "  query> | jq", at: 20 }, { t: "expect  a stamp +", at: 60 }, { t: "  its run, no key", at: 70 }]} /></Slot>
        <ArkivFlow f={t} x={610} y={PY + 10} beat="query" />
      </>
    )}</Win>
    <Win f={f} a={450} b={540}>{(t) => (
      <Slot take={TAKES.WEB10A} x={PX} y={PY} w={1780} h={560} keep>
        <TermPH f={t} id="WEB-10a" x={0} y={0} w={1780} h={560} real lines={[
          { t: "$ ls arkiv/", at: 2 },
          { t: "friction.md   how-you-use-arkiv.md   reach.md", at: 20, c: MW.blue },
          { t: "schema.md     snapshot.json          why-arkiv.md", at: 26, c: MW.blue },
        ]} />
      </Slot>
    )}</Win>
  </Shell>
);

const S13: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[230]}
    meta={[{ from: 0, tag: "DIAGRAM + TERMINAL", todo: "TERM-3 ARKIV:LOOKALIKE", take: TAKES.TERM3, safeTag: "DIAGRAM: WHAT THE BOARD IGNORES" }, { from: 230, tag: "CONSOLE SCREEN (UI): THE BOARD'S BOT ROWS", todo: "UI-2 AFTER THE SWITCH", take: TAKES.UI2B }]}
    ls={lines(8, [[0.3, pick("A stranger's look-alike row: no stamp, ignored.", "A stranger's look-alike row is ignored.")], [4.2, pick("BOT ghosts: a separate house wallet, labelled BOT.", "BOT ghosts are labelled BOT: made by a program.")]])}>
    <Board f={f} />
    <Win f={f} a={0} b={230}>{(t) => (
      <>
        <Slot take={TAKES.TERM3} {...SMALL}><TermPH f={t} id="TERM-3" x={0} y={0} w={SMALL.w} h={SMALL.h} lines={[{ t: "$ npm run arkiv:", at: 4 }, { t: "  lookalike", at: 20 }, { t: "expect  a perfect", at: 60 }, { t: "  copy, no stamp", at: 70 }]} /></Slot>
        <ArkivFlow f={t} x={610} y={PY + 10} beat="lookalike" />
      </>
    )}</Win>
    <Win f={f} a={230} b={480}>{(t) => (
      <>
        {isLive(TAKES.UI2B) ? <LiveScreen take={TAKES.UI2B} /> : <RecCrop file={REC.humans} from={11.0} crop={[186, 100, 612, 208]} x={PX} y={PY + 30} w={1180} f={t} />}
        <Card2 f={t} at={12} x={CX} y={PY} w={CW} h={226} head="BOT" accent={MW.amber} headCol={MW.amber}>
          <Row2 k="MADE BY" v="A PROGRAM" />
          {SAFE ? null : <Row2 k="WRITTEN BY" v="HOUSE WALLET" />}
          <Row2 k="NEVER" v="HUMAN" c={MW.amber} />
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 14-17. Hedera ---------------- */
const S14: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[60, 210, 366, 492]}
    meta={[{ from: 0, tag: "" }, { from: 60, tag: "CAD RENDER + CONSOLE SCREEN (UI): THE BOARD, CROSS, SCOUTING" }, { from: 210, tag: "CONSOLE SCREEN (UI): SCOUTING" },
      { from: 366, tag: "CONSOLE SCREEN (UI): THE PICK SCREEN (STOPPED BEFORE BUYING)" }, { from: 492, tag: "DIAGRAM: THE PICK ABOVE, THEN PB'S GUARDS" }]}
    ls={lines(12, [[1.3, "PB's scout: a language model on Groq."], [4.8, "It finds the ghost that beats you where you're slowest."], [8.6, "It picks which ghost. Code decides the rest."]])}>
    <Win f={f} a={0} b={60}>{(t) => <Slate2 f={t} part="HEDERA // x402" title="AN AGENT THAT PAYS" num="03" />}</Win>
    <Win f={f} a={60} b={210}>{(t) => <C3D id="s14" t={t} />}</Win>
    <Win f={f} a={210} b={366}>{(t) => (
      <>
        <Board f={t} />
        <RecCrop file={REC.scout} from={5.5} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} />
      </>
    )}</Win>
    <Win f={f} a={366} b={492}>{(t) => (
      <>
        <Board f={t} />
        <RecCrop file={REC.scout} from={8.1} crop={CROP.card} x={PX} y={PY + 20} w={1180} f={t} />
      </>
    )}</Win>
    {f >= 210 && f < 492 ? (
      <Card2 f={f} at={220} x={CX} y={PY} w={CW} h={290} head="THE SCOUT">
        <Row2 k="MODEL" v="gpt-oss-120b" />
        <Row2 k="ON" v="GROQ" />
        <Row2 k="READS" v="LAPS ON ARKIV" />
        <Row2 k="IT PICKS" v="WHICH GHOST" c={MW.amber} />
      </Card2>
    ) : null}
    {f >= 366 && f < 492 ? (
      <Card2 f={f} at={380} x={CX} y={PY + 310} w={CW} h={180} head="THIS PICK" accent={MW.blue} headCol={MW.blue}>
        <Row2 k="GHOST" v="BOT-A2 1:43.93" />
        <Row2 k="LAP 2" v="-2.85 S" c={MW.red} />
      </Card2>
    ) : null}
    <Win f={f} a={492} b={720}>{(t) => (
      <>
        <Board f={t} />
        <ModelCode f={t} x={PX} y={PY + 150} />
      </>
    )}</Win>
  </Shell>
);

const S15: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} meta={[{ from: 0, tag: "DIAGRAM: AN EARLIER REAL PURCHASE (HCS #12, #13)", todo: "UI-7 PAYING, GHOST LOADED", take: TAKES.UI7A, liveTag: "CONSOLE SCREEN (UI)" }]}
    ls={lines(11, [[0.4, "No human approves the payment."], [3.4, "Code limits: 0.10 USDC a ghost, 1.00 a book daily."], [7.4, "It pays only the account on the listing."]])}>
    <Board f={f} />
    {isLive(TAKES.UI7A) ? (
      <>
        <LiveScreen take={TAKES.UI7A} />
        <Card2 f={f} at={16} x={CX} y={PY} w={CW} h={290} head="GUARDS, IN CODE" accent={MW.green} headCol={MW.green}>
          <Row2 k="A GHOST" v="0.10 MAX" />
          <Row2 k="A BOOK, DAILY" v="1.00 MAX" />
          <Row2 k="PAYS ONLY" v="THE LISTING" c={MW.amber} />
          <Row2 k="APPROVAL" v="NONE" />
        </Card2>
      </>
    ) : (
      <>
        <PayFlow f={f} x={PX} y={PY + 20} />
        <Card2 f={f} at={30} x={PX} y={PY + 290} w={340} h={150} head="HUMAN APPROVAL" accent={MW.red} headCol={MW.red}>
          <Mono s={30} c={MW.text} w={700}>NONE</Mono>
          <Mono s={22} c={MW.dim}>UNDER THE CAPS</Mono>
        </Card2>
      </>
    )}
  </Shell>
);

const S16: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[240, 390]}
    meta={[{ from: 0, tag: "HEDERA MIRROR NODE, DECODED (WEB): AN EARLIER REAL PURCHASE" }, { from: 240, tag: "HEDERA MIRROR NODE, DECODED (WEB): ITS RECEIPT" },
      { from: 390, tag: "HASHSCAN TESTNET (WEB): THE SAME PAYMENT" }]}
    ls={lines(10, [[0.3, "INTENT, with the model's reason, goes to HCS before signing."], [4.1, "RECEIPT after it settles."], [6.6, "Settled on Hedera testnet, in USDC, via x402.org."]])}>
    <Board f={f} />
    <Win f={f} a={0} b={240}>{(t) => (
      <HcsPanel f={t} x={PX} y={PY} w={1780} h={500} head="HCS #12  INTENT" sub="topic 0.0.11332437 // sent before PB signs"
        rows={[["buyer", `${INTENT.buyer}  buys  ${INTENT.seller}'s ghost`], ["scout", `${INTENT.scout.by}: ${INTENT.scout.model}`, MW.blue],
          ["why", `"${INTENT.scout.why}"`, MW.amber], ["laps", `you ${INTENT.scout.you.join(" / ")}  vs  ${INTENT.scout.it.join(" / ")} frames`],
          ["pays", `${INTENT.amount} USDC (${INTENT.asset}) to ${INTENT.pay_to}`], ["left today", `${INTENT.left_today} USDC`, MW.green]]} />
    )}</Win>
    <Win f={f} a={240} b={390}>{(t) => (
      <HcsPanel f={t} x={PX} y={PY} w={1780} h={420} head="HCS #13  RECEIPT" sub={`for INTENT #${RECEIPT.intent} // after it settles`}
        rows={[["tx", String(RECEIPT.tx)], ["from", `${RECEIPT.from}  (PB's agent)`], ["to", `${RECEIPT.pay_to}  (the house)`],
          ["amount", `${RECEIPT.amount} USDC (${RECEIPT.asset})`], ["mirror", String(RECEIPT.mirror), MW.green]]} />
    )}</Win>
    <Win f={f} a={390} b={600}>{(t) => (
      <>
        <Web f={t} src="final/web/hashscan_payment_bot.png" focus={[0, 230, 1600, 440]} focus2={[0, 860, 1100, 140]} at2={70} to={[0, TOP + 54, W, 620]} />
        <Url f={t} at={4} text="hashscan.io/testnet/transaction/0.0.9185802-1793951207-849742365" x={60} y={TOP + 2} s={24} />
      </>
    )}</Win>
  </Shell>
);

const S17: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={pick([180, 300, 390], [])}
    meta={pick([{ from: 0, tag: "TERMINAL", todo: "TERM-7 EVIL402", take: TAKES.TERM7, safeTag: "HASHSCAN TESTNET (WEB): THE TOPIC PB WRITES TO" }, { from: 180, tag: "TERMINAL", todo: "TERM-8 VERIFY", take: TAKES.TERM8 }, { from: 300, tag: "TERMINAL", todo: "TERM-9 NO SOLIDITY", take: TAKES.TERM9 },
      { from: 390, tag: "GITHUB (WEB)", todo: "WEB-10b README IDS", take: TAKES.WEB10B }], [{ from: 0, tag: "HASHSCAN TESTNET (WEB): THE TOPIC PB WRITES TO" }])}
    ls={lines(8, [[0.3, "A paywall naming another account: refused. Nothing signed."], [3.3, "Anyone can check the records agree."], [5.6, "Hedera SDK only. No Solidity."]])}>
    <Board f={f} />
    {SAFE ? (
      <>
        <Web f={f} src="final/web/hashscan_topic.png" focus={[0, 70, 1600, 520]} to={[0, TOP + 54, W, 620]} />
        <Url f={f} at={4} text="hashscan.io/testnet/topic/0.0.11332437" x={60} y={TOP + 2} s={24} />
        <Card2 f={f} at={20} x={1290} y={PY + 110} w={560} h={226} head="PB'S GUARDS, IN CODE" accent={MW.green} headCol={MW.green}>
          <Row2 k="PAYS ONLY" v="THE LISTING" />
          <Row2 k="A FAKE 402" v="REFUSED" c={MW.red} />
          <Row2 k="THE SAME GHOST" v="NEVER TWICE" />
        </Card2>
        <Card2 f={f} at={sec(5.6)} x={1290} y={PY + 356} w={560} h={150} head="NO SOLIDITY" accent={MW.blue} headCol={MW.blue}>
          <Row2 k="HEDERA SDK ONLY" v="HCS + HTS" />
        </Card2>
      </>
    ) : null}
    <Win f={f} a={0} b={pick(180, 0)}>{(t) => (
      <>
        <Slot take={TAKES.TERM7} x={PX} y={PY} w={1780} h={560}><TermPH f={t} id="TERM-7" x={0} y={0} w={1780} h={560} lines={[
          { t: "$ npm run hedera:evil402 -- --listing <take>", at: 2 },
          { t: "expect  REFUSED payTo", at: 60, c: MW.red },
          { t: "expect  EVIL402 REFUSED (as it should be)", at: 80, c: MW.red },
        ]} /></Slot>
        <Stamp f={t} at={90} text="REFUSED" col={MW.red} y={PY + 380} s={100} sub="NOTHING SIGNED" />
      </>
    )}</Win>
    <Win f={f} a={pick(180, 0)} b={pick(300, 0)}>{(t) => (
      <Slot take={TAKES.TERM8} x={PX} y={PY} w={1780} h={560}><TermPH f={t} id="TERM-8" x={0} y={0} w={1780} h={560} lines={[
        { t: "$ npm run hedera:verify -- <take: purchase>", at: 2 },
        { t: "expect  VERIFIED: INTENT, payment, RECEIPT agree", at: 50, c: MW.green },
      ]} /></Slot>
    )}</Win>
    <Win f={f} a={pick(300, 0)} b={pick(390, 0)}>{(t) => (
      <Slot take={TAKES.TERM9} x={PX} y={PY} w={1780} h={560}><TermPH f={t} id="TERM-9" x={0} y={0} w={1780} h={560} lines={[{ t: "$ git ls-files '*.sol' | wc -l", at: 2 }, { t: "expect  0", at: 40, c: MW.green }]} /></Slot>
    )}</Win>
    <Win f={f} a={pick(390, 0)} b={pick(480, 0)}>{(t) => (
      <Slot take={TAKES.WEB10B} x={PX} y={PY} w={1780} h={560}><WebPH f={t} id="WEB-10b" url="github.com/chrsnikhil/anypercent" head="README // Hedera on-chain ids" x={0} y={0} w={1780} h={560}
        rows={[["HCS topic", "0.0.11332437"], ["PB's agent", "0.0.11332435"], ["House", "0.0.11333910"], ["A payment", "0.0.9185802@1793951207.849742365"], ["Contracts", "none: Hedera SDK only"]]} /></Slot>
    )}</Win>
  </Shell>
);

/* ---------------- 18-20. What you get ---------------- */
const S18: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[60]}
    meta={[{ from: 0, tag: "" }, { from: 60, tag: "PUBLIC WEB BOARD (WEB): PRE-SWITCH STILL", todo: "WEB-9b (PHONE-6)", take: TAKES.WEB9B, liveTag: "PUBLIC WEB BOARD (WEB)", safeTag: "PUBLIC WEB BOARD (WEB)" }]}
    ls={lines(8, [[1.2, "A public board anyone can open."], [4.2, "Read straight from Arkiv: no account, no key."]])}>
    <Win f={f} a={0} b={60}>{(t) => <Slate2 f={t} part="ANY%" title="WHAT YOU GET" num="04" />}</Win>
    <Win f={f} a={60} b={480}>{(t) => (
      <>
        <Board f={t} />
        <AbsoluteFill><TakeOr take={TAKES.WEB9B} keep><Web f={t} src="final/web/public_board.png" focus={[370, 10, 860, 620]} focus2={[370, 260, 860, 620]} at2={150} dim={prog(t, 160, 190) * 0.35} /></TakeOr></AbsoluteFill>
        {t >= 180 ? (
          <div style={{ position: "absolute", left: 0, right: 0, top: H / 2 - 90, display: "flex", justifyContent: "center",
            clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 180, 200))}% 0 0)` }}>
            <div style={{ background: "rgba(5,5,6,0.92)", borderLeft: `5px solid ${MW.orange}`, padding: "22px 48px 28px" }}>
              <Mono s={24} c={MW.orange} w={700} ls="0.3em" style={{ marginBottom: 12 }}>OPEN IT ON ANY PHONE</Mono>
              <Mono s={64} c={MW.ice} w={700} ls="0.01em">chrsnikhil.github.io/anypercent</Mono>
            </div>
          </div>
        ) : null}
      </>
    )}</Win>
  </Shell>
);

const S19: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} meta={[{ from: 0, tag: "CONSOLE SCREEN (UI): BOT-A2'S RECORDS", todo: "HAND-3 + UI-8", take: TAKES.HAND3, liveTag: "THE HANDHELD (HAND)" }]}
    ls={lines(8, [[0.4, "Any run's records, one press away on the handheld."]])}>
    <Board f={f} />
    <AbsoluteFill><TakeOr take={TAKES.HAND3} safe={
      f < 200 ? <RecCrop file={REC.sample} from={9.6} crop={[180, 60, 620, 145]} x={PX} y={PY + 60} w={1180} f={f} />
        : <RecCrop file={REC.sample} from={12.9} crop={[180, 60, 620, 145]} x={PX} y={PY + 60} w={1180} f={f} hold />}>
      <RecCrop file={REC.sample} from={9.6} crop={[180, 30, 620, 260]} x={PX} y={PY + 20} w={1180} f={f} /></TakeOr></AbsoluteFill>
    <Card2 f={f} at={60} x={CX} y={PY} w={CW} h={350} head="TRIANGLE // ITS RECORDS">
      <Row2 k="ARKIV" v="RUN, LISTING" />
      {SAFE ? null : <Row2 k="HEDERA" v="LISTING #9" />}
      <Row2 k="REPLAYED BY" v="THE CHECKER" c={MW.amber} />
      <Row2 k="PAYS" v="0.0.11333910" />
      <Row2 k="AGAIN" v="THE EXPLORER" />
    </Card2>
  </Shell>
);

const S20: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={SAFE && !isLive(TAKES.UI7B) ? [270] : [90, 270]}
    meta={[{ from: 0, tag: "CONSOLE SCREEN (UI)", todo: "UI-7 REPLAYED HERE", take: TAKES.UI7B, safeTag: "REPLAY OF A REAL RUN: BOT-A2'S GHOST FINISHES AHEAD" }, { from: 90, tag: "REPLAY OF A REAL RUN: BOT-A2'S GHOST FINISHES AHEAD" },
      { from: 270, tag: "HASHSCAN TESTNET (WEB): A REAL EARLIER SALE" }]}
    ls={lines(8, [[0.3, pick("Race a bought ghost, checked on the console first.", "Race a bought ghost, its run replayed first.")], [4.6, "A sale pays the runner's own Hedera account."]])}>
    <Board f={f} />
    <Win f={f} a={0} b={SAFE && !isLive(TAKES.UI7B) ? 0 : 90}>{(t) => (
      <>{SAFE && !isLive(TAKES.UI7B) ? <RecCrop file={REC.sample} from={13.4} crop={[180, 30, 620, 260]} x={PX} y={PY + 20} w={1180} f={t} /> : null}
      <Screen x={(W - 1100) / 2} y={PY} w={SAFE && !isLive(TAKES.UI7B) ? 0 : 1100}>
        <TakeOr take={TAKES.UI7B}><ConsolePH f={t} id="UI-7" title="Ghost loaded" rows={[["Replayed here", "<take: = N frames>"], ["", "same as the board"]]} accent={MW.green} /></TakeOr>
      </Screen></>
    )}</Win>
    <Win f={f} a={SAFE && !isLive(TAKES.UI7B) ? 0 : 90} b={270}>{(t) => <Race from={SAFE && !isLive(TAKES.UI7B) ? 110.5 : 112.0} f={t} duck={() => true} />}</Win>
    <Win f={f} a={270} b={480}>{(t) => (
      <>
        <Web f={t} src="final/web/hashscan_payment_human.png" focus={[0, 70, 1600, 560]} focus2={[50, 930, 780, 70]} at2={40} to={[0, TOP + 54, W, 620]} />
        <Url f={t} at={14} text="hashscan.io/testnet/transaction/0.0.9185802-1793930445-643007633" x={60} y={TOP + 2} s={24} />
        <Card2 f={t} at={90} x={CX} y={TOP + 74} w={CW} h={150} head="A SALE" accent={MW.green} headCol={MW.green}>
          <Row2 k="0.10 USDC TO" v="0.0.9473064" />
          <Row2 k="WHOSE" v="ANY-6PS'S" c={MW.amber} />
        </Card2>
      </>
    )}</Win>
  </Shell>
);

/* ---------------- 21. The handheld: assembly and parts ---------------- */
/** MachineSubs' lines (src/acts/MachineSubs.tsx, local frame = Briefing frame - 120), at the film's 44 px. */
const MS: Line[] = [
  { at: 240, len: 190, who: "Handler", text: "Fifty-nine parts, from the shell to the screws." },
  { at: 900, len: 230, who: "Handler", text: "A five-inch touchscreen, and a Raspberry Pi to run the games." },
  { at: 1690, len: 195, who: "Handler", text: "And every input, every frame, is written to a log." },
];
const ASM: { a: number; b: number; subTo: number }[] = [{ a: 160, b: 560, subTo: 560 }, { a: 1020, b: 1490, subTo: 1260 }, { a: 1800, b: 2010, subTo: 2010 }];
const MachineLine: React.FC<{ g: number }> = ({ g }) => {
  const l = MS.find((q) => g - 120 >= q.at && g - 120 < q.at + q.len);
  if (!l) return null;
  return (
    <div style={{ position: "absolute", left: 380, right: 20, bottom: BAR + 36, textAlign: "center", fontFamily: FONT.sub, fontWeight: 600, fontSize: 44,
      color: "#f4f4f2", textShadow: "0 2px 8px rgba(0,0,0,0.95), 0 0 3px rgba(0,0,0,0.9)" }}>
      <span style={{ display: "inline-block", padding: "14px 60px 16px", background: "radial-gradient(ellipse at 50% 55%, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.55) 55%, rgba(0,0,0,0) 80%)" }}>
        <span style={{ color: MW.blue }}>{l.who}: </span>{l.text}
      </span>
    </div>
  );
};
const S21: React.FC<{ f: number }> = ({ f }) => {
  let g = 0, acc = 0, subTo = 0;
  for (const s of ASM) { if (f < acc + (s.b - s.a)) { g = s.a + (f - acc); subTo = s.subTo; break; } acc += s.b - s.a; }
  return (
    <Shell f={f} meta={[{ from: 0, tag: "CAD RENDER (EARLIER FILM)" }]}>
      <Series>
        {ASM.map(({ a, b }) => (
          <Series.Sequence key={a} durationInFrames={b - a}>
            <OffthreadVideo src={staticFile("final/acts/briefing_120.mp4")} trimBefore={a - 120} muted style={{ width: "100%", height: "100%" }} />
          </Series.Sequence>
        ))}
      </Series>
      {g < subTo ? <MachineLine g={g} /> : null}
    </Shell>
  );
};

/* ---------------- 22. Close: three sponsors, one line each ---------------- */
const CLOSE = [
  { at: 18, k: "WORLD", v: "Consoles exclusive to humans." },
  { at: 120, k: "ARKIV", v: "The console owns its record." },
  { at: 222, k: "HEDERA", v: "An agent that pays, within code limits." },
];
const S22: React.FC<{ f: number }> = ({ f }) => (
  <Shell f={f} cuts={[540]} meta={[{ from: 0, tag: "CAD RENDER + CONSOLE SCREEN (UI): THE BOARD", todo: "HAND-5", take: TAKES.HAND5, liveTag: "THE HANDHELD (HAND)" }, { from: 540, tag: "" }]}>
    <Win f={f} a={0} b={540}>{(t) => (
      <>
        <AbsoluteFill><TakeOr take={TAKES.HAND5} keep><C3D id="s22" t={t} /></TakeOr></AbsoluteFill>
        <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.5) 52%, rgba(0,0,0,0.72) 100%)" }} />
        {CLOSE.map((c, i) => (
          <Card2 key={c.k} f={t} at={c.at} x={1000} y={PY + i * 150} w={860} h={132} head={c.k}>
            <div style={{ fontFamily: "Archivo Black", fontSize: 30, color: MW.text, letterSpacing: "0.01em", lineHeight: 1.1 }}>{c.v}</div>
          </Card2>
        ))}
        {t >= 360 ? (
          <div style={{ position: "absolute", left: 1000, right: 40, top: PY + 470, clipPath: `inset(0 ${100 - 100 * easeOutExpo(prog(t, 360, 380))}% 0 0)` }}>
            <Mono s={44} c={MW.ice} w={700} ls="0">chrsnikhil.github.io/anypercent</Mono>
          </div>
        ) : null}
      </>
    )}</Win>
    <Sequence from={540} durationInFrames={120}>
      <OffthreadVideo src={staticFile("final/acts/title_end.mp4")} trimBefore={120} muted style={{ width: "100%", height: "100%" }} />
    </Sequence>
  </Shell>
);

const SCENES: React.FC<{ f: number }>[] = [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22];
const Scene: React.FC<{ C: React.FC<{ f: number }> }> = ({ C }) => <C f={useCurrentFrame()} />;

export const FinalDemo: React.FC = () => (
  <AbsoluteFill style={{ background: "#000" }}>
    <Series>
      {SC.scenes.map((s, i) => (
        <Series.Sequence key={s.n} durationInFrames={s.len} name={`${s.n}. ${s.name}`}>
          <Scene C={SCENES[i]} />
        </Series.Sequence>
      ))}
    </Series>
    {SOUND ? <Audio src={staticFile("final/audio/final_demo.wav")} /> : null}
  </AbsoluteFill>
);

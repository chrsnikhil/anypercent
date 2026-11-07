import React from "react";
import { getInputProps, getStaticFiles, Img, OffthreadVideo, staticFile } from "remotion";
import { MW } from "../acts/common";

/* The live takes the film still waits for, one constant each (video/final/SCRIPT.md shot ids). To swap one in, drop
   its file at public/final/live/<file>.mp4 (or .mov, .webm, .png, .jpg) and render again: the slot plays the file
   instead of its placeholder, and the top bar's TODO(live) for it disappears. `from` is where the slot starts in the
   file, in seconds; `fit` is how it fills its box. No other code changes. */

/** SAFE (render with --props=out/final_props.json, {"safe": true}): every take not shot yet plays its best real
    stand-in, with honest captions and no TODO(live) or PLACEHOLDER marks, so a submittable cut exists without the live
    takes. A live file still wins over its stand-in. Off by default (the loop's working cut shows what is missing). */
export const SAFE: boolean = (() => {
  try { return Boolean((getInputProps() as { safe?: boolean }).safe); } catch { return false; }
})();
export const pick = <V,>(normal: V, safe: V): V => (SAFE ? safe : normal);
/** LIVE (props {"safe": true, "live": true}): the owner's real recordings of 7 Nov sit beside the film's version of each
    sponsor beat (src/final/live.ts). They back the switch-era claims, so captions use the normal wording (cap), while
    the left side keeps SAFE's real stand-ins (no placeholders). */
export const LIVE: boolean = (() => {
  try { return Boolean((getInputProps() as { live?: boolean }).live); } catch { return false; }
})();
export const cap = <V,>(normal: V, safe: V): V => (LIVE ? normal : SAFE ? safe : normal);

export type Take = { id: string; file: string; from: number; fit?: "contain" | "cover"; what: string };
const T = (id: string, file: string, what: string, from = 0, fit: "contain" | "cover" = "contain"): Take => ({ id, file, from, fit, what });

export const TAKES = {
  HAND1: T("HAND-1", "hand1_wake", "the handheld lifted into frame, waking on Home (scene 4)", 0, "cover"),
  TERM1: T("TERM-1", "term1_replay", "arcade_replay true, one byte, false (scene 4)"),
  UI4A: T("UI-4a", "ui4a_need_book", "fresh console: Record book needed (scene 5)"),
  UI4B: T("UI-4b", "ui4b_signup", "fresh console: QR, waiting, Already registered (scene 6)"),
  PHONE1: T("PHONE-1", "phone1_signup_again", "World App's own answer to a second sign-up (scene 6)"),
  PHONE2: T("PHONE-2", "phone2_listing", "World App: the listing text, then Approve (scene 7)"),
  UI6A: T("UI-6a", "ui6_approve", "Approve on your phone, with the QR (scene 7)"),
  UI6B: T("UI-6b", "ui6_listing", "Recording on Hedera, Listing on Arkiv (scene 7)"),
  TERM6: T("TERM-6", "term6_link", "npm run console:link, the text naming the wallet (scene 8)"),
  PHONE3: T("PHONE-3", "phone3_link", "World App: link console C-QP6P (wallet ...), Approve (scene 8)"),
  UI3B: T("UI-3b", "ui3b_book_wallet", "the book card with the console's wallet line (scene 8)"),
  WEB6: T("WEB-6", "web6_console_tx", "the console's tx on the Arkiv explorer (scene 9)"),
  WEB7: T("WEB-7", "web7_stamp", "the stamp entity on the Arkiv explorer (scene 10)"),
  UI2A: T("UI-2a", "ui2_board", "the board after the switch, ranking stamped runs (scene 10)"),
  WEB8: T("WEB-8", "web8_run_stamp", "run and stamp entities side by side (scene 11)"),
  WEB9A: T("WEB-9a", "web9_board", "the stamp-reading public board (scene 12)", 0, "cover"),
  TERM2: T("TERM-2", "term2_query", "the README's stamp query with curl (scene 12)"),
  WEB10A: T("WEB-10a", "web10_arkiv_folder", "the repo's /arkiv folder (scene 12)"),
  TERM3: T("TERM-3", "term3_lookalike", "npm run arkiv:lookalike (scene 13)"),
  UI2B: T("UI-2b", "ui2_bot_rows", "the board's BOT rows after the switch (scene 13)"),
  UI7A: T("UI-7a", "ui7_pay", "checking, paying, loading, Ghost loaded (scene 15)"),
  TERM7: T("TERM-7", "term7_evil402", "npm run hedera:evil402: REFUSED payTo (scene 17)"),
  TERM8: T("TERM-8", "term8_verify", "npm run hedera:verify: VERIFIED (scene 17)"),
  TERM9: T("TERM-9", "term9_no_solidity", "git ls-files '*.sol' | wc -l: 0 (scene 17)"),
  WEB10B: T("WEB-10b", "web10_readme_ids", "the README's Hedera on-chain ids (scene 17)"),
  WEB9B: T("WEB-9b", "web9_board_phone", "the public board on a phone or browser (scene 18)", 0, "cover"),
  HAND3: T("HAND-3", "hand3_records", "on the handheld: a run's records, the explorer, back (scene 19)", 0, "cover"),
  UI7B: T("UI-7b", "ui7_replayed", "Ghost loaded: Replayed on this console (scene 20)"),
  HAND5: T("HAND-5", "hand5_board", "the board on the handheld, held 12 s (scene 22)", 0, "cover"),
} as const;

/** The take's file under public/, or null while it is not there (the bundle lists public/ when it is made). */
export const liveFile = (t: Take): string | null => {
  const names = new Set(getStaticFiles().map((f) => f.name.replace(/\\/g, "/")));
  for (const ext of [".mp4", ".mov", ".webm", ".png", ".jpg"]) {
    const n = `final/live/${t.file}${ext}`;
    if (names.has(n)) return n;
  }
  return null;
};
export const isLive = (t?: Take) => !!t && liveFile(t) !== null;

/** The live take filling its parent, or the placeholder. */
/** keep: the fallback is itself real footage (a 3D clip, a real still), so SAFE keeps it. */
export const TakeOr: React.FC<{ take: Take; children: React.ReactNode; safe?: React.ReactNode; keep?: boolean }> = ({ take, children, safe, keep }) => {
  const f = liveFile(take);
  if (!f) return <>{SAFE ? (safe !== undefined ? safe : keep ? children : null) : children}</>;
  const style: React.CSSProperties = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: take.fit ?? "contain", background: "#050607" };
  return /\.(png|jpg)$/.test(f) ? <Img src={staticFile(f)} style={style} />
    : <OffthreadVideo src={staticFile(f)} trimBefore={Math.round(take.from * 60)} muted style={style} />;
};

/** A positioned box holding a take or, until it exists, its placeholder (drawn at 0, 0 of the box). */
export const Slot: React.FC<{ take: Take; x: number; y: number; w: number; h: number; children: React.ReactNode; safe?: React.ReactNode; keep?: boolean }> = ({ take, x, y, w, h, children, safe, keep }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, ...(isLive(take) ? { overflow: "hidden", border: `2px solid ${MW.faint}`, borderRadius: 8 } : {}) }}>
    <TakeOr take={take} safe={safe} keep={keep}>{children}</TakeOr>
  </div>
);

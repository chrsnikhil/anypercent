import { HANDHELD, LAPTOP, LiveWin, PHONE } from "./split";

/* Which live recording sits beside which beat (scene number -> windows in scene frames, 60 fps). In-points from
   video/final/CLIPS_A.md / CLIPS_B.md and frame checks of the proxies in public/final/live_clips/ (all muted). Slates and
   the reused acts stay full frame. The World App recording is cropped to its verification sheet only (no profile, no
   promo image, no identifiers). */
const PH = 720 / 1564;                                  // the World App screen recording's proxy aspect
const SHEET: [number, number, number, number] = [0, 0.6, 1, 0.38];

export const LIVE_WINS: Record<number, LiveWin[]> = {
  4: [{ a: 0, b: 240, clip: "IMG_2890", at: 0.5, note: "THE HANDHELD: ITS MENU, THEN LIVE GAMEPLAY" }],
  5: [
    { a: 60, b: 420, clip: "IMG_2896", at: 69.0, note: "THE REAL BOOK: ANY-6PS, ORB, CONSOLE C-FMHE LINKED" },
    { a: 420, b: 600, clip: "IMG_2895", at: 28.0, note: "A CONSOLE WITH NO BOOK: RECORD BOOK NEEDED" },
  ],
  6: [{ a: 0, b: 660, clip: "IMG_2895", at: 63.5, note: "SAME PERSON, SECOND SIGN-UP: ALREADY REGISTERED" }],
  7: [
    { a: 0, b: 480, clip: "XGDA1280", at: 12.0, label: PHONE, crop: SHEET, ar: PH, note: "THE LISTING, APPROVED IN WORLD APP" },
    { a: 480, b: 840, clip: "IMG_2896", at: 199.0, note: "THE CONSOLE ASKS, THE OWNER APPROVES ON THE PHONE" },
  ],
  8: [
    { a: 0, b: 300, clip: "IMG_2896", at: 0.0, note: "THE LINK TEXT NAMES THE CONSOLE'S WALLET 0xda28...2f89" },
    { a: 300, b: 480, clip: "IMG_2896", at: 71.0, note: "THE BOOK CARD NOW SHOWS THAT WALLET" },
  ],
  9: [
    { a: 60, b: 230, clip: "IMG_2896", at: 120.0, note: "LISTING ON ARKIV, FROM THE CONSOLE" },
    { a: 230, b: 660, clip: "IMG_2896", at: 352.0, note: "ITS RUN ON THE ARKIV EXPLORER: OWNER 0xdA28...2f89" },
  ],
  10: [
    { a: 0, b: 360, clip: "IMG_2896", at: 443.0, note: "THE CHECKER'S STAMP ON THE ARKIV EXPLORER" },
    { a: 360, b: 660, clip: "IMG_2896", at: 538.0, note: "THE BOARD ON THE HANDHELD" },
  ],
  11: [{ a: 0, b: 540, clip: "IMG_5143", at: 0.0, label: LAPTOP, note: "THE SERVER TRIES TO EDIT AND DELETE THE CONSOLE'S RUN: BOTH REFUSED" }],
  12: [{ a: 0, b: 240, clip: "IMG_2896", at: 604.0, note: "THE PUBLIC BOARD, ON THE HANDHELD'S BROWSER" }],
  13: [{ a: 230, b: 480, clip: "IMG_2896", at: 538.0, note: "THE BOARD: BOT ROWS LABELLED BOT" }],
  14: [
    { a: 60, b: 366, clip: "IMG_2897", at: 58.0, note: "THE SCOUT ON THE HANDHELD" },
    { a: 366, b: 492, clip: "IMG_2897", at: 65.0, note: "THE MODEL PICKS BOT-A3" },
    { a: 492, b: 720, clip: "IMG_2897", at: 146.0, note: "ALREADY OWNED: LOADED, NOTHING PAID" },
  ],
  15: [
    { a: 0, b: 420, clip: "IMG_5144", at: 0.0, label: LAPTOP, note: "A NEW PURCHASE: PB'S AGENT, NO HUMAN" },
    { a: 420, b: 660, clip: "IMG_2897", at: 362.0, note: "HASHSCAN, OPENED ON THE HANDHELD" },
  ],
  16: [{ a: 0, b: 600, clip: "IMG_2897", at: 192.0, note: "PB'S PAYMENTS ON HASHSCAN, OPENED ON THE HANDHELD" }],
  17: [{ a: 0, b: 480, clip: "IMG_5145", at: 0.0, label: LAPTOP, note: "A PAYWALL NAMING ANOTHER ACCOUNT: REFUSED, NOTHING SIGNED" }],
  18: [{ a: 60, b: 480, clip: "IMG_2896", at: 610.0, note: "THE PUBLIC BOARD, ON THE HANDHELD'S BROWSER" }],
  19: [{ a: 0, b: 480, clip: "IMG_2896", at: 556.0, note: "A RUN'S RECORDS, ONE PRESS AWAY: ARKIV, HEDERA LISTING #17" }],
  20: [{ a: 0, b: 270, clip: "IMG_2898", at: 100.0, note: "THE OWNER RACES THE BOUGHT GHOST ON THE HANDHELD" }],
};
export { HANDHELD };

#!/bin/bash
# Render the v3 acts one after another (heavy jobs one at a time). Usage: bash render_acts.sh [Comp ...]
cd "$(dirname "$0")"
R="--codec=prores --prores-profile=hq --gl=angle --concurrency=${CONC:-3} --log=error"
# A submission-cut act differs from its full-cut render only in the PART label on its first card, so render just the
# card and splice it onto the full render (ProRes is intra-only: a stream copy cuts on the exact frame).
splice() {  # splice CARD_MOV FULL_MOV OUT_MOV FRAMES
  printf "file '%s'\nfile '%s'\ninpoint %s\n" "$(basename "$1")" "$(basename "$2")" "$(python -c "print($4/60)")" > out/splice.txt
  ffmpeg -v error -y -f concat -safe 0 -i out/splice.txt -c copy "$3" && rm out/splice.txt "$1"
}
ACTS=${@:-ColdOpen Teaser Primer Breaks MachineSubs GameReel Proof Objectives Coda Chapters}
for a in $ACTS; do
  t=$(date +%s)
  case $a in
    ColdOpen) npx remotion render src/index.ts ColdOpen out/cold_raw.mov $R ;;
    Breaks) npx remotion render src/index.ts Breaks out/breaks_raw.mov $R ;;
    Proof) npx remotion render src/index.ts Proof out/proof_raw.mov $R ;;
    Objectives) npx remotion render src/index.ts Objectives out/obj_raw.mov $R ;;
    Coda) npx remotion render src/index.ts Coda out/coda_raw.mov $R ;;
    Teaser) npx remotion render src/index.ts ProofTeaser out/teaser_raw.mov $R ;;
    Primer) npx remotion render src/index.ts Primer out/primer_raw.mov $R ;;
    GameReel) npx remotion render src/index.ts GameReel out/reel_raw.mov $R ;;
    Check) npx remotion render src/index.ts Check out/check_raw.mov $R ;;
    Coach) npx remotion render src/index.ts Coach out/coach_raw.mov $R ;;
    Handler) npx remotion render src/index.ts Handler out/handler_raw.mov $R ;;
    Flash) npx remotion render src/index.ts ProofFlash out/flash_raw.mov $R ;;
    # the submission cut drops Part I (the dossier), so its act cards are renumbered
    # the submission cut also plays Part I at its v3 pace, so it is a render of its own, not a spliced card
    BreaksSub) npx remotion render src/index.ts BreaksSub out/breaks_sub_raw.mov $R ;;
    ReelShort) npx remotion render src/index.ts GameReelShort out/reel_short_raw.mov $R ;;
    ProofSub) npx remotion render src/index.ts Proof out/proof_card.mov $R --frames=0-71 --props='{"part":"PART III"}' &&
      splice out/proof_card.mov out/proof_raw.mov out/proof_sub_raw.mov 72 ;;
    ObjSub) npx remotion render src/index.ts Objectives out/obj_card.mov $R --frames=0-47 --props='{"part":"PART IV"}' &&
      splice out/obj_card.mov out/obj_raw.mov out/obj_sub_raw.mov 48 ;;
    Dossier) npx remotion render src/index.ts Dossier out/dossier_raw.mov $R ;;
    Titles) npx remotion render src/index.ts TitleOpen out/title_open_raw.mov $R &&
      npx remotion render src/index.ts TitleEnd out/title_end_raw.mov $R ;;
    # a new act slate only: re-render the lead frames and splice them onto the act's existing render, in place
    BreaksLead) npx remotion render src/index.ts Breaks out/breaks_card.mov $R --frames=0-62 &&
      splice out/breaks_card.mov out/breaks_raw.mov out/breaks_new.mov 63 && mv -f out/breaks_new.mov out/breaks_raw.mov ;;
    BreaksSubLead) npx remotion render src/index.ts BreaksSub out/breaks_card.mov $R --frames=0-49 &&
      splice out/breaks_card.mov out/breaks_sub_raw.mov out/breaks_new.mov 50 && mv -f out/breaks_new.mov out/breaks_sub_raw.mov ;;
    Briefing) npx remotion render src/index.ts Briefing out/briefing_raw.mov $R ;;
    ChaptersSub) npx remotion render src/index.ts Chapter out/ch2s_raw.mov $R --props='{"part":"PART II","title":"THE MACHINE"}' ;;
    MachineSubs) npx remotion render src/index.ts MachineSubs out/machine_subs.mov --codec=prores --prores-profile=4444 \
      --pixel-format=yuva444p10le --image-format=png --gl=angle --concurrency=4 --log=error ;;
    Chapters)
      npx remotion render src/index.ts Chapter out/ch1_raw.mov $R --props='{"part":"PART I","title":"THE CASE FILES"}'
      npx remotion render src/index.ts Chapter out/ch3_raw.mov $R --props='{"part":"PART III","title":"THE MACHINE"}' ;;
  esac
  echo "$a done in $(( $(date +%s) - t )) s"
done

import React from "react";
import { Composition } from "remotion";
import { Briefing } from "./Briefing";
import { Board, Dossier } from "./dossier/Dossier";
import DD from "./dossier/dossier.json";
import { TitleCard, TitleEnd, TitleOpen } from "./dossier/TitleCard";
import { TL } from "./theme";
import { Coda, CODA_LEN, COLD_LEN, ColdOpen } from "./acts/ColdOpen";
import { Proof, PROOF_LEN, ProofTeaser, TEASER_LEN } from "./acts/Proof";
import { Breaks, BREAKS_LEN } from "./acts/Breaks";
import { OBJ_LEN, Objectives } from "./acts/Objectives";
import { Chapter, CHAPTER_LEN } from "./acts/Chapter";
import { Primer, PRIMER_LEN } from "./acts/Primer";
import { MACHINE_LEN, MachineSubs } from "./acts/MachineSubs";
import { GameReel, REEL_LEN, REEL_SHORT_LEN, SHORT_SHOT } from "./acts/GameReel";
import { Check, CHECK_LEN } from "./acts/Check";
import { Coach, COACH_LEN } from "./acts/Coach";
import { Handler, HANDLER_LEN } from "./acts/Handler";
import { Poster } from "./acts/Poster";
import { FLASH_LEN, ProofFlash } from "./acts/ProofFlash";
import { Prompter, PROMPTER_H, PROMPTER_LEN, PROMPTER_W } from "./acts/Prompter";
import { FIELD_LEN, FieldTape } from "./acts/FieldTape";
import { ARKIV_LEN, ArkivAct } from "./sponsors/arkiv/Act";
import { HEDERA_LEN, HederaAct } from "./sponsors/hedera/Act";
import { CHAINLINK_LEN, ChainlinkAct } from "./sponsors/chainlink/Act";
import { WORLD_LEN, WorldAct } from "./sponsors/world/Act";
import { FINAL_LEN, FinalDemo } from "./final/FinalDemo";
import { Console3DShot, SHOTS_3D } from "./final/console3d";

export const Root: React.FC = () => (
  <>
    <Composition id="Briefing" component={Briefing} durationInFrames={TL.duration} fps={TL.fps} width={TL.width} height={TL.height} />
    <Composition id="BoardPlate" component={() => <Board f={0} plate />} durationInFrames={1} fps={60} width={4800} height={2800} />
    <Composition id="Title" component={TitleCard} durationInFrames={150} fps={60} width={TL.width} height={TL.height} />
    <Composition id="TitleOpen" component={TitleOpen} durationInFrames={150} fps={60} width={TL.width} height={TL.height} />
    <Composition id="TitleEnd" component={TitleEnd} durationInFrames={240} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Dossier" component={Dossier} durationInFrames={DD.duration} fps={DD.fps} width={TL.width} height={TL.height} />
    <Composition id="ColdOpen" component={ColdOpen} durationInFrames={COLD_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Proof" component={Proof} durationInFrames={PROOF_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Breaks" component={Breaks} durationInFrames={BREAKS_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Objectives" component={Objectives} durationInFrames={OBJ_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Chapter" component={Chapter} durationInFrames={CHAPTER_LEN} fps={60} width={TL.width} height={TL.height} defaultProps={{ part: "PART I", title: "THE CASE FILES" }} />
    <Composition id="Coda" component={Coda} durationInFrames={CODA_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="ProofTeaser" component={ProofTeaser} durationInFrames={TEASER_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Primer" component={Primer} durationInFrames={PRIMER_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="MachineSubs" component={MachineSubs} durationInFrames={MACHINE_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="GameReel" component={GameReel} durationInFrames={REEL_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="GameReelShort" component={GameReel} durationInFrames={REEL_SHORT_LEN} fps={60} width={TL.width} height={TL.height} defaultProps={{ shot: SHORT_SHOT }} />
    <Composition id="BreaksSub" component={Breaks} durationInFrames={1340} fps={60} width={TL.width} height={TL.height} defaultProps={{ part: "PART I", slow: 1 }} />
    <Composition id="Check" component={Check} durationInFrames={CHECK_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Coach" component={Coach} durationInFrames={COACH_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Handler" component={Handler} durationInFrames={HANDLER_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="ProofFlash" component={ProofFlash} durationInFrames={FLASH_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="Poster" component={Poster} durationInFrames={PROOF_LEN} fps={60} width={TL.width} height={TL.height} defaultProps={{ title: true }} />
    <Composition id="FieldTape" component={FieldTape} durationInFrames={FIELD_LEN} fps={60} width={TL.width} height={TL.height} />
    {/* the sponsor demos' own acts (SPONSOR_DEMOS.md, post_sponsor.py) */}
    <Composition id="SponsorArkiv" component={ArkivAct} durationInFrames={ARKIV_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="SponsorHedera" component={HederaAct} durationInFrames={HEDERA_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="SponsorChainlink" component={ChainlinkAct} durationInFrames={CHAINLINK_LEN} fps={60} width={TL.width} height={TL.height} />
    <Composition id="SponsorWorld" component={WorldAct} durationInFrames={WORLD_LEN} fps={60} width={TL.width} height={TL.height} />
    {/* the final submission film (video/final/SCRIPT.md, LOOP.md) */}
    <Composition id="FinalDemo" component={FinalDemo} durationInFrames={FINAL_LEN} fps={60} width={TL.width} height={TL.height} />
    {SHOTS_3D.map((s) => <Composition key={s.id} id={`FinalC3D-${s.id}`} component={Console3DShot} durationInFrames={s.len} fps={60} width={TL.width} height={TL.height} defaultProps={{ id: s.id }} />)}
    <Composition id="Prompter" component={Prompter} durationInFrames={PROMPTER_LEN} fps={60} width={PROMPTER_W} height={PROMPTER_H} />
  </>
);

import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { AgentsIllo, ChapterCard, CloseIllo, CostIllo, GapIllo, Logo, MapIllo, NetworkIllo, StandardsIllo } from "./Illustrations";
import { PhoneScene, ScreenScene } from "./Screens";
import { C, FONT } from "./theme";
import { SCENES, TRANSITION, type Scene } from "./timeline";

const Backdrop: React.FC = () => {
  const f = useCurrentFrame();
  const drift = Math.sin(f / 240) * 40;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(1200px 800px at ${30 + drift / 10}% 20%, ${C.navy} 0%, ${C.night} 60%), ${C.night}`,
      }}
    />
  );
};

const Chapter: React.FC<{ text: string }> = ({ text }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [8, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 150, top: 24, fontFamily: FONT, fontSize: 22, letterSpacing: 3, textTransform: "uppercase", color: C.sky, fontWeight: 700, opacity: o }}>
      {text}
    </div>
  );
};

/** Captions in short groups of words, timed evenly across the spoken line. */
const Caption: React.FC<{ text: string; frames: number }> = ({ text, frames }) => {
  const f = useCurrentFrame();
  const sentences = text.match(/[^.!?]+[.!?]?/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
  const total = sentences.reduce((n, s) => n + s.length, 0);
  const speak = frames - TRANSITION - 15;
  let start = 6;
  for (const s of sentences) {
    const len = Math.max(30, (s.length / total) * speak);
    if (f < start + len) {
      const o = interpolate(f, [start, start + 6, start + len - 6, start + len], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
      return (
        <div style={{ position: "absolute", bottom: 40, left: 260, right: 260, textAlign: "center", opacity: o }}>
          <span style={{ fontFamily: FONT, fontSize: 30, color: C.white, background: "rgba(5,10,28,0.78)", padding: "10px 22px", borderRadius: 12, lineHeight: 1.5, boxDecorationBreak: "clone" }}>
            {s}
          </span>
        </div>
      );
    }
    start += len;
  }
  return null;
};

const Visual: React.FC<{ scene: Scene }> = ({ scene }) => {
  switch (scene.visual) {
    case "logo": return <Logo />;
    case "chapter": return <ChapterCard number={scene.text} title={scene.chapter} />;
    case "illo-map": return <MapIllo />;
    case "illo-gap": return <GapIllo />;
    case "illo-cost": return <CostIllo />;
    case "illo-network": return <NetworkIllo />;
    case "illo-standards": return <StandardsIllo />;
    case "illo-agents": return <AgentsIllo />;
    case "illo-close": return <CloseIllo />;
    case "screen": return scene.clip ? <ScreenScene clip={scene.clip} frames={scene.frames} /> : null;
    case "phone": return scene.clip ? <PhoneScene clip={scene.clip} frames={scene.frames} behind={scene.behind} /> : null;
    default: return null;
  }
};

const SceneView: React.FC<{ scene: Scene }> = ({ scene }) => (
  <AbsoluteFill>
    <Backdrop />
    <Visual scene={scene} />
    {(scene.visual === "screen" || scene.visual === "phone") && <Chapter text={scene.chapter} />}
    {scene.audio && <Caption text={scene.text} frames={scene.frames} />}
    {scene.audio && (
      <Sequence from={8}>
        <Audio src={staticFile(scene.audio)} />
      </Sequence>
    )}
  </AbsoluteFill>
);

export const Film: React.FC = () => (
  <AbsoluteFill style={{ background: C.night }}>
    <TransitionSeries>
      {SCENES.map((scene, i) => {
        const next = SCENES[i + 1];
        // Slide when the stage changes kind (screen ↔ phone ↔ illustration); fade within a kind.
        const kind = (s: Scene) => (s.visual === "screen" || s.visual === "phone" ? s.visual : "illo");
        const presentation = next && kind(next) !== kind(scene) ? slide({ direction: "from-right" }) : fade();
        return (
          <React.Fragment key={scene.id}>
            <TransitionSeries.Sequence durationInFrames={scene.frames}>
              <SceneView scene={scene} />
            </TransitionSeries.Sequence>
            {next && (
              <TransitionSeries.Transition presentation={presentation} timing={linearTiming({ durationInFrames: TRANSITION })} />
            )}
          </React.Fragment>
        );
      })}
    </TransitionSeries>
  </AbsoluteFill>
);

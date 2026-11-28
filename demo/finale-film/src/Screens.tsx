import React from "react";
import { AbsoluteFill, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "./theme";
import type { Clip } from "./timeline";

/** Fit the clip's usable span to the scene: speed it up when it is long, never below 0.8x. */
function rateFor(clip: Clip, frames: number, fps: number): number {
  const span = clip.to - clip.from;
  return Math.min(2.2, Math.max(0.8, span / (frames / fps)));
}

/** Screen recordings are 1600x1112; the frame is sized to that, so nothing is cropped. */
const SCREEN_RATIO = 1600 / 1112;
const VIDEO_H = 822;
const VIDEO_W = Math.round(VIDEO_H * SCREEN_RATIO);
const BAR_H = 44;
/** The phone records at 1080x2340. */
const PHONE_INNER_H = 902;
const PHONE_INNER_W = Math.round((PHONE_INNER_H * 1080) / 2340);

const Chrome: React.FC<{ label: string; ratio?: number; children: React.ReactNode }> = ({ label, ratio, children }) => (
  <div
    style={{
      width: ratio ? Math.round(VIDEO_H * ratio) : VIDEO_W, height: VIDEO_H + BAR_H, borderRadius: 18, overflow: "hidden", background: C.white,
      boxShadow: "0 40px 90px rgba(4,10,30,0.45), 0 0 0 1px rgba(255,255,255,0.08)",
      display: "flex", flexDirection: "column",
    }}
  >
    <div style={{ height: BAR_H, background: "#E9EDF5", display: "flex", alignItems: "center", gap: 10, padding: "0 18px" }}>
      {["#F87171", "#FBBF24", "#34D399"].map((c) => (
        <div key={c} style={{ width: 13, height: 13, borderRadius: 7, background: c }} />
      ))}
      <div style={{ marginLeft: 16, fontFamily: FONT, fontSize: 17, color: "#475569", fontWeight: 600 }}>{label}</div>
    </div>
    <div style={{ flex: 1, position: "relative" }}>{children}</div>
  </div>
);

export const ScreenVideo: React.FC<{ clip: Clip; frames: number; style?: React.CSSProperties }> = ({ clip, frames, style }) => {
  const { fps } = useVideoConfig();
  return (
    <OffthreadVideo
      src={staticFile(`clips/${clip.file}`)}
      startFrom={Math.round(clip.from * fps)}
      playbackRate={rateFor(clip, frames, fps)}
      muted
      style={{ width: "100%", height: "100%", objectFit: "contain", ...style }}
    />
  );
};

const labelFor = (clip: Clip) =>
  clip.file.includes("openemr")
    ? "OpenEMR · the hospital's own system"
    : clip.file.includes("N3-apply")
      ? "Saathi partner app · apply to join"
      : "Saathi Control Centre";

export const ScreenScene: React.FC<{ clip: Clip; frames: number }> = ({ clip, frames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 24 });
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 62, transform: `translateY(${(1 - rise) * 40}px) scale(${0.96 + rise * 0.04})` }}>
      <Chrome label={labelFor(clip)} ratio={clip.ratio}>
        <ScreenVideo clip={clip} frames={frames} />
      </Chrome>
    </AbsoluteFill>
  );
};

/** The phone comes to the front; whatever screen came before is pushed back and blurred. */
export const PhoneScene: React.FC<{ clip: Clip; frames: number; behind?: Clip }> = ({ clip, frames, behind }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inn = spring({ frame, fps, config: { damping: 18, mass: 0.9 }, durationInFrames: 30 });
  const push = interpolate(frame, [0, 24], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      {behind && (
        <AbsoluteFill
          style={{
            alignItems: "center", paddingTop: 62,
            transform: `scale(${1 - push * 0.08}) translateX(${-push * 260}px)`,
            filter: `blur(${push * 7}px) brightness(${1 - push * 0.35})`,
            opacity: 1 - push * 0.3,
          }}
        >
          <Chrome label={labelFor(behind)} ratio={behind.ratio}>
            <ScreenVideo clip={behind} frames={frames} />
          </Chrome>
        </AbsoluteFill>
      )}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingBottom: 70 }}>
        <div
          style={{
            width: PHONE_INNER_W + 28, height: PHONE_INNER_H + 28, borderRadius: 58, background: "#0A0A0A", padding: 14,
            boxShadow: "0 50px 120px rgba(0,0,0,0.55), 0 0 0 2px #2A2A2A",
            transform: `translateY(${(1 - inn) * 700}px) rotate(${(1 - inn) * 6}deg)`,
          }}
        >
          <div style={{ width: "100%", height: "100%", borderRadius: 46, overflow: "hidden", background: C.white, position: "relative" }}>
            <OffthreadVideo
              src={staticFile(`clips/${clip.file}`)}
              startFrom={Math.round(clip.from * fps)}
              playbackRate={rateFor(clip, frames, fps)}
              muted
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
            {clip.blurTop && clip.blurAfter !== undefined &&
              clip.from + (frame / fps) * rateFor(clip, frames, fps) >= clip.blurAfter && (
                <div
                  style={{
                    position: "absolute", left: 0, right: 0, top: 0, height: `${clip.blurTop * 100}%`,
                    backdropFilter: "blur(22px)", WebkitBackdropFilter: "blur(22px)",
                    background: "rgba(220,226,236,0.35)",
                  }}
                />
              )}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

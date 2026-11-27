import React from "react";
import { Composition } from "remotion";
import { Demo, Roadmap, nextFrames, totalFrames } from "./Demo";
import { FPS } from "./theme";

/**
 * One composition. The length is computed from the narration, so re-recording
 * the voice with a different engine or a reworded line changes the film's
 * duration automatically rather than leaving the last section clipped.
 */
export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Demo"
      component={Demo}
      durationInFrames={totalFrames()}
      fps={FPS}
      width={1920}
      height={1080}
    />
    {/* Rendered separately and concatenated, so appending a roadmap slide
        costs a minute rather than re-encoding nineteen minutes of video. */}
    <Composition
      id="Roadmap"
      component={Roadmap}
      durationInFrames={nextFrames()}
      fps={FPS}
      width={1920}
      height={1080}
    />
  </>
);

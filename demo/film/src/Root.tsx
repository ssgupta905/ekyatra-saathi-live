import React from "react";
import { Composition } from "remotion";
import { Demo, totalFrames } from "./Demo";
import { FPS } from "./theme";

/**
 * One composition. The length is computed from the narration, so re-recording
 * the voice with a different engine or a reworded line changes the film's
 * duration automatically rather than leaving the last section clipped.
 */
export const RemotionRoot: React.FC = () => (
  <Composition
    id="Demo"
    component={Demo}
    durationInFrames={totalFrames()}
    fps={FPS}
    width={1920}
    height={1080}
  />
);

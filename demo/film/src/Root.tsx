import React from "react";
import { Composition } from "remotion";
import { Built, Demo, Roadmap, builtFrames, nextFrames, totalFrames } from "./Demo";
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
    {/* The addendum. Its own composition for the same reason as the roadmap:
        four minutes of clips renders in minutes, and the nineteen-minute film
        it belongs after does not have to be touched. */}
    <Composition
      id="Built"
      component={Built}
      durationInFrames={builtFrames()}
      fps={FPS}
      width={1920}
      height={1080}
    />
  </>
);

import { Composition } from "remotion";
import { Film } from "./Film";
import { FPS, TOTAL_FRAMES } from "./timeline";

export const RemotionRoot: React.FC = () => (
  <Composition id="SaathiFinale" component={Film} durationInFrames={TOTAL_FRAMES} fps={FPS} width={1920} height={1080} />
);

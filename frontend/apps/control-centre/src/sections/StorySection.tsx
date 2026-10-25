import { useCallback, useEffect, useState } from "react";
import { stories, type Story } from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { StoryBar } from "../components/StoryBar";
import { StoryScorecard } from "../components/StoryScorecard";
import { StoryView } from "../components/StoryView";
import { useWorld } from "../world";

/**
 * The brief's two stories, as they happen: four lanes (desk, agents, navigator and
 * doctor, family), one dot per real event with what it cost, and a scorecard read
 * off the same stream. Advance runs the next beat; nothing here is scripted output.
 */
export function StorySection() {
  const world = useWorld();
  const [storyId, setStoryId] = useState<string | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [scripted, setScripted] = useState(true);

  const refresh = useCallback(() => {
    stories
      .state()
      .then((state) => {
        setScripted(state.scripted && state.stories.length > 0);
        const chosen = state.stories.find((s) => s.id === storyId) ?? state.stories[0] ?? null;
        setStory(chosen);
        if (chosen) setStoryId((current) => current ?? chosen.id);
      })
      .catch(() => setStory(null));
  }, [storyId]);

  useEffect(refresh, [refresh, world.cohortRevision]);

  if (!scripted) {
    return <Notice tone="calm">This world has no scripted stories (SAATHI_LIVE_SCRIPTED is off).</Notice>;
  }
  return (
    <div className="cc-story">
      <StoryBar selected={storyId} onSelect={setStoryId} onAdvanced={refresh} revision={world.cohortRevision} />
      {story && (
        <>
          <StoryView story={story} events={world.events} />
          <StoryScorecard story={story} events={world.events} />
        </>
      )}
    </div>
  );
}

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { stories as storyApi, type Story, type StoryState } from "@saathi/api-client";
import { Chip, Play, Spark, StepForward } from "@saathi/ui-web";

/**
 * The brief's "Press" column, on every screen.
 *
 * One control, always in the same place, that says who acts next and runs the
 * next beat when pressed. A presenter reading the brief's table does not have to
 * find the right console first — whichever persona is signed in, Advance is here,
 * and what it runs is the real method that persona would otherwise click.
 *
 * It is deliberately explicit about whose turn it is. "Next: Seema approves"
 * before the press means the audience knows what to watch for, and makes it
 * obvious afterwards that the system reacted rather than performed.
 */
export function StoryBar({
  selected,
  onSelect,
  onAdvanced,
  revision,
}: {
  selected: string | null;
  onSelect: (storyId: string) => void;
  onAdvanced: () => void;
  /** Bumped by the live stream so the bar refetches when the world moves. */
  revision: number;
}) {
  const [state, setState] = useState<StoryState | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    storyApi
      .state()
      .then(setState)
      .catch(() => setState(null));
  }, []);

  useEffect(refresh, [refresh, revision]);

  // Publish this bar's real height so anything else that sticks can clear it.
  // Hardcoding the number means guessing at rendered padding, and a guess that
  // is six pixels out puts the navigator's own tabs underneath the bar.
  useLayoutEffect(() => {
    const node = barRef.current;
    const root = document.documentElement;
    if (!node) {
      root.style.removeProperty("--story-bar-h");
      return;
    }
    const publish = () => {
      root.style.setProperty("--story-bar-h", `${Math.ceil(node.offsetHeight)}px`);
    };
    publish();
    const observer = new ResizeObserver(publish);
    observer.observe(node);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--story-bar-h");
    };
  }, [state]);

  if (!state || !state.scripted || state.stories.length === 0) return null;

  const current: Story | null =
    state.stories.find((s) => s.id === selected) ?? state.stories[0] ?? null;
  if (!current) return null;

  const advance = async () => {
    setBusy(true);
    setError(null);
    try {
      await storyApi.advance(current.id);
      refresh();
      onAdvanced();
    } catch (e) {
      setError(e instanceof Error ? e.message : "that did not run");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="story-bar" ref={barRef}>
      <div className="segmented" role="group" aria-label="Story">
        {state.stories.map((story) => (
          <button
            key={story.id}
            type="button"
            aria-pressed={story.id === current.id}
            onClick={() => onSelect(story.id)}
            title={story.title}
          >
            {story.who.split(" · ")[0]}
          </button>
        ))}
      </div>

      <div className="story-next">
        {current.done ? (
          <Chip tone="go">
            <span className="dot" />
            story complete — reset the world to run it again
          </Chip>
        ) : (
          <>
            <span className="story-when">{current.next?.at}</span>
            <span className="story-who">{current.next?.actor}</span>
            <span className="story-headline">{current.next?.headline}</span>
          </>
        )}
      </div>

      <span className="spacer" />

      {error && <Chip tone="critical">{error}</Chip>}

      <span className="story-progress mono">
        {current.index}/{current.total}
      </span>

      <button
        type="button"
        className="btn primary"
        disabled={busy || current.done}
        onClick={advance}
      >
        <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
          {current.index === 0 ? <Play /> : busy ? <Spark /> : <StepForward />}
        </span>
        {busy ? "running…" : current.index === 0 ? "Start the story" : "Advance"}
      </button>
    </div>
  );
}

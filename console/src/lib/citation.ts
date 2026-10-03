/**
 * A pointer from something on screen to the ledger row it came from.
 *
 * `n` counts clicks rather than identifying the row, so clicking the same
 * citation twice replays the jump. Without it the second click sets state to
 * a value it already holds, React skips the render, and the effect that does
 * the scrolling never runs — which reads to a navigator as a broken link.
 */
export interface Citation {
  id: string;
  n: number;
}

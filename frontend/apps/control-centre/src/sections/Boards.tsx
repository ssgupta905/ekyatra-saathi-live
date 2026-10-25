import { PlanBoardList } from "../components/PlanBoardList";
import { useWorld } from "../world";

/** Every family's pathway at once. The question a list cannot answer: what is waiting on what. */
export function Boards() {
  const world = useWorld();
  return <PlanBoardList revision={world.cohortRevision} />;
}

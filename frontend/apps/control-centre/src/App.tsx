import { useEffect } from "react";
import { usePersona } from "./session";
import { HOME, sectionsFor } from "./sections";
import { Shell } from "./Shell";
import { useRoute } from "./route";
import { useWorld } from "./world";
import { Approvals } from "./sections/Approvals";
import { Audit } from "./sections/Audit";
import { Boards } from "./sections/Boards";
import { Cohort } from "./sections/Cohort";
import { Configuration } from "./sections/Configuration";
import { Desk } from "./sections/Desk";
import { Families } from "./sections/Families";
import { Operator } from "./sections/Operator";
import { StorySection } from "./sections/StorySection";

/**
 * The hospital's control centre: one website, every staff role, each seeing the
 * screens their work uses. The family's side is a different product (their phone),
 * and the demo stage frames both.
 */
export default function App() {
  const { persona } = usePersona();
  const world = useWorld();
  const [route, go] = useRoute(HOME[persona.role]);
  const demo = (world.snapshot?.world ?? "demo") === "demo";
  const allowed = sectionsFor(persona.role, demo);

  // A persona switch or a pasted link can land on a screen this role does not use.
  const section = allowed.some((s) => s.id === route.section) ? route.section : HOME[persona.role];
  useEffect(() => {
    if (section !== route.section) go({ section, id: null, tab: null });
  }, [section, route.section, go]);

  const openFamily = (patientId: string, tab?: string) =>
    go({ section: "families", id: patientId, tab: tab ?? null });

  return (
    <Shell current={section} onNavigate={(next) => go({ section: next, id: null, tab: null })}>
      {section === "families" && <Families patientId={route.id} tab={route.tab} onOpen={openFamily} />}
      {section === "boards" && <Boards />}
      {section === "approvals" && <Approvals />}
      {section === "desk" && <Desk />}
      {section === "cohort" && <Cohort onOpen={(id) => openFamily(id)} />}
      {section === "story" && <StorySection />}
      {section === "operator" && <Operator />}
      {section === "config" && <Configuration />}
      {section === "audit" && <Audit />}
    </Shell>
  );
}

import { useEffect } from "react";
import { usePersona } from "./session";
import { HOME, SECTIONS, sectionsFor } from "./sections";
import { Shell } from "./Shell";
import { useRoute } from "./route";
import { useWorld } from "./world";
import { PageHeader, ToastProvider } from "./ui/kit";
import { Approvals } from "./sections/Approvals";
import { Audit } from "./sections/Audit";
import { Boards } from "./sections/Boards";
import { Cohort } from "./sections/Cohort";
import { Directory } from "./sections/Directory";
import { Configuration } from "./sections/Configuration";
import { Families } from "./sections/Families";
import { Issues } from "./sections/Issues";
import { Network } from "./sections/Network";
import { Onboarding } from "./sections/Onboarding";
import { Operator } from "./sections/Operator";
import { Records } from "./sections/Records";
import { Registries } from "./sections/Registries";
import { Releases } from "./sections/Releases";
import { Reports } from "./sections/Reports";
import { StorySection } from "./sections/StorySection";
import { Today } from "./sections/Today";

/** Screens that carry their own heading; the rest get the section's title and one line. */
const OWN_HEADING = new Set(["today", "families", "onboarding"]);

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
  // Old links to the retired "desk" screen land on the desk's new home for it.
  const asked = route.section === "desk" ? "issues" : route.section;
  const section = allowed.some((s) => s.id === asked) ? asked : HOME[persona.role];
  useEffect(() => {
    if (section !== route.section) go({ section, id: null, tab: null });
  }, [section, route.section, go]);

  const openFamily = (patientId: string, layer?: string) =>
    go({ section: "families", id: patientId, tab: layer ?? null });
  const navigate = (next: string) => go({ section: next, id: null, tab: null });
  const meta = SECTIONS.find((s) => s.id === section);

  return (
    <ToastProvider>
      <Shell current={section} onNavigate={navigate} onOpenFamily={openFamily}>
        {meta && !OWN_HEADING.has(section) && <PageHeader title={meta.label} lead={meta.hint} />}
        {section === "today" && <Today go={navigate} open={openFamily} />}
        {section === "families" && <Families patientId={route.id} layer={route.tab} onOpen={openFamily} />}
        {section === "network" && <Network onOpen={(id) => openFamily(id)} />}
        {section === "approvals" && <Approvals />}
        {section === "issues" && <Issues />}
        {section === "releases" && <Releases />}
        {section === "onboarding" && <Onboarding patientId={route.id} onOpen={(id) => go({ section: "onboarding", id })} />}
        {section === "records" && <Records />}
        {section === "boards" && <Boards />}
        {section === "reports" && <Reports onOpenFamily={(id) => openFamily(id, "reports")} />}
        {section === "cohort" && <Cohort onOpen={(id) => openFamily(id)} />}
        {section === "story" && <StorySection />}
        {section === "operator" && <Operator />}
        {section === "directory" && <Directory />}
        {section === "registries" && <Registries tab={route.id} onTab={(t) => go({ section: "registries", id: t })} />}
        {section === "config" && <Configuration />}
        {section === "audit" && <Audit />}
      </Shell>
    </ToastProvider>
  );
}

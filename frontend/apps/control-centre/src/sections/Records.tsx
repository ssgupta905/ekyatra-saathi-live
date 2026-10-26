import { useState } from "react";
import { AddStep } from "../desk/AddStep";
import { ImportRecords } from "../desk/ImportRecords";
import { RegisterFamily } from "../desk/RegisterFamily";
import { SegmentedControl } from "../components/SegmentedControl";
import { EmptyState, useToast } from "../ui/kit";
import { UserPlus } from "../ui/icons";
import { useWorld } from "../world";

const STEPS = [
  { value: "register" as const, label: "1 · Register a family" },
  { value: "step" as const, label: "2 · Add their steps" },
  { value: "import" as const, label: "Or import a file" },
];

/**
 * Putting families on record, one step at a time: who they are first, then
 * their journey, or a whole file at once. Real records only; the demo's cohort
 * is generated and a reset would discard anything entered.
 */
export function Records() {
  const world = useWorld();
  const toast = useToast();
  const [step, setStep] = useState<(typeof STEPS)[number]["value"]>("register");
  const [n, setN] = useState(0);

  if (world.snapshot?.world !== "real") {
    return (
      <EmptyState title="Records are entered on real records" icon={<UserPlus />}>
        The demo world's families are generated, and a reset would throw away anything typed here.
        Run the API with <code>make api-real</code> to enter families.
      </EmptyState>
    );
  }

  return (
    <div className="stack">
      <SegmentedControl options={STEPS} value={step} onChange={setStep} aria-label="Step" />
      {step === "register" && (
        <RegisterFamily
          onRegistered={(id) => {
            setN((x) => x + 1);
            toast(`Registered ${id}. Next, add their steps.`);
            setStep("step");
          }}
        />
      )}
      {step === "step" && <AddStep revision={n} onAdded={() => { setN((x) => x + 1); toast("Step added; the family has been re-planned."); }} />}
      {step === "import" && <ImportRecords onImported={() => { setN((x) => x + 1); toast("Imported."); }} />}
    </div>
  );
}

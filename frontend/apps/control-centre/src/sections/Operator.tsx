import { useEffect, useState } from "react";
import { api, type Patient } from "@saathi/api-client";
import { OperatorControls } from "../components/OperatorControls";
import { useWorld } from "../world";

/** The simulated clock, and a way to put a question in a family's mouth. Demo only. */
export function Operator() {
  const world = useWorld();
  const [patients, setPatients] = useState<Patient[]>([]);
  useEffect(() => {
    api.patients().then(setPatients).catch(() => undefined);
  }, []);
  return <OperatorControls snapshot={world.snapshot} patients={patients} onChange={world.refresh} />;
}

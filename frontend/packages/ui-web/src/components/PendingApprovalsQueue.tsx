/**
 * Every disrupted family currently waiting on a human — the navigator's and
 * doctor's shared call list for the disruption loop. A master-detail split,
 * the same idiom as the call list and the one-family view: picking a row
 * opens its ranked options beside the list rather than pushing it down the
 * page. `requires_doctor` is shown so a navigator can see at a glance which
 * ones are not theirs to approve (the server enforces this regardless of
 * what this list displays).
 */

import { useEffect, useState } from "react";
import { disruptions, type PendingOption, type Role } from "@saathi/api-client";
import { Badge, Card } from "../primitives";
import { OptionsApprovalCard } from "./OptionsApprovalCard";

export function PendingApprovalsQueue({
  approverRole,
  approverName,
  onlyRequiringDoctor = false,
  revision,
  onSelect,
}: {
  approverRole: Role;
  approverName: string;
  onlyRequiringDoctor?: boolean;
  /** Bump this to force a refetch after something elsewhere changed the world. */
  revision?: number;
  /** Told which family is open, so a screen can show why beside the options. */
  onSelect?: (patientId: string | null) => void;
}) {
  const [rows, setRows] = useState<PendingOption[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  const refresh = () => {
    disruptions
      .pending()
      .then((all) => {
        const filtered = onlyRequiringDoctor ? all.filter((r) => r.requires_doctor) : all;
        setRows(filtered);
        setSelected((current) =>
          current && filtered.some((r) => r.patient_id === current) ? current : null,
        );
      })
      .catch(() => undefined);
  };

  useEffect(refresh, [onlyRequiringDoctor, revision]);

  useEffect(() => onSelect?.(selected), [selected]);

  const active = rows.find((r) => r.patient_id === selected) ?? null;

  return (
    <Card
      title={onlyRequiringDoctor ? "Awaiting your decision" : "Awaiting a decision"}
      hint="Every disrupted family with ranked options still pending"
    >
      <div className="master-detail">
        <div className="master-list widget-scroll">
          {rows.length === 0 && <p className="empty" style={{ padding: "0 4px" }}>Nothing is waiting right now.</p>}
          {rows.map((row) => (
            <div
              key={`${row.disruption_id}:${row.patient_id}`}
              className="master-row"
              role="button"
              tabIndex={0}
              aria-current={selected === row.patient_id}
              onClick={() => setSelected(row.patient_id)}
            >
              <strong>{row.patient_id}</strong>
              <span className="hint">{row.option_count} option{row.option_count === 1 ? "" : "s"}</span>
              <span className="spacer" />
              {row.requires_doctor && <Badge tone="critical">doctor</Badge>}
            </div>
          ))}
        </div>

        <div key={selected ?? "none"} className="panel-fade">
          {active ? (
            <OptionsApprovalCard
              disruptionId={active.disruption_id}
              patientId={active.patient_id}
              approverRole={approverRole}
              approverName={approverName}
              onApproved={() => {
                setSelected(null);
                refresh();
              }}
            />
          ) : (
            <div className="master-empty">Pick a family on the left to see its options.</div>
          )}
        </div>
      </div>
    </Card>
  );
}

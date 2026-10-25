import { AuditLog } from "../admin/AuditLog";

/** Every fact the system has asserted, across every family, with the chain checked. */
export function Audit() {
  return <AuditLog />;
}

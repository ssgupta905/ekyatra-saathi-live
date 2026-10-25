import type { StaffIdentity } from "@saathi/ui-web";

/** Who is acting in this app until login exists. The server decides what the role may do. */
export const IDENTITY: StaffIdentity = {
  name: "Dr Amrita Sinha",
  title: "Treating oncologist",
  role: "doctor",
};

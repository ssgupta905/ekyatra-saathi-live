import type { StaffIdentity } from "@saathi/ui-web";

/** Who is acting in this app when login is off (the demo); signed in, the server says. The server decides what the role may do. */
export const IDENTITY: StaffIdentity = {
  name: "Dr Amrita Sinha",
  title: "Treating oncologist",
  role: "doctor",
};

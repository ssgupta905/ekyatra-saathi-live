import type { ReactNode } from "react";
import type { Icon } from "../sections";
import * as I from "./icons";

/** The glyph for each section, shared by the navigation rail and the command palette. */
export const ICONS: Record<Icon, () => ReactNode> = {
  home: () => <I.Home />, users: () => <I.Users />, approve: () => <I.Approve />, file: () => <I.FileText />,
  graph: () => <I.Graph />, alert: () => <I.Alert />, inbox: () => <I.Inbox />, userplus: () => <I.UserPlus />,
  chart: () => <I.Chart />, building: () => <I.Building />, sliders: () => <I.Sliders />,
  ledger: () => <I.Ledger />, film: () => <I.Film />, dial: () => <I.Dial />,
};

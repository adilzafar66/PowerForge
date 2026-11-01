"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import type { Project, Revision } from "@/lib/projects";

export type ShellContext = {
  project?: Project;
  revision?: Revision;
  revisions?: Revision[];
  /** The document open in the dedicated viewer. */
  document?: { id: string; name: string };
};
export const ShellContextPublisher = createContext<
  (context: ShellContext) => void
>(() => {});

/** Publish the page's authoritative data into the persistent root frame. */
export function AppShell({
  children,
  project,
  revision,
  revisions,
  document,
}: ShellContext & { children: ReactNode; active?: "projects" | "status" }) {
  const publish = useContext(ShellContextPublisher);
  useEffect(() => {
    publish({ project, revision, revisions, document });
  }, [publish, project, revision, revisions, document]);
  return children;
}

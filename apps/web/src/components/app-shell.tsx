"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import type { Project, Revision } from "@/lib/projects";

export type ShellContext = {
  project?: Project;
  revision?: Revision;
  revisions?: Revision[];
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
}: ShellContext & { children: ReactNode; active?: "projects" | "status" }) {
  const publish = useContext(ShellContextPublisher);
  useEffect(() => {
    publish({ project, revision, revisions });
  }, [publish, project, revision, revisions]);
  return children;
}

"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import {
  Activity,
  Box,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  GitBranch,
  LayoutDashboard,
  Layers,
  Menu,
  Network,
  X,
  Zap,
} from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Select from "@radix-ui/react-select";
import {
  ShellContextPublisher,
  type ShellContext,
} from "@/components/app-shell";
import { SelectItem } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  revisionHref,
  type RevisionDestination,
} from "@/lib/workspace-navigation";
import { cn } from "@/lib/utils";

export function AppFrame({ children }: { children: ReactNode }) {
  const [context, setContext] = useState<ShellContext>({});
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const route = pathname.match(/^\/projects\/([^/]+)(?:\/revisions\/([^/]+))?/);
  const projectId = route?.[1] === "new" ? undefined : route?.[1];
  const revisionId = route?.[2];
  const project =
    context.project?.id === projectId ? context.project : undefined;
  const revisions = project ? (context.revisions ?? []) : [];
  const revision = revisionId
    ? context.revision?.id === revisionId &&
      context.revision.project_id === projectId
      ? context.revision
      : revisions.find((r) => r.id === revisionId)
    : revisions.find((r) => r.status === "ACTIVE");
  const destination: RevisionDestination =
    params.get("view") === "overview"
      ? "overview"
      : params.get("workspace") === "model"
        ? params.get("view") === "topology"
          ? "topology"
          : "equipment"
        : "documents";
  const projectRevisions =
    !revisionId &&
    (pathname === `/projects/${projectId}/revisions` ||
      params.get("section") === "revisions");
  const uiC =
    pathname === "/" ||
    pathname === "/projects/new" ||
    (!!projectId && (!revisionId || destination === "overview"));
  const currentLabel =
    pathname === "/status"
      ? "System Status"
      : pathname === "/projects/new"
        ? "Create Project"
        : revisionId
          ? {
              overview: "Overview",
              documents: "Documents",
              equipment: "Equipment",
              topology: "Topology",
            }[destination]
          : projectId
            ? projectRevisions
              ? "Revisions"
              : "Overview"
            : "Projects";
  const href = (target: RevisionDestination) =>
    revisionHref(
      projectId!,
      revision!.id,
      revisionId,
      params.toString(),
      target,
    );
  const navLink = (
    label: string,
    url: string,
    active: boolean,
    Icon: typeof FolderOpen,
  ) => (
    <Link
      href={url}
      onClick={() => setMobileOpen(false)}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors hover:bg-soft",
        active ? "bg-selection font-semibold text-accent" : "text-ink",
      )}
    >
      <Icon aria-hidden className="h-[18px] w-[18px] shrink-0" />
      {label}
    </Link>
  );
  const navigation = (
    <>
      <Link
        href="/"
        onClick={() => setMobileOpen(false)}
        className="flex h-20 shrink-0 items-center gap-3 border-b border-border px-6 text-xl font-bold tracking-tight"
      >
        <Zap aria-hidden className="h-6 w-6 text-accent" />
        PowerForge
      </Link>
      <nav
        aria-label="Main navigation"
        className="flex-1 space-y-5 overflow-y-auto px-3 py-5"
      >
        <div>
          <p className="mb-2 px-3 text-[10px] font-semibold tracking-widest text-muted uppercase">
            General
          </p>
          {navLink(
            "Projects",
            "/",
            pathname === "/" || pathname === "/projects/new",
            FolderOpen,
          )}
        </div>
        {projectId && (
          <div>
            <p className="mb-2 px-3 text-[10px] font-semibold tracking-widest text-muted uppercase">
              Project
            </p>
            {navLink(
              "Overview",
              `/projects/${projectId}`,
              !revisionId && !projectRevisions,
              LayoutDashboard,
            )}
            {navLink(
              "Revisions",
              `/projects/${projectId}/revisions`,
              projectRevisions,
              GitBranch,
            )}
          </div>
        )}
        {project && revision && (
          <div>
            <p className="mb-2 px-3 text-[10px] font-semibold tracking-widest text-muted uppercase">
              Current Revision
            </p>
            <div className="mb-2 flex items-stretch rounded-lg bg-soft">
              <Link
                href={href("overview")}
                onClick={() => setMobileOpen(false)}
                aria-current={
                  revisionId && destination === "overview" ? "page" : undefined
                }
                className={cn(
                  "min-w-0 flex-1 rounded-l-lg px-3 py-2 hover:bg-selection",
                  revisionId &&
                    destination === "overview" &&
                    "bg-selection text-accent",
                )}
              >
                <span className="block truncate text-[13px] font-semibold">
                  {revision.identifier}
                </span>
                <span className="text-[11px] text-muted">
                  {revision.status.charAt(0) +
                    revision.status.slice(1).toLowerCase()}
                </span>
              </Link>
              <Select.Root
                key={projectId}
                value={revision.id}
                onValueChange={(id) => {
                  setMobileOpen(false);
                  router.push(
                    revisionHref(
                      project.id,
                      id,
                      revisionId,
                      params.toString(),
                      revisionId ? undefined : "overview",
                    ),
                  );
                }}
              >
                <Select.Trigger
                  aria-label="Switch revision"
                  className="flex w-10 shrink-0 items-center justify-center rounded-r-lg border-l border-border hover:bg-selection"
                >
                  <ChevronDown aria-hidden className="h-4 w-4" />
                </Select.Trigger>
                <Select.Portal>
                  <Select.Content
                    position="popper"
                    align="start"
                    sideOffset={6}
                    collisionPadding={12}
                    className="z-[80] max-h-[var(--radix-select-content-available-height)] min-w-52 max-w-[calc(100vw-24px)] overflow-hidden rounded-[10px] border border-border bg-panel p-1 shadow-lg"
                  >
                    <Select.Viewport>
                      {revisions.map((r) => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.identifier} · {r.status.toLowerCase()}
                        </SelectItem>
                      ))}
                    </Select.Viewport>
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </div>
            {navLink(
              "Documents",
              href("documents"),
              !!revisionId && destination === "documents",
              FileText,
            )}
            <div className="mt-2 flex items-center gap-3 px-3 py-2 text-[13px] text-muted">
              <Layers aria-hidden className="h-[18px] w-[18px]" />
              Engineering Model
            </div>
            <div className="ml-3 space-y-1 rounded-lg bg-soft p-1">
              {navLink(
                "Equipment",
                href("equipment"),
                !!revisionId && destination === "equipment",
                Box,
              )}
              {navLink(
                "Topology",
                href("topology"),
                !!revisionId && destination === "topology",
                Network,
              )}
            </div>
          </div>
        )}
      </nav>
      <div className="shrink-0 border-t border-border p-3">
        {navLink("System Status", "/status", pathname === "/status", Activity)}
      </div>
    </>
  );
  return (
    <ShellContextPublisher.Provider value={setContext}>
      <div className={`flex min-h-screen bg-canvas ${uiC ? "ui-c-shell" : ""}`}>
        <a
          href="#main-content"
          className="sr-only fixed top-2 left-2 z-[100] rounded bg-panel p-3 focus:not-sr-only"
        >
          Skip to content
        </a>
        <aside className="sticky top-0 hidden h-dvh w-[236px] shrink-0 flex-col border-r border-border bg-panel md:flex">
          {navigation}
        </aside>
        <div className="min-w-0 flex-1">
          <header
            className={`flex items-center gap-3 border-b border-border bg-panel px-4 ${uiC ? "min-h-[66px] md:px-[43px]" : "min-h-16 md:px-8"}`}
          >
            <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
              <Dialog.Trigger asChild>
                <Button
                  variant="ghost"
                  className="md:hidden"
                  aria-label="Open navigation"
                >
                  <Menu className="h-5 w-5" />
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 md:hidden" />
                <Dialog.Content
                  aria-describedby={undefined}
                  className="fixed inset-y-0 left-0 z-50 flex w-[min(300px,85vw)] flex-col bg-panel shadow-xl md:hidden"
                >
                  <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                  <Dialog.Close
                    aria-label="Close navigation"
                    className="absolute top-2 right-2 rounded p-2"
                  >
                    <X className="h-4 w-4" />
                  </Dialog.Close>
                  {navigation}
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
            <nav
              aria-label="Context breadcrumbs"
              className="flex min-w-0 flex-wrap items-center gap-2 py-3 text-[12px] text-muted"
            >
              {pathname !== "/" && (
                <>
                  <Link href="/" className="hover:text-accent">
                    Projects
                  </Link>
                  <ChevronRight aria-hidden className="h-3 w-3" />
                </>
              )}
              {project && (
                <>
                  <Link
                    href={`/projects/${project.id}`}
                    className="max-w-60 truncate hover:text-accent"
                    title={project.project_name}
                    aria-current={
                      uiC && !revisionId && !projectRevisions
                        ? "page"
                        : undefined
                    }
                  >
                    {uiC
                      ? project.project_name
                      : `${project.project_number} · ${project.project_name}`}
                  </Link>
                  {(!uiC || projectRevisions || revisionId) && (
                    <ChevronRight aria-hidden className="h-3 w-3" />
                  )}
                </>
              )}
              {uiC && revisionId && (
                <>
                  <Link
                    href={`/projects/${projectId}/revisions`}
                    className="hover:text-accent"
                  >
                    Revisions
                  </Link>
                  <ChevronRight aria-hidden className="h-3 w-3" />
                </>
              )}
              {revisionId && revision && !uiC && (
                <>
                  <Link
                    href={href("overview")}
                    className="font-mono hover:text-accent"
                  >
                    {revision.identifier}
                  </Link>
                  <ChevronRight aria-hidden className="h-3 w-3" />
                </>
              )}
              {!(uiC && project && !revisionId && !projectRevisions) && (
                <span aria-current="page" className="font-medium text-ink">
                  {uiC && revisionId && revision
                    ? revision.identifier
                    : currentLabel}
                </span>
              )}
            </nav>
            {uiC && project && (
              <span
                className={`ui-c-status ${project.status} ml-auto hidden sm:inline-flex`}
              >
                {project.status.charAt(0) +
                  project.status.slice(1).toLowerCase()}{" "}
                project
              </span>
            )}
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className="min-w-0 outline-none"
          >
            {children}
          </main>
        </div>
      </div>
    </ShellContextPublisher.Provider>
  );
}

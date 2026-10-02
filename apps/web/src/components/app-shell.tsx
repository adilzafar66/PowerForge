import Link from "next/link";
import { Zap } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function AppShell({
  children,
  active = "projects",
}: {
  children: ReactNode;
  active?: "projects" | "status";
}) {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="z-10 flex h-12 shrink-0 items-center border-b border-slate-200 bg-white px-5 shadow-[0_1px_0_rgba(0,0,0,0.04)]">
        <Link href="/" className="group mr-6 flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent text-white shadow-[0_1px_3px_rgba(29,111,216,0.4)] transition-colors group-hover:bg-accent-hover">
            <Zap className="h-[15px] w-[15px]" fill="currentColor" strokeWidth={0} />
          </span>
          <span className="text-[14.5px] font-bold tracking-tight text-slate-900">PowerForge</span>
        </Link>

        <div className="mr-6 h-4 w-px bg-slate-200" />

        <nav className="flex h-full items-center gap-0.5">
          <NavLink href="/" active={active === "projects"}>
            Projects
          </NavLink>
          <NavLink href="/status" active={active === "status"}>
            System Status
          </NavLink>
        </nav>
      </header>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "relative flex h-12 items-center px-3.5 text-[13.5px] font-medium transition-colors",
        active ? "text-accent" : "text-slate-500 hover:text-slate-800",
      )}
    >
      {children}
      {active ? (
        <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-accent" />
      ) : null}
    </Link>
  );
}

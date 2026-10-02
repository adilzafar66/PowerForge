import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

export type BreadcrumbItem = {
  label: ReactNode;
  onClick?: () => void;
  href?: string;
};

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="mb-6 flex items-center gap-1.5 text-[12.5px] text-slate-400">
      {items.map((item, index) => (
        <span key={`${index}-${String(item.label)}`} className="flex items-center gap-1.5">
          {index > 0 ? (
            <span className="text-slate-300">
              <ChevronRight className="h-[13px] w-[13px]" strokeWidth={1.8} />
            </span>
          ) : null}
          {item.href ? (
            <Link
              href={item.href}
              className="cursor-pointer font-medium transition-colors hover:text-slate-700"
            >
              {item.label}
            </Link>
          ) : item.onClick ? (
            <button
              type="button"
              onClick={item.onClick}
              className="cursor-pointer font-medium transition-colors hover:text-slate-700"
            >
              {item.label}
            </button>
          ) : (
            <span className="font-semibold text-slate-700">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

import { useState } from "react";
import type { Collection, Detail, Issue, PublishedCandidate } from "./api";

export function object(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

export function display(value: unknown) {
  if (typeof value === "string") return value;
  try { return JSON.stringify(value) ?? "Unavailable"; }
  catch { return "Expand JSON to inspect this value"; }
}

export function Copy({ value, label }: { value: string; label: string }) {
  const [feedback, setFeedback] = useState("");
  return <button className="quiet" type="button" onClick={async () => {
    try { await navigator.clipboard.writeText(value); setFeedback("Copied"); }
    catch { setFeedback("Clipboard unavailable"); }
  }} aria-label={label}>{feedback || label}</button>;
}

export function JsonTree({ value, path = "", name = "Response", root = true }: {
  value: unknown; path?: string; name?: string; root?: boolean;
}) {
  const [limit, setLimit] = useState(40);
  const [open, setOpen] = useState(root);
  const children = value !== null && typeof value === "object" ? Object.entries(value) : null;
  if (!children) return <div className="json-leaf"><code>{name}: {JSON.stringify(value)}</code>
    <Copy value={display(value)} label="Copy value" /><Copy value={path} label="Copy path" /></div>;
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)} className="json-node">
    <summary><code>{name}</code> <span className="muted">{Array.isArray(value) ? "Array" : "Object"} · {children.length}</span></summary>
    {open && <div className="json-children"><Copy value={path} label="Copy path" />
      {children.slice(0, limit).map(([key, child]) => <JsonTree key={key} name={key} value={child}
        path={`${path}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`} root={false} />)}
      {limit < children.length && <button onClick={() => setLimit(limit + 40)}>Show more children</button>}
    </div>}
  </details>;
}

export function Diagnostics({ issues, fatal = false }: { issues: Issue[]; fatal?: boolean }) {
  if (issues.length === 0) return null;
  return <section className="diagnostics"><h3>{fatal ? "Fatal response diagnostics" : "Quarantine diagnostics"}</h3>
    <ul>{issues.map((issue, index) => <li key={index}><code>{issue.path.map((part, i) =>
      typeof part === "number" ? `[${part}]` : `${i ? "." : ""}${part}`).join("") || "Response"}</code>
      <span>{issue.error_type} · {issue.category}</span></li>)}</ul></section>;
}

export type Assertion = {
  collection: Collection; index: number; original?: unknown; validated?: unknown;
  candidate?: PublishedCandidate; issues: Issue[]; state: string; publishedPosition?: boolean;
};

export function assertions(detail: Detail, parsed: unknown): Assertion[] {
  const rows = new Map<string, Assertion>();
  const response = object(parsed);
  const fatal = detail.attempt.validation === "fatal";
  for (const collection of ["attributes", "raw_unmapped"] as const) {
    const list = response?.[collection];
    if (Array.isArray(list) && list.length <= (collection === "attributes" ? 512 : 16)) {
      list.forEach((original, index) => rows.set(`${collection}:${index}`,
        { collection, index, original, issues: [], state: fatal ? "Fatal response" : "Accepted" }));
    }
  }
  for (const rejection of detail.rejections) {
    const key = `${rejection.collection}:${rejection.index}`;
    rows.set(key, { ...rows.get(key), ...rejection, state: "Quarantined" });
  }
  // The immutable rejection positions mark the holes left in each original
  // array. The count checks make this derivation safe even after raw expiry.
  const groups = ["attributes", "raw_unmapped"] as const;
  const lists = groups.map(group => detail.validated?.[group]);
  if (lists.every(Array.isArray) && !fatal && detail.attempt.received !== null) {
    const total = lists.reduce((sum, list) => sum + (list as unknown[]).length, 0);
    const received = detail.attempt.received;
    if (total === detail.attempt.accepted && total + detail.rejections.length === received) {
      const candidates = new Map(detail.candidates.map(candidate => [candidate.ordinal, candidate]));
      let ordinal = 0;
      groups.forEach((collection, groupIndex) => {
        const accepted = lists[groupIndex] as unknown[];
        const quarantined = detail.rejections.filter(item => item.collection === collection);
        const rejected = new Set(quarantined.map(item => item.index));
        const originalCount = accepted.length + rejected.size;
        const original = response?.[collection];
        const shapeMatches = rejected.size === quarantined.length &&
          [...rejected].every(index => index >= 0 && index < originalCount) &&
          (original === undefined || (Array.isArray(original) && original.length === originalCount));
        let index = 0;
        for (const validated of accepted) {
          while (rejected.has(index)) index++;
          const key = `${collection}:${index}`;
          const prior = rows.get(key);
          const ref = object(validated)?.local_ref;
          const candidate = candidates.get(ordinal++);
          if (shapeMatches && typeof ref === "string" && (!prior || object(prior.original)?.local_ref === ref)) {
            rows.set(key, { collection, index, issues: [], state: "Accepted", ...prior,
              validated, candidate: candidate?.local_ref === ref ? candidate : undefined });
          }
          index++;
        }
      });
    }
  }
  if (detail.attempt.validation === null && lists.every(Array.isArray) && rows.size === 0) {
    const candidates = new Map(detail.candidates.map(candidate => [candidate.ordinal, candidate]));
    let ordinal = 0;
    groups.forEach((collection, groupIndex) => {
      (lists[groupIndex] as unknown[]).forEach((validated, index) => {
        const candidate = candidates.get(ordinal++);
        rows.set(`${collection}:${index}`, {
          collection, index, state: "Accepted", issues: [], validated, publishedPosition: true,
          candidate: candidate && candidate.local_ref === object(validated)?.local_ref ? candidate : undefined,
        });
      });
    });
  }
  return [...rows.values()].sort((a, b) => a.collection.localeCompare(b.collection) || a.index - b.index);
}

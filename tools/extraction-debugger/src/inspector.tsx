import { useState } from "react";
import type { Collection, Detail, Issue, PublishedCandidate } from "./api";

class NumericLiteral {
  constructor(readonly source: string, readonly integer: boolean) {}
}

export function parseInspectorJson(text: string): unknown {
  return JSON.parse(text, (_key, value, context?: { source?: string }) => {
    if (typeof value !== "number") return value;
    const literal = context?.source;
    if (literal && !/^-?\d+$/.test(literal)) return new NumericLiteral(literal, false);
    if (literal === "-0") return new NumericLiteral(literal, true);
    if (!Number.isSafeInteger(value)) {
      return new NumericLiteral(literal ?? "Exact digits unavailable", !!literal);
    }
    return value;
  });
}

export function object(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) && !(value instanceof NumericLiteral)
    ? value as Record<string, unknown> : undefined;
}

export function display(value: unknown) {
  if (typeof value === "string") return value;
  if (value instanceof NumericLiteral) return value.source;
  try { return JSON.stringify(value) ?? "Unavailable"; }
  catch { return "Expand JSON to inspect this value"; }
}

function typedValue(value: unknown) {
  const type = value instanceof NumericLiteral ? (value.integer ? "integer" : "number")
    : value === null ? "null" : Array.isArray(value) ? "array"
    : typeof value === "number" && Number.isInteger(value) ? "integer" : typeof value;
  const content = type === "object" || type === "array"
    ? "See assertion JSON"
    : typeof value === "string"
      ? JSON.stringify(value.slice(0, 2048)) + (value.length > 2048 ? "…" : "")
      : display(value);
  return <><code>{content}</code> <span className="muted">({type})</span></>;
}

export function AssertionFields({ value, persisted = false, compact = false }: {
  value: unknown; persisted?: boolean; compact?: boolean;
}) {
  const assertion = object(value);
  if (!assertion) return null;
  const fields = [
    ["raw_value", "Raw value"], ["raw_unit", "Source unit"],
    ["proposed_value", "Proposed value"], ["proposed_enum_value", "Historical enum proposal"],
    ["proposed_unit", "Proposed unit"], ["value_form", "Source form"],
  ] as const;
  const aliases: Record<string, string> = {
    raw_value: "raw", raw_unit: "source_unit", proposed_value: "value",
    proposed_unit: "unit", value_form: "form",
  };
  const alternates = Object.hasOwn(assertion, "alternate_representations")
    ? assertion.alternate_representations : compact ? assertion.alternates : undefined;
  const recorded = fields.map(([key, label]) => [compact && !Object.hasOwn(assertion, key) ? aliases[key] : key, label])
    .filter(([key]) => key && Object.hasOwn(assertion, key));
  const hasAlternates = Array.isArray(alternates) && alternates.length > 0;
  if (!recorded.length && !hasAlternates) return null;
  return <dl className="metadata assertion-fields" aria-label={persisted ? "Persisted candidate fields" : "Recorded assertion fields"}>
    {recorded.map(([key, label]) =>
      <div key={key}><dt>{label}</dt><dd>{typedValue(assertion[key])}</dd></div>)}
    {hasAlternates && <div>
      <dt>Alternate representations</dt><dd><ul>{alternates.slice(0, 4).map((item, index) => {
        const pair = object(item);
        return <li key={index}>{pair ? <>{typedValue(pair.value)} {typedValue(pair.unit)}</> : typedValue(item)}</li>;
      })}</ul>{alternates.length > 4 && <span className="muted">See assertion JSON for additional entries.</span>}</dd>
    </div>}
    {persisted && !hasAlternates && <div>
      <dt>Alternate representations</dt><dd><code>{alternates === null ? "null" : "[]"}</code></dd>
    </div>}
  </dl>;
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
  const children = value !== null && typeof value === "object" && !(value instanceof NumericLiteral)
    ? Object.entries(value) : null;
  if (!children) return <div className="json-leaf"><code>{name}: {value instanceof NumericLiteral ? value.source : JSON.stringify(value)}</code>
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
  const compact = detail.attempt.output_version === "compact-assertions-v1";
  const serverOwned = compact || detail.attempt.output_version === "server-owned-assertions-v1";
  const overflow = detail.overflow_indices ?? [];
  for (const collection of ["attributes", "raw_unmapped"] as const) {
    const list = response?.[collection];
    if (Array.isArray(list) && list.length <= (collection === "attributes" ? 512 : serverOwned ? 32 : 16)) {
      list.forEach((original, index) => rows.set(`${collection}:${index}`,
        { collection, index, original, issues: [], state: fatal ? "Fatal response" : "Accepted" }));
    }
  }
  for (const rejection of detail.rejections) {
    const key = `${rejection.collection}:${rejection.index}`;
    rows.set(key, { ...rows.get(key), ...rejection, state: "Quarantined" });
  }
  for (const index of overflow) {
    const key = `raw_unmapped:${index}`;
    rows.set(key, { ...rows.get(key), collection: "raw_unmapped", index, issues: [], state: "Overflowed" });
  }
  // Immutable rejection and overflow positions mark the holes left in each original
  // array. The count checks make this derivation safe even after raw expiry.
  const groups = ["attributes", "raw_unmapped"] as const;
  const lists = groups.map(group => detail.validated?.[group]);
  if (lists.every(Array.isArray) && !fatal && detail.attempt.received !== null) {
    const total = lists.reduce((sum, list) => sum + (list as unknown[]).length, 0);
    const received = detail.attempt.received;
    if (total === detail.attempt.accepted && total + detail.rejections.length + overflow.length === received &&
        overflow.length === (detail.attempt.overflowed ?? 0)) {
      const candidates = new Map(detail.candidates.map(candidate => [candidate.ordinal, candidate]));
      let ordinal = 0;
      groups.forEach((collection, groupIndex) => {
        const accepted = lists[groupIndex] as unknown[];
        const quarantined = detail.rejections.filter(item => item.collection === collection);
        const omitted = [...quarantined.map(item => item.index), ...(collection === "raw_unmapped" ? overflow : [])];
        const rejected = new Set(omitted);
        const originalCount = accepted.length + rejected.size;
        const original = response?.[collection];
        const shapeMatches = rejected.size === omitted.length &&
          [...rejected].every(index => index >= 0 && index < originalCount) &&
          (original === undefined || (Array.isArray(original) && original.length === originalCount));
        let index = 0;
        for (const validated of accepted) {
          while (rejected.has(index)) index++;
          const key = `${collection}:${index}`;
          const prior = rows.get(key);
          const ref = object(validated)?.local_ref;
          const candidate = candidates.get(ordinal++);
          const originalMatches = serverOwned ? ref === `${collection === "attributes" ? "attr" : "raw"}-${index}`
            : !prior || object(prior.original)?.local_ref === ref;
          if (shapeMatches && typeof ref === "string" && originalMatches) {
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

import { QueryClient } from "@tanstack/react-query";
import { keys } from "./query-keys";

export function makeQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: (count, error) => {
          const status = (error as Error & { status?: number }).status;
          return count < 2 && !(status && status < 500);
        },
        refetchOnWindowFocus: true,
        refetchIntervalInBackground: false,
      },
      mutations: { retry: false },
    },
  });
  client.setQueryDefaults(keys.registry, { staleTime: 60 * 60_000 });
  return client;
}

/** Called only after a confirmed write. Inactive queries become stale without fetching. */
export async function invalidateWrite(client: QueryClient, path: string) {
  const parts = path.split("?")[0].split("/").filter(Boolean);
  if (parts[0] !== "api" || parts[1] !== "projects") return;
  const p = parts[2],
    r = parts[4],
    domain = parts[5];
  const affected: (readonly unknown[])[] = [];
  if (!p) affected.push(keys.projects);
  else if (parts[3] !== "revisions")
    affected.push(keys.projects, keys.project(p));
  else if (!r || !domain || domain === "activate") {
    affected.push(keys.projects, keys.project(p), keys.revisions(p), [
      "revision",
      p,
    ]);
  } else if (domain === "documents") {
    affected.push([...keys.documents(p, r), "list"]);
    if (parts[6]) affected.push(keys.document(p, r, parts[6]));
  } else if (["equipment", "nodes", "connections"].includes(domain)) {
    // Equipment reconciliation and node removal can change terminals/connections.
    if (domain === "equipment")
      affected.push([...keys.model(p, r), "equipment"]);
    if (domain !== "connections")
      affected.push(
        keys.nodes(p, r),
        domain === "equipment" && parts[6]
          ? keys.editor(p, r, parts[6])
          : [...keys.model(p, r), "editor"],
      );
    affected.push(keys.connections(p, r));
  }
  await Promise.all(
    affected.map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

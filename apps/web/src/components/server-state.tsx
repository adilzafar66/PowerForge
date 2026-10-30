import { dehydrate, HydrationBoundary } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { makeQueryClient } from "@/lib/query-client";

/** A fresh client per server render; timestamps let newer RSC payloads hydrate an existing browser cache. */
export function ServerState({
  entries,
  children,
}: {
  entries: [readonly unknown[], unknown][];
  children: ReactNode;
}) {
  const client = makeQueryClient();
  for (const [key, data] of entries)
    if (data !== undefined) client.setQueryData(key, data);
  return (
    <HydrationBoundary state={dehydrate(client)}>{children}</HydrationBoundary>
  );
}

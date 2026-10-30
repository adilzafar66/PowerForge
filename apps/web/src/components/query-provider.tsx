"use client";
import { useEffect, useState, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { makeQueryClient, invalidateWrite } from "@/lib/query-client";
import { onServerWrite } from "@/lib/server-writes";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  useEffect(
    () =>
      onServerWrite((path) => {
        void invalidateWrite(client, path);
      }),
    [client],
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

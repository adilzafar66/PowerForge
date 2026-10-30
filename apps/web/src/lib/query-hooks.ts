"use client";
import { useQuery, type QueryKey } from "@tanstack/react-query";
import { apiErrorOf } from "./api";

export function useResource<T>(
  queryKey: QueryKey,
  queryFn: () => Promise<T>,
  enabled = true,
) {
  const query = useQuery({ queryKey, queryFn, enabled });
  return {
    ...query,
    data: query.data ?? null,
    loading: query.isPending && query.isFetching,
    refreshing: !!query.data && query.isFetching,
    error: query.error ? apiErrorOf(query.error).detail : null,
    retry: () => void query.refetch(),
  };
}

export function isRunning(status?: string | null) {
  return status === "PENDING" || status === "RUNNING";
}
/** Shared bounded polling policy for real jobs; never manufactures progress. */
export function jobInterval(active: boolean, failures = 0): number | false {
  return active ? Math.min(3000 * 2 ** failures, 30_000) : false;
}

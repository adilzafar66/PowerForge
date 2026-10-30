"use client";
import { Button } from "./button";
import { apiErrorOf } from "@/lib/api";

export function AsyncState({
  pending = false,
  refreshing = false,
  error,
  retry,
}: {
  pending?: boolean;
  refreshing?: boolean;
  error?: unknown;
  retry?: () => unknown;
}) {
  return (
    <>
      {pending ? (
        <div
          role="status"
          className="my-4 rounded-lg bg-soft p-5 text-sm text-muted motion-safe:animate-pulse"
        >
          Loading…
        </div>
      ) : refreshing ? (
        <p role="status" className="my-2 text-xs text-muted">
          Refreshing…
        </p>
      ) : null}
      {error ? (
        <div
          role="alert"
          className="pf-feedback my-3 rounded-lg border border-danger/20 bg-danger/5 p-3 text-sm text-danger"
        >
          {apiErrorOf(error).detail}{" "}
          {retry && (
            <Button size="sm" variant="outline" onClick={() => void retry()}>
              Retry
            </Button>
          )}
        </div>
      ) : null}
    </>
  );
}

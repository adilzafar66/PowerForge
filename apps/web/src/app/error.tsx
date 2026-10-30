"use client";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div role="alert" className="p-8">
      <p className="mb-3">Unable to load this workspace. Please try again.</p>
      <Button onClick={reset}>Retry</Button>
    </div>
  );
}

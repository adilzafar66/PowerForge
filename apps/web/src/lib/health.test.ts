import { describe, expect, it } from "vitest";

import { isApiHealthy, overallLabel } from "./health";

describe("health helpers", () => {
  it("treats an ok health payload as healthy", () => {
    expect(
      isApiHealthy({ status: "ok", service: "powerforge-api", version: "0.1.0" }),
    ).toBe(true);
    expect(isApiHealthy(null)).toBe(false);
  });

  it("describes readiness for the engineer-facing status page", () => {
    expect(overallLabel(null, null)).toBe("API unreachable");
    expect(
      overallLabel(
        {
          status: "ok",
          service: "powerforge-api",
          version: "0.1.0",
          database: "ok",
          redis: "ok",
        },
        { status: "ok", service: "powerforge-api", version: "0.1.0" },
      ),
    ).toBe("Stack ready");
    expect(
      overallLabel(
        {
          status: "degraded",
          service: "powerforge-api",
          version: "0.1.0",
          database: "ok",
          redis: "unavailable",
        },
        { status: "ok", service: "powerforge-api", version: "0.1.0" },
      ),
    ).toBe("API up, Redis unavailable");
  });
});

import { describe, expect, it } from "vitest";

import { buildHeaders } from "./headers";

describe("buildHeaders", () => {
  it("sends the new secret key only as apikey", () => {
    const headers = buildHeaders("sb_secret_abc");

    expect(headers.apikey).toBe("sb_secret_abc");
    expect(headers.Authorization).toBeUndefined();
  });

  it("also sends Authorization for legacy JWT keys", () => {
    const headers = buildHeaders("eyJhbGci.payload.sig");

    expect(headers.apikey).toBe("eyJhbGci.payload.sig");
    expect(headers.Authorization).toBe("Bearer eyJhbGci.payload.sig");
  });

  it("merges extra headers without dropping the defaults", () => {
    const headers = buildHeaders("sb_secret_abc", { Prefer: "count=exact" });

    expect(headers.Prefer).toBe("count=exact");
    expect(headers.Accept).toBe("application/json");
  });
});

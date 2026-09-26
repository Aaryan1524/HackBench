import { describe, expect, it } from "vitest";
import { normalizeBackendUrl } from "@/lib/backendUrl";

describe("normalizeBackendUrl", () => {
  it.each([
    ["https://hackbench-production.up.railway.app", "https://hackbench-production.up.railway.app"],
    ["hackbench-production.up.railway.app", "https://hackbench-production.up.railway.app"], // the value that broke the build
    ["https://x.up.railway.app/", "https://x.up.railway.app"],
    ["https://x.up.railway.app///", "https://x.up.railway.app"],
    ["https://x.up.railway.app/api", "https://x.up.railway.app"],
    ["https://x.up.railway.app/api/", "https://x.up.railway.app"],
    ["  https://x.up.railway.app  ", "https://x.up.railway.app"],
    ["http://localhost:8000", "http://localhost:8000"],
    ["HTTPS://X.up.railway.app", "HTTPS://X.up.railway.app"],
  ])("%s -> %s", (input, expected) => expect(normalizeBackendUrl(input)).toBe(expected));

  it("falls back to the local backend when nothing is set", () => {
    expect(normalizeBackendUrl(undefined)).toBe("http://127.0.0.1:8000");
    expect(normalizeBackendUrl("   ")).toBe("http://127.0.0.1:8000");
  });
});

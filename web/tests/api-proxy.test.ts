import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/[...path]/route";

const SECRET = "test-shared-secret-value";
const upstream = vi.fn();

function req(method: string, path: string, body?: string, headers: Record<string, string> = {}) {
  return new NextRequest(`http://localhost:3000/api/${path}`, { method, body, headers });
}
const ctx = (path: string) => ({ params: { path: path.split("/") } });

beforeEach(() => {
  upstream.mockReset();
  upstream.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", upstream);
  vi.stubEnv("BACKEND_URL", "https://backend.internal/");
  vi.stubEnv("BACKEND_SHARED_SECRET", SECRET);
});
afterEach(() => vi.unstubAllEnvs());

describe("the /api proxy", () => {
  it("forwards analyze with the secret and the visitor's address, server-side only", async () => {
    const res = await POST(req("POST", "analyze", '{"a":1}', { "x-real-ip": "203.0.113.9", "x-backend-secret": "attacker-supplied" }), ctx("analyze"));
    expect(res.status).toBe(200);
    const [url, init] = upstream.mock.calls[0];
    expect(url).toBe("https://backend.internal/api/analyze");
    expect(init.headers["x-backend-secret"]).toBe(SECRET); // ours, never the caller's
    expect(init.headers["x-client-ip"]).toBe("203.0.113.9");
    expect(init.body).toBe('{"a":1}');
    expect(init.redirect).toBe("manual");
  });

  it("never returns the secret or backend address to the browser", async () => {
    const res = await POST(req("POST", "analyze", "{}"), ctx("analyze"));
    const everything = JSON.stringify(Array.from(res.headers.entries())) + (await res.text());
    expect(everything).not.toContain(SECRET);
    expect(everything).not.toContain("backend.internal");
  });

  it("copes with a backend address entered without https://, or with /api on the end", async () => {
    for (const typed of ["backend.internal", "backend.internal/", "https://backend.internal/api"]) {
      upstream.mockClear();
      vi.stubEnv("BACKEND_URL", typed);
      await POST(req("POST", "analyze", "{}"), ctx("analyze"));
      expect(upstream.mock.calls[0][0], typed).toBe("https://backend.internal/api/analyze");
    }
  });

  it("does not add a secret header when none is configured (local development)", async () => {
    vi.stubEnv("BACKEND_SHARED_SECRET", "");
    await POST(req("POST", "analyze", "{}"), ctx("analyze"));
    expect(upstream.mock.calls[0][1].headers["x-backend-secret"]).toBeUndefined();
  });

  it("uses the last forwarded address when there is no x-real-ip", async () => {
    await POST(req("POST", "analyze", "{}", { "x-forwarded-for": "6.6.6.6, 198.51.100.4" }), ctx("analyze"));
    expect(upstream.mock.calls[0][1].headers["x-client-ip"]).toBe("198.51.100.4");
  });

  it("only exposes the two calls the UI makes", async () => {
    for (const path of ["health", "docs", "openapi.json", "events", "events/x/other", "analyze/extra", "../etc/passwd", ""]) {
      const res = await POST(req("POST", path || "x", "{}"), ctx(path || "x"));
      expect(res.status, path).toBe(404);
    }
    expect(upstream).not.toHaveBeenCalled();
  });

  it("enforces methods", async () => {
    expect((await GET(req("GET", "analyze"), ctx("analyze"))).status).toBe(405);
    expect((await POST(req("POST", "events/shellhacks2025:2025/prizes", "{}"), ctx("events/shellhacks2025:2025/prizes"))).status).toBe(405);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("proxies the prizes list", async () => {
    const res = await GET(req("GET", "events/shellhacks2026:2026/prizes"), ctx("events/shellhacks2026:2026/prizes"));
    expect(res.status).toBe(200);
    expect(upstream.mock.calls[0][0]).toBe("https://backend.internal/api/events/shellhacks2026:2026/prizes");
  });

  it("rejects oversized request bodies without calling the backend", async () => {
    const res = await POST(req("POST", "analyze", "x".repeat(70_000)), ctx("analyze"));
    expect(res.status).toBe(413);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("passes the backend's status and failure stage through", async () => {
    upstream.mockResolvedValue(new Response('{"detail":"busy"}', { status: 503, headers: { "content-type": "application/json", "x-failure-stage": "repo_analysis" } }));
    const res = await POST(req("POST", "analyze", "{}"), ctx("analyze"));
    expect(res.status).toBe(503);
    expect(res.headers.get("x-failure-stage")).toBe("repo_analysis");
  });

  it("turns a backend outage or timeout into a friendly error, not a stack trace", async () => {
    upstream.mockRejectedValue(new TypeError("fetch failed: ECONNREFUSED 10.0.0.5:8000"));
    let res = await POST(req("POST", "analyze", "{}"), ctx("analyze"));
    expect(res.status).toBe(502);
    expect(await res.text()).not.toMatch(/ECONNREFUSED|10\.0\.0\.5/);
    upstream.mockRejectedValue(Object.assign(new Error("t"), { name: "TimeoutError" }));
    res = await POST(req("POST", "analyze", "{}"), ctx("analyze"));
    expect(res.status).toBe(504);
  });
});

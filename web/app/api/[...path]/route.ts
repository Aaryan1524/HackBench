import { NextRequest } from "next/server";

/**
 * The browser only ever talks to this app. This handler forwards the two calls the UI makes to the private
 * backend, adding a shared secret and the visitor's address on the server side, so:
 *  - the backend can refuse any request that did not come through here (the secret never reaches the browser), and
 *  - rate limiting is per visitor, not per proxy.
 * Everything else is a 404. Runs at request time, so BACKEND_URL can change without a rebuild.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60; // a review can take 20 to 45 seconds

const MAX_BODY_BYTES = 64 * 1024;
const UPSTREAM_TIMEOUT_MS = 55_000;

const ROUTES: Array<{ method: "GET" | "POST"; pattern: RegExp }> = [
  { method: "POST", pattern: /^analyze$/ },
  { method: "GET", pattern: /^events\/[A-Za-z0-9:\-]{1,60}\/prizes$/ },
];

const json = (status: number, detail: string, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...extra },
  });

function visitorAddress(req: NextRequest): string {
  // Vercel sets these to the real client address; a client-supplied value is overwritten at its edge.
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",").pop()!.trim();
  return "";
}

async function proxy(req: NextRequest, ctx: { params: { path: string[] } }): Promise<Response> {
  const path = (ctx.params.path || []).join("/");
  const route = ROUTES.find((r) => r.pattern.test(path));
  if (!route) return json(404, "Not found.");
  if (req.method !== route.method) return json(405, "Method not allowed.");

  let body: string | undefined;
  if (route.method === "POST") {
    body = await req.text();
    if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) return json(413, "Request too large.");
  }

  const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
  const headers: Record<string, string> = { accept: "application/json" };
  if (body !== undefined) headers["content-type"] = "application/json";
  const secret = process.env.BACKEND_SHARED_SECRET;
  if (secret) headers["x-backend-secret"] = secret;
  const ip = visitorAddress(req);
  if (ip) headers["x-client-ip"] = ip;

  try {
    const upstream = await fetch(`${backend}/api/${path}`, {
      method: route.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const text = await upstream.text();
    const out: Record<string, string> = {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    };
    const stage = upstream.headers.get("x-failure-stage");
    if (stage) out["x-failure-stage"] = stage;
    return new Response(text, { status: upstream.status, headers: out });
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
    return json(
      timedOut ? 504 : 502,
      timedOut ? "The review took too long. Try again." : "The review service is unavailable. Try again in a moment.",
      { "x-failure-stage": "unknown" }
    );
  }
}

export const GET = proxy;
export const POST = proxy;

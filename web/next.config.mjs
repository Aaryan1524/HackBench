import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

// One shared .env at the repo root serves both the backend and this app. Next.js itself only reads web/.env*,
// so load the root file here, and ONLY the variables that are meant for the frontend. Secrets such as
// CHATGPT_API_KEY are never copied into this process, so they can never reach the browser bundle.
const FRONTEND_VARS = /^(NEXT_PUBLIC_[A-Z0-9_]+|BACKEND_URL|BACKEND_SHARED_SECRET)$/; // the last two are read only by server code
const rootEnv = process.env.HACKBENCH_ENV_FILE || resolve(process.cwd(), "..", ".env");
if (existsSync(rootEnv)) {
  for (const line of readFileSync(rootEnv, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!m || !FRONTEND_VARS.test(m[1]) || process.env[m[1]] !== undefined) continue;
    process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, "$2");
  }
}

/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;

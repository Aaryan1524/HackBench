/**
 * Accepts the backend address however it was typed and returns "https://host" with no trailing slash:
 *   "host.up.railway.app", "https://host/", "https://host/api", " https://host " all work.
 * A typo in a deployment variable should degrade to a working (or clearly failing) proxy, never break the build.
 */
export function normalizeBackendUrl(raw: string | undefined): string {
  let url = (raw || "").trim();
  if (!url) return "http://127.0.0.1:8000"; // local development
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
  return url.replace(/\/+$/, "").replace(/\/api$/i, "").replace(/\/+$/, "");
}

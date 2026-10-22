export async function onRequest(context) {
  const backendUrl = (context.env.BACKEND_URL || "").replace(/\/+$/, "");
  if (!backendUrl) {
    return new Response("BACKEND_URL is not configured", { status: 500 });
  }

  const incoming = new URL(context.request.url);
  if (!["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"].includes(context.request.method)) {
    return new Response("Method not allowed", { status: 405, headers: { Allow: "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS" } });
  }
  if (!incoming.pathname.startsWith("/api/v1/") && incoming.pathname !== "/api/v1") {
    return new Response("Not found", { status: 404 });
  }
  const backend = new URL(backendUrl);
  if (backend.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(backend.hostname)) {
    return new Response("BACKEND_URL must use HTTPS", { status: 500 });
  }
  const target = `${backendUrl}${incoming.pathname}${incoming.search}`;
  const headers = new Headers();
  // Forward only headers required by the API.  In particular, never forward
  // client-controlled proxy headers that could affect rate limiting or logs.
  for (const name of ["accept", "authorization", "content-type", "cookie", "origin", "referer", "x-request-id"]) {
    const value = context.request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const contentLength = Number(context.request.headers.get("content-length") || 0);
  if (contentLength > 16 * 1024 * 1024) {
    return new Response("Request too large", { status: 413 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  let upstream;
  try {
    upstream = await fetch(target, {
      method: context.request.method,
      headers,
      body: ["GET", "HEAD"].includes(context.request.method) ? undefined : context.request.body,
      redirect: "manual",
      signal: controller.signal,
    });
  } catch {
    return new Response("Upstream unavailable", { status: 502 });
  } finally {
    clearTimeout(timeout);
  }

  const responseHeaders = new Headers();
  for (const [key, value] of upstream.headers) {
    if (key.toLowerCase() !== "set-cookie") {
      responseHeaders.append(key, value);
    }
  }
  // Preserve each HttpOnly refresh cookie as a separate header.
  const setCookies = typeof upstream.headers.getSetCookie === "function"
    ? upstream.headers.getSetCookie()
    : [];
  for (const cookie of setCookies) {
    responseHeaders.append("set-cookie", cookie);
  }
  if (!setCookies.length) {
    const singleCookie = upstream.headers.get("set-cookie");
    if (singleCookie) responseHeaders.append("set-cookie", singleCookie);
  }
  responseHeaders.delete("content-length");
  responseHeaders.set("x-shoply-proxy", "cloudflare-pages");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

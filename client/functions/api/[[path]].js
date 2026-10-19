export async function onRequest(context) {
  const backendUrl = (context.env.BACKEND_URL || "").replace(/\/+$/, "");
  if (!backendUrl) {
    return new Response("BACKEND_URL is not configured", { status: 500 });
  }

  const incoming = new URL(context.request.url);
  const target = `${backendUrl}${incoming.pathname}${incoming.search}`;
  const headers = new Headers(context.request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const upstream = await fetch(target, {
    method: context.request.method,
    headers,
    body: ["GET", "HEAD"].includes(context.request.method)
      ? undefined
      : context.request.body,
    redirect: "manual",
  });

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
  responseHeaders.delete("content-length");
  responseHeaders.set("x-shoply-proxy", "cloudflare-pages");

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

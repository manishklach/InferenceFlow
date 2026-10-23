// A single read-only target. No server-side credential is injected or stored.
export async function GET(request: Request) {
  const authorization = request.headers.get("authorization") || "";
  if (!authorization.startsWith("Bearer ")) {
    return Response.json({ error: { message: "Metrics credential required" } }, { status: 401 });
  }
  try {
    const response = await fetch(`${process.env.API_PROXY_URL || "http://127.0.0.1:8080"}/internal/scheduling/report`, {
      headers: { Authorization: authorization }, cache: "no-store", signal: AbortSignal.timeout(15000),
    });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: { message: "Operator report unavailable" } }, { status: 502 });
  }
}

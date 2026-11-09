import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  const upstream = process.env.NEXUS_API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const target = new URL(`${upstream.replace(/\/$/, "")}/api/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const key of ["authorization", "content-type", "accept", "x-nexus-api-key", "x-nexus-tenant-id", "x-nexus-workspace-id"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const streamingUpload = request.method === "POST" && path.join("/") === "v1/uploads";
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    body: hasBody ? streamingUpload ? request.body : await request.arrayBuffer() : undefined,
    cache: "no-store",
    signal: request.signal,
    ...(streamingUpload ? { duplex: "half" } : {}),
  };
  const response = await fetch(target, init);
  const responseHeaders = new Headers();
  for (const key of ["content-type", "content-disposition", "x-content-type-options", "cache-control", "last-event-id", "x-accel-buffering"]) {
    const value = response.headers.get(key);
    if (value) responseHeaders.set(key, value);
  }
  return new Response(response.body, { status: response.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

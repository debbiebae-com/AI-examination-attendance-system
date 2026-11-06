import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
export const dynamic = "force-dynamic";
const readPaths =
  /^(live\/session|students|exams|exams\/\d+\/attendance|control\/(status|readiness))$/;
const writePaths =
  /^control\/(camera\/(start|stop|check)|sync|register|delete\/(preview|confirm))$/;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
  method: "GET" | "POST",
) {
  const { path } = await context.params;
  const route = path.join("/");
  if (!(method === "GET" ? readPaths : writePaths).test(route))
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  if (method === "POST") {
    const origin = request.headers.get("origin");
    const hosts = [
      request.headers.get("host"),
      request.headers.get("x-forwarded-host"),
    ];
    try {
      if (!origin || !hosts.includes(new URL(origin).host)) throw new Error();
    } catch {
      return NextResponse.json(
        { detail: "Cross-origin control request rejected" },
        { status: 403 },
      );
    }
    if (Number(request.headers.get("content-length") || 0) > 65536)
      return NextResponse.json(
        { detail: "Request too large" },
        { status: 413 },
      );
  }
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (route.startsWith("control/")) {
      // Server-only secret shared via the local checkout, never exposed to browser code.
      const keyPath =
        process.env.LOCAL_CONTROL_KEY_FILE ||
        resolve(process.cwd(), "../backend/data/control.key");
      try {
        headers["X-Local-Control"] = (
          await readFile(/* turbopackIgnore: true */ keyPath, "utf8")
        ).trim();
      } catch {
        return NextResponse.json(
          {
            detail:
              "Restart the updated backend API on this PC to enable demo controls.",
          },
          { status: 503 },
        );
      }
    }
    const body = method === "POST" ? await request.text() : undefined;
    if (body && body.length > 65536)
      return NextResponse.json(
        { detail: "Request too large" },
        { status: 413 },
      );
    const origin = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";
    const response = await fetch(
      `${origin}/${route}${request.nextUrl.search}`,
      {
        method,
        headers,
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      },
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail:
          "Local attendance API is unavailable. Start the backend on this PC.",
      },
      { status: 503 },
    );
  }
}
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "GET");
}
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "POST");
}

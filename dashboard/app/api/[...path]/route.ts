import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
// Browser requests remain same-origin. Only these read-only local API paths are allowed.
export async function GET(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const { path } = await context.params;
  const route = path.join("/");
  if (!/^(live\/session|students|exams|exams\/\d+\/attendance)$/.test(route))
    return NextResponse.json({detail: "Not found"}, {status: 404});
  try {
    const origin = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";
    const response = await fetch(`${origin}/${route}${request.nextUrl.search}`, {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    return new NextResponse(await response.text(), {status: response.status,
      headers: {"Content-Type": "application/json", "Cache-Control": "no-store"}});
  } catch {
    return NextResponse.json({detail: "Local attendance API is unavailable. Start the backend on this PC."}, {status: 503});
  }
}

import { NextRequest, NextResponse } from "next/server";
import { getAdminToken } from "@/lib/server-auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = await getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Se requiere rol administrador." }, { status: 403 });
  }

  const contentType = request.headers.get("content-type") ?? "";
  const body = await request.arrayBuffer();

  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND}/admin/ingest`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": contentType,
      },
      body,
    });
  } catch {
    return NextResponse.json({ detail: "No se puede conectar con el servidor." }, { status: 503 });
  }

  const data = await backendRes.json();
  return NextResponse.json(data, { status: backendRes.status });
}

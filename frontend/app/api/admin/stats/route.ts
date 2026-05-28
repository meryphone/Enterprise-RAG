import { NextResponse } from "next/server";
import { getAdminToken } from "@/lib/server-auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  const token = await getAdminToken();
  if (!token) {
    return NextResponse.json({ detail: "Se requiere rol administrador." }, { status: 403 });
  }

  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND}/admin/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    return NextResponse.json({ detail: "No se puede conectar con el servidor." }, { status: 503 });
  }

  const data = await backendRes.json();
  return NextResponse.json(data, { status: backendRes.status });
}

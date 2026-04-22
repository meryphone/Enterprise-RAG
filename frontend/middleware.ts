import { NextRequest, NextResponse } from "next/server";

/**
 * Route protection based on the httpOnly auth_token cookie.
 *
 * This only checks cookie *existence* for routing purposes — real signature
 * verification happens on the backend for every API call. An attacker who
 * manually sets auth_token=garbage reaches the main page but every API
 * request immediately returns 401 and triggers a redirect to /login.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get("auth_token")?.value;
  const { pathname } = request.nextUrl;

  if (!token && pathname !== "/login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (token && pathname === "/login") {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};

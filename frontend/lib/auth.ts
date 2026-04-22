/**
 * Auth helpers.
 *
 * The JWT lives exclusively in an httpOnly cookie set by the Next.js API
 * route /api/auth/login — JavaScript never touches the token value.
 * logout() calls the server-side route that clears the cookie.
 */

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
  window.location.href = "/login";
}

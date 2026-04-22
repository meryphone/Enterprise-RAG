"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";

/* ── Colour tokens (mirrors globals.css variables) ── */
const C = {
  navy950: "#0B1026", navy900: "#0F1733",
  navy700: "#1B2A6B", navy600: "#24358A",
  gold500: "#F5A800", gold600: "#D68F00",
  ink900: "#0E1220", ink700: "#2A2F40", ink500: "#5A607A",
  ink400: "#7C8299", ink300: "#A7ACBE", ink200: "#D5D8E2",
  ink100: "#E8EAF0",
  canvas: "#F6F6F3", white: "#FFFFFF",
  danger: "#C63A3A", ok: "#2FA36B",
} as const;

/* ── Inline SVG icons ── */
const Icon = {
  mail: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3.5" width="12" height="9" rx="1" /><path d="M2.5 4.5 8 9l5.5-4.5" />
    </svg>
  ),
  lock: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="7" width="10" height="7" rx="1" /><path d="M5 7V5a3 3 0 0 1 6 0v2" />
    </svg>
  ),
  eye: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" /><circle cx="8" cy="8" r="2" />
    </svg>
  ),
  eyeOff: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 3l10 10" /><path d="M6.5 6.5A2 2 0 0 0 8 10a2 2 0 0 0 1.5-.5" />
      <path d="M2 8s2-4.5 6-4.5c1 0 2 .3 2.8.8M14 8s-.6 1.4-2 2.6" />
    </svg>
  ),
  shield: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 2l5 2v4c0 3-2.5 5.5-5 6-2.5-.5-5-3-5-6V4z" /><path d="M6 8l1.5 1.5L10 7" />
    </svg>
  ),
  arrow: () => (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  ),
  dot: () => <svg width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3" fill="currentColor" /></svg>,
  check: () => (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8.5 6.5 12 13 5" />
    </svg>
  ),
};

/* ── Wordmark ── */
function Wordmark({ size = 20, dark = false }: { size?: number; dark?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, lineHeight: 1 }}>
      <div style={{
        width: size * 1.8, height: size * 1.8, background: C.navy950,
        border: "1px solid rgba(255,255,255,.14)", borderRadius: 6,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', sans-serif", fontWeight: 900,
        color: "#fff", fontSize: size * 1.1, letterSpacing: -0.5, position: "relative",
      }}>
        <span style={{ position: "relative", zIndex: 2 }}>i</span>
        <span style={{
          position: "absolute", right: 3, bottom: 2,
          width: size * 0.5, height: 2, background: C.gold500,
          transform: "rotate(-55deg)", transformOrigin: "right bottom",
        }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{
          fontFamily: "'Inter', sans-serif", fontWeight: 800,
          fontSize: size * 0.78, letterSpacing: -0.3,
          color: dark ? "#FFFFFF" : C.navy900,
        }}>
          intecsa<span style={{ color: C.gold500 }}>/</span>rag
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9.5, letterSpacing: 1.2,
          color: dark ? "rgba(255,255,255,.55)" : C.ink400,
          textTransform: "uppercase",
        }}>
          knowledge&nbsp;·&nbsp;v1.4
        </div>
      </div>
    </div>
  );
}

/* ── Hero mark ── */
function HeroMark() {
  const ticks: [number, number][] = [[-6, -6], [146, -6], [-6, 146], [146, 146]];
  return (
    <div style={{ position: "relative", width: 140, height: 140 }}>
      <div style={{
        width: 140, height: 140, borderRadius: 16, background: C.navy700,
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 18px 50px rgba(0,0,0,.45), inset 0 -4px 0 rgba(0,0,0,.22)",
        position: "relative",
      }}>
        <span style={{ fontFamily: "Inter", fontWeight: 900, fontSize: 100, color: "#fff", letterSpacing: -2 }}>i</span>
        <span style={{
          position: "absolute", right: 22, bottom: 20,
          width: 52, height: 5, background: C.gold500,
          transform: "rotate(-55deg)", transformOrigin: "right bottom",
        }} />
      </div>
      {ticks.map(([x, y], i) => (
        <span key={i} style={{
          position: "absolute", left: x, top: y, width: 12, height: 12,
          borderTop: y < 0 ? `1px solid ${C.gold500}` : "none",
          borderBottom: y > 0 ? `1px solid ${C.gold500}` : "none",
          borderLeft: x < 0 ? `1px solid ${C.gold500}` : "none",
          borderRight: x > 0 ? `1px solid ${C.gold500}` : "none",
        }} />
      ))}
    </div>
  );
}

/* ── Field ── */
interface FieldProps {
  icon?: React.ReactNode;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: React.ReactNode;
  right?: React.ReactNode;
  autoFocus?: boolean;
}

function Field({ icon, label, type = "text", value, onChange, placeholder, hint, right, autoFocus }: FieldProps) {
  const [focus, setFocus] = useState(false);
  return (
    <label style={{ display: "block" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 10.5, letterSpacing: 1.3, textTransform: "uppercase", color: C.ink500, fontWeight: 600 }}>
          {label}
        </span>
        {hint}
      </div>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        height: 40, padding: "0 12px", background: C.white,
        border: `1px solid ${focus ? C.navy700 : C.ink200}`, borderRadius: 6,
        boxShadow: focus ? "0 0 0 3px rgba(27,42,107,.10)" : "none",
        transition: "border-color .12s, box-shadow .12s",
      }}>
        {icon && <span style={{ color: focus ? C.navy700 : C.ink400 }}>{icon}</span>}
        <input
          type={type} value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
          placeholder={placeholder} autoFocus={autoFocus}
          style={{
            flex: 1, border: "none", outline: "none", background: "transparent",
            fontSize: 13.5, color: C.ink900, minWidth: 0, fontFamily: "inherit",
          }}
        />
        {right}
      </div>
    </label>
  );
}

/* ── Left panel ── */
function LeftPanel() {
  return (
    <div style={{
      flex: "1 1 560px", minWidth: 440, position: "relative",
      display: "flex", flexDirection: "column", padding: "36px 44px",
      color: "#E8EAF2", overflow: "hidden",
      backgroundColor: C.navy900,
      backgroundImage: [
        "linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px)",
        "linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px)",
        "linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px)",
        "linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px)",
      ].join(", "),
      backgroundSize: "80px 80px, 80px 80px, 16px 16px, 16px 16px",
      backgroundPosition: "-1px -1px, -1px -1px, -1px -1px, -1px -1px",
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, height: 3, width: 96, background: C.gold500 }} />
      <Wordmark size={18} dark />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", maxWidth: 460, gap: 28 }}>
        <HeroMark />
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 10.5, letterSpacing: 1.6, textTransform: "uppercase",
            color: C.gold500, fontWeight: 600, marginBottom: 12,
          }}>
            intecsa industrial · acceso restringido
          </div>
          <h1 style={{ margin: 0, fontSize: 30, fontWeight: 800, letterSpacing: -0.6, color: "#FFFFFF", lineHeight: 1.15 }}>
            Consulta técnica<br />
            <span style={{ color: C.gold500 }}>asistida</span> sobre tu corpus documental.
          </h1>
          <p style={{ marginTop: 14, fontSize: 13.5, color: "#B8BED6", lineHeight: 1.6, maxWidth: 420 }}>
            Respuestas citadas — sección y páginas — sobre especificaciones,
            procedimientos, datasheets y anexos de Intecsa y sus proyectos cliente.
          </p>
        </div>

        <div style={{
          display: "grid", gridTemplateColumns: "auto 1fr",
          columnGap: 18, rowGap: 10, fontSize: 12,
          paddingTop: 18, borderTop: "1px solid rgba(255,255,255,.08)", maxWidth: 420,
        }}>
          {([
            ["01", "Búsqueda híbrida sobre corpus documental corporativo"],
            ["02", "Permisos por corpus según rol y proyecto asignado"],
            ["03", "Respuestas con referencia a sección y página fuente"],
          ] as [string, string][]).map(([n, t]) => (
            <React.Fragment key={n}>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", color: C.gold500, fontWeight: 600 }}>{n}</span>
              <span style={{ color: "#D0D5E4" }}>{t}</span>
            </React.Fragment>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11, color: "#7B82A0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: C.ok, display: "inline-flex", animation: "pulse 1.6s ease-in-out infinite" }}><Icon.dot /></span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>servicio operativo</span>
          <span style={{ color: "#3D4670" }}>·</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>lat. 48ms</span>
        </div>
        <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>build 2026.04.22 · rag-1.4.0</span>
      </div>

      <span style={{ position: "absolute", right: 20, top: 20, width: 14, height: 14, borderTop: "1px solid rgba(245,168,0,.5)", borderRight: "1px solid rgba(245,168,0,.5)" }} />
      <span style={{ position: "absolute", right: 20, bottom: 20, width: 14, height: 14, borderBottom: "1px solid rgba(245,168,0,.5)", borderRight: "1px solid rgba(245,168,0,.5)" }} />
    </div>
  );
}

/* ── Login form (right panel) ── */
function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [pwd, setPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password: pwd, remember }),
        credentials: "same-origin",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErr(body.detail ?? "Credenciales incorrectas.");
        return;
      }
      router.push("/");
    } catch {
      setErr("Error de conexión. Inténtalo de nuevo.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      flex: "0 0 460px", background: C.white,
      borderLeft: `1px solid ${C.ink100}`,
      display: "flex", flexDirection: "column",
      padding: "36px 44px", position: "relative",
    }}>
      {/* Top strip */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 32 }}>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10, letterSpacing: 1.4, textTransform: "uppercase",
          color: C.ink400, display: "inline-flex", alignItems: "center", gap: 6,
          padding: "4px 8px", border: `1px solid ${C.ink200}`, borderRadius: 3,
        }}>
          <span style={{ color: C.gold500 }}><Icon.dot /></span>
          entorno: beta · corp
        </span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, color: C.ink400 }}>
          es · 22/04/2026
        </span>
      </div>

      {/* Heading */}
      <div style={{ marginBottom: 26 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: -0.4, color: C.navy900 }}>
          Iniciar sesión
        </h2>
        <p style={{ margin: "6px 0 0", fontSize: 13, color: C.ink500 }}>
          Usa tu cuenta corporativa de Intecsa Industrial.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field
          icon={<Icon.mail />} label="Correo corporativo" type="email"
          value={email} onChange={setEmail}
          placeholder="nombre.apellido@intecsaindustrial.com" autoFocus
        />
        <Field
          icon={<Icon.lock />} label="Contraseña"
          type={showPwd ? "text" : "password"}
          value={pwd} onChange={setPwd} placeholder="••••••••"
          right={
            <button type="button" onClick={() => setShowPwd((s) => !s)}
              title={showPwd ? "Ocultar" : "Mostrar"}
              style={{ color: C.ink400, display: "inline-flex", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
              {showPwd ? <Icon.eyeOff /> : <Icon.eye />}
            </button>
          }
        />

        {/* Remember checkbox */}
        <div style={{ display: "flex", alignItems: "center", marginTop: 2 }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer", userSelect: "none" }}>
            <span onClick={() => setRemember((r) => !r)} style={{
              width: 16, height: 16, borderRadius: 3,
              background: remember ? C.navy700 : C.white,
              border: `1px solid ${remember ? C.navy700 : C.ink300}`,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              color: C.white, cursor: "pointer",
            }}>
              {remember && <Icon.check />}
            </span>
            <span style={{ fontSize: 12, color: C.ink700 }}>Mantener la sesión en este dispositivo</span>
          </label>
        </div>

        {/* Error banner */}
        {err && (
          <div style={{
            fontSize: 12, color: C.danger, padding: "8px 12px",
            background: "#FDF2F2", borderRadius: 4, border: "1px solid #F9C8C8",
          }}>
            {err}
          </div>
        )}

        {/* Submit */}
        <button type="submit" disabled={submitting} style={{
          marginTop: 8, height: 44,
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          background: submitting ? "#FBE5AB" : C.gold500,
          color: C.navy900, borderRadius: 6, fontWeight: 700, fontSize: 13,
          cursor: submitting ? "not-allowed" : "pointer",
          transition: "background .12s", border: "none", width: "100%", fontFamily: "inherit",
        }}
          onMouseEnter={(e) => { if (!submitting) (e.currentTarget as HTMLButtonElement).style.background = C.gold600; }}
          onMouseLeave={(e) => { if (!submitting) (e.currentTarget as HTMLButtonElement).style.background = C.gold500; }}
        >
          {submitting ? "Autenticando…" : <><span>Entrar</span> <Icon.arrow /></>}
        </button>
      </form>

      {/* Footer notice */}
      <div style={{
        marginTop: "auto", paddingTop: 24,
        borderTop: `1px solid ${C.ink100}`,
        fontSize: 11, color: C.ink500, lineHeight: 1.55,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
          <span style={{ color: C.navy700 }}><Icon.shield /></span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: "uppercase", fontSize: 10, letterSpacing: 1.2, fontWeight: 600, color: C.ink700,
          }}>aviso de uso</span>
        </div>
        El acceso a IntecsaRAG queda registrado. Toda consulta es auditable conforme
        a la política de seguridad de la información y al contrato de tratamiento de datos
        con los clientes cuyos corpus son accedidos.
        <div style={{ marginTop: 10, display: "flex", gap: 14, color: C.ink400 }}>
          <span>Soporte IT</span>
          <span>Política de privacidad</span>
          <span>Estado del servicio</span>
        </div>
      </div>
    </div>
  );
}

/* ── Page ── */
export default function LoginPage() {
  return (
    <>
      <style>{`@keyframes pulse { 0%,100%{opacity:.35} 50%{opacity:1} }`}</style>
      <div style={{ minHeight: "100vh", display: "flex", background: C.canvas }}>
        <LeftPanel />
        <LoginForm />
      </div>
    </>
  );
}

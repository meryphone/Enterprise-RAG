"use client";

import type { Scope } from "@/lib/types";

export type SystemStatus = "connected" | "processing" | "offline";

const STATUS_CONFIG: Record<SystemStatus, { color: string; label: string; sub: string }> = {
  connected:  { color: "var(--ok)",       label: "Conectado",   sub: "índice sincronizado"    },
  processing: { color: "var(--gold-500)", label: "Procesando",  sub: "recuperando fragmentos" },
  offline:    { color: "var(--danger)",   label: "Sin conexión", sub: "reintentando…"          },
};

const IFolder = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M2 4h4l1 1h7v7H2z"/>
  </svg>
);
const IDot = () => (
  <svg width="8" height="8" viewBox="0 0 8 8">
    <circle cx="4" cy="4" r="3" fill="currentColor"/>
  </svg>
);

interface Props {
  scope: Scope;
  status: SystemStatus;
}

export function Topbar({ scope, status }: Props) {
  const s = STATUS_CONFIG[status];

  return (
    <div style={{
      height: 52, flexShrink: 0,
      display: "flex", alignItems: "center", gap: 14,
      padding: "0 18px",
      background: "#FFFFFF",
      borderBottom: "1px solid var(--ink-100)",
      overflow: "hidden",
    }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, flex: 1 }}>
        <span style={{
          fontSize: 10, letterSpacing: 1.4, textTransform: "uppercase",
          color: "var(--ink-400)", fontWeight: 600, whiteSpace: "nowrap",
        }}>
          Corpus
        </span>
        <span style={{ color: "var(--ink-300)" }}>/</span>
        <span style={{ color: "var(--navy-700)", display: "flex", flexShrink: 0 }}>
          <IFolder />
        </span>
        <span style={{
          fontSize: 14, fontWeight: 700, color: "var(--navy-900)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {scope.label}
        </span>
        <span style={{
          fontSize: 10.5, color: "var(--ink-400)",
          padding: "2px 6px", border: "1px solid var(--ink-200)", borderRadius: 3,
          fontFamily: "'JetBrains Mono', monospace", whiteSpace: "nowrap", flexShrink: 0,
        }}>
          {scope.coleccion}
        </span>
      </div>

      {/* Scope description */}
      {scope.scope_desc && (
        <>
          <div style={{ width: 1, height: 22, background: "var(--ink-100)", flexShrink: 0 }} />
          <div style={{
            fontSize: 12, color: "var(--ink-500)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            maxWidth: 300,
          }}>
            {scope.scope_desc}
          </div>
        </>
      )}

      {/* Stats */}
      {scope.docs !== undefined && (
        <>
          <div style={{ width: 1, height: 22, background: "var(--ink-100)", flexShrink: 0 }} />
          <div style={{
            display: "flex", gap: 12, fontSize: 11, color: "var(--ink-500)",
            fontFamily: "'JetBrains Mono', monospace", whiteSpace: "nowrap",
          }}>
            <span>
              <span style={{ color: "var(--ink-700)", fontWeight: 600 }}>
                {scope.docs.toLocaleString("es")}
              </span>{" "}docs
            </span>
            {scope.updated && (
              <span>
                act. <span style={{ color: "var(--ink-700)" }}>{scope.updated}</span>
              </span>
            )}
          </div>
        </>
      )}

      <div style={{ width: 1, height: 22, background: "var(--ink-100)", flexShrink: 0 }} />

      {/* Status pill */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "5px 10px",
        border: "1px solid var(--ink-200)",
        borderRadius: 20, background: "#FAFBFD",
        flexShrink: 0,
      }}>
        <span
          className={status === "processing" ? "dot-pulse" : ""}
          style={{ color: s.color, display: "inline-flex" }}
        >
          <IDot />
        </span>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-900)" }}>{s.label}</span>
          <span style={{ fontSize: 9.5, color: "var(--ink-400)", fontFamily: "'JetBrains Mono', monospace" }}>
            {s.sub}
          </span>
        </div>
      </div>
    </div>
  );
}

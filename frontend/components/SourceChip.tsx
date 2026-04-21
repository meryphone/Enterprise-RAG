"use client";

import type { SourceRef } from "@/lib/types";

const ILink = () => (
  <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M6 10a3 3 0 0 0 4 0l2-2a3 3 0 0 0-4-4"/>
    <path d="M10 6a3 3 0 0 0-4 0L4 8a3 3 0 0 0 4 4"/>
  </svg>
);
const ICopy = () => (
  <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="5" y="5" width="9" height="9" rx="1"/><path d="M11 5V3H2v9h2"/>
  </svg>
);

interface Props {
  source: SourceRef;
  index: number;
}

export function SourceChip({ source, index }: Props) {
  const code = source.doc.replace(/\.pdf$/i, "");
  const isAnnex = source.es_anexo;

  const pages =
    source.pagina_inicio === -1
      ? null
      : source.pagina_inicio === source.pagina_fin || source.pagina_fin === -1
        ? `p. ${source.pagina_inicio}`
        : `pp. ${source.pagina_inicio}–${source.pagina_fin}`;

  const citaText = [source.titulo || code, source.version ? `Ed. ${source.version}` : null, source.seccion || null, pages]
    .filter(Boolean)
    .join(" · ");

  return (
    <span className="tt">
      {/* Chip button */}
      <span style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "3px 8px 3px 6px",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11, fontWeight: 500,
        color: isAnnex ? "#5A3F00" : "var(--navy-700)",
        background: isAnnex ? "var(--gold-050)" : "#EEF1FB",
        border: `1px solid ${isAnnex ? "var(--gold-500)" : "#C7D0EA"}`,
        borderRadius: 4, cursor: "default", lineHeight: 1.3,
        userSelect: "none",
      }}>
        <span style={{
          fontSize: 9.5,
          color: isAnnex ? "var(--gold-600)" : "var(--navy-500)",
          fontWeight: 600, minWidth: 14, textAlign: "right",
        }}>
          {String(index).padStart(2, "0")}
        </span>
        <span>[{code}]</span>
        {pages && (
          <span style={{ opacity: 0.65, fontSize: 10 }}>{pages}</span>
        )}
      </span>

      {/* CSS Tooltip */}
      <div className="tt-body">
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase",
          color: isAnnex ? "var(--gold-500)" : "#9BA4C5",
          fontWeight: 600, marginBottom: 4,
        }}>
          {isAnnex ? "Anexo" : "Documento base"} · {code}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#fff", marginBottom: 6 }}>
          {source.titulo || code}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, color: "#B8BED6", fontSize: 11.5 }}>
          {source.version && (
            <div>
              <span style={{ color: "#7B82A0" }}>Edición: </span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{source.version}</span>
            </div>
          )}
          {source.seccion && (
            <div>
              <span style={{ color: "#7B82A0" }}>Sección: </span>
              {source.seccion}
            </div>
          )}
          {pages && (
            <div>
              <span style={{ color: "#7B82A0" }}>Páginas: </span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{pages}</span>
            </div>
          )}
        </div>
        <div style={{
          marginTop: 10, display: "flex", gap: 6,
          paddingTop: 8, borderTop: "1px solid #2A2F40",
        }}>
          <button
            onClick={() => navigator.clipboard.writeText(citaText)}
            style={{
              fontSize: 11, color: "#B8BED6",
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "4px 8px", border: "1px solid #2A2F40", borderRadius: 4,
              background: "none", cursor: "pointer", fontFamily: "inherit",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "#fff"; e.currentTarget.style.borderColor = "#3B4780"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "#B8BED6"; e.currentTarget.style.borderColor = "#2A2F40"; }}
          >
            <ICopy /> Copiar cita
          </button>
        </div>
      </div>
    </span>
  );
}

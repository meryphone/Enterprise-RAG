"use client";

import type { Message, SourceRef } from "@/lib/types";
import { SourceChip } from "./SourceChip";

function renderMarkdown(text: string): React.ReactNode[] {
  // Normalizar: insertar salto antes de ítems numerados inline ("... 2. **X**")
  const normalized = text
    .replace(/ (\d+\. \*\*)/g, "\n$1")
    .replace(/ (\d+\. )(?=[A-ZÁÉÍÓÚÑ])/g, "\n$1");

  const lines = normalized.split("\n");
  const nodes: React.ReactNode[] = [];

  lines.forEach((line, li) => {
    if (li > 0) nodes.push(<br key={`br${li}`} />);

    // Parsear **negrita** dentro de cada línea
    line.split(/(\*\*[^*\n]+\*\*)/g).forEach((part, pi) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        nodes.push(<strong key={`${li}-${pi}`}>{part.slice(2, -2)}</strong>);
      } else if (part) {
        nodes.push(<span key={`${li}-${pi}`}>{part}</span>);
      }
    });
  });

  return nodes;
}

const ICopy = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="5" y="5" width="9" height="9" rx="1"/><path d="M11 5V3H2v9h2"/>
  </svg>
);


function ActionBtn({
  icon, label, onClick,
}: { icon: React.ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 6px", borderRadius: 3,
        fontSize: 11, color: "var(--ink-400)",
        background: "transparent", border: "none", cursor: "pointer",
        fontFamily: "inherit",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "var(--ink-050)"; e.currentTarget.style.color = "var(--ink-700)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink-400)"; }}
    >
      {icon} {label}
    </button>
  );
}

interface Props {
  message: Message;
}

function limpiarMarcadores(texto: string): string {
  return texto.replace(/\[(\d+)\]/g, "").replace(/ +/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function parsearRefsUsadas(texto: string): Set<number> {
  const refs = new Set<number>();
  for (const m of texto.matchAll(/\[(\d+)\]/g)) refs.add(parseInt(m[1], 10));
  return refs;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const ts = message.timestamp ?? "";

  /* Solo mostrar las fuentes que el LLM citó explícitamente con [N].
     Si no hay marcadores en el texto, no se muestra ninguna. */
  const refsUsadas = !message.streaming && message.sources
    ? parsearRefsUsadas(message.content)
    : null;
  const fuentes: SourceRef[] = message.sources && refsUsadas && refsUsadas.size > 0
    ? message.sources.filter((s) => refsUsadas.has(s.ref))
    : [];
  const texto = !message.streaming && refsUsadas
    ? limpiarMarcadores(message.content)
    : message.content;

  // Deduplicar: mismo doc + misma página = misma fuente. Conservar la primera aparición.
  const fuentesVisibles = fuentes.reduce<SourceRef[]>((acc, src) => {
    const clave = `${src.doc}|${src.pagina_inicio}`;
    if (!acc.some((s) => `${s.doc}|${s.pagina_inicio}` === clave)) acc.push(src);
    return acc;
  }, []);

  /* ── USER message ─────────────────────────────────────────── */
  if (isUser) {
    return (
      <div style={{
        display: "flex", justifyContent: "flex-end",
        padding: "10px 22px 10px 90px",
      }}>
        <div style={{ maxWidth: "min(640px, 72%)" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end",
            marginBottom: 4, fontSize: 10.5, color: "var(--ink-400)",
          }}>
            <span>María C.</span>
            {ts && <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{ts}</span>}
            <div style={{
              width: 18, height: 18, borderRadius: 3,
              background: "linear-gradient(180deg,#24358A,#1B2A6B)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 9, fontWeight: 700,
            }}>MC</div>
          </div>
          <div style={{
            background: "var(--navy-700)", color: "#FFFFFF",
            padding: "10px 14px",
            borderRadius: "8px 8px 2px 8px",
            fontSize: 13.5, lineHeight: 1.55,
            boxShadow: "0 1px 0 rgba(0,0,0,.05)",
            whiteSpace: "pre-wrap",
          }}>
            {texto}
          </div>
        </div>
      </div>
    );
  }

  /* ── ASSISTANT message ────────────────────────────────────── */
  return (
    <div style={{
      display: "flex", justifyContent: "flex-start",
      padding: "10px 90px 10px 22px",
    }}>
      <div style={{ maxWidth: "min(720px, 80%)" }}>
        {/* Header row */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          marginBottom: 4, fontSize: 10.5, color: "var(--ink-400)",
        }}>
          <div style={{
            width: 18, height: 18, borderRadius: 3,
            background: "var(--navy-700)", position: "relative",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 10, fontWeight: 800,
          }}>
            i
            <span style={{
              position: "absolute", right: 2, bottom: 2,
              width: 7, height: 1.5, background: "var(--gold-500)",
              transform: "rotate(-55deg)", transformOrigin: "right bottom",
            }} />
          </div>
          <span style={{ fontWeight: 600, color: "var(--ink-700)" }}>IntecsaRAG</span>
          {ts && <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{ts}</span>}
          {message.streaming && (
            <span style={{
              fontSize: 10, color: "var(--gold-600)", fontWeight: 600,
              display: "inline-flex", alignItems: "center", gap: 4,
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              <span className="dot-pulse" style={{ color: "var(--gold-500)", display: "inline-flex" }}>
                <svg width="8" height="8" viewBox="0 0 8 8">
                  <circle cx="4" cy="4" r="3" fill="currentColor"/>
                </svg>
              </span>
              generando…
            </span>
          )}
        </div>

        {/* Message bubble */}
        <div style={{
          background: "#FFFFFF",
          border: "1px solid var(--ink-100)",
          borderLeft: "3px solid var(--navy-700)",
          padding: "12px 14px",
          borderRadius: "2px 8px 8px 8px",
          fontSize: 13.5, lineHeight: 1.6,
          color: "var(--ink-900)", whiteSpace: "pre-wrap",
        }}>
          {message.streaming ? texto : renderMarkdown(texto)}
          {message.streaming && <span className="caret" />}
        </div>

        {/* Sources */}
        {!message.streaming && fuentesVisibles.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase",
              color: "var(--ink-400)", fontWeight: 600, marginBottom: 6,
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span>{fuentesVisibles.length} fuente{fuentesVisibles.length !== 1 ? "s" : ""}</span>
              <span style={{ flex: 1, height: 1, background: "var(--ink-100)" }} />
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {fuentesVisibles.map((s, i) => (
                <SourceChip key={s.ref} source={s} index={i + 1} />
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        {!message.streaming && (
          <div style={{ marginTop: 6, display: "flex", gap: 2 }}>
            <ActionBtn
              icon={<ICopy />}
              label="Copiar"
              onClick={() => navigator.clipboard.writeText(texto)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

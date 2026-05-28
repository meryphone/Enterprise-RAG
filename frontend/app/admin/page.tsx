"use client";

import { useState, useRef, useMemo, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { Scope, UserInfo } from "@/lib/types";
import { fetchScopes } from "@/lib/api";

/* ── Icons ──────────────────────────────────────────────────── */
const IBack = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
    <path d="M7 4 3 8l4 4M3 8h10"/>
  </svg>
);
const IDoc = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M4 2h6l2 2v10H4z"/><path d="M6 6h4M6 9h4M6 12h3"/>
  </svg>
);
const IUpload = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <path d="M8 11V3M4 7l4-4 4 4"/><path d="M2 13h12"/>
  </svg>
);
const IUploadBig = () => (
  <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 19h16"/>
  </svg>
);
const IX = () => (
  <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
    <path d="M4 4l8 8M12 4l-8 8"/>
  </svg>
);
const ICheck = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 8.5 6.5 12 13 5"/>
  </svg>
);
const IInfo = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="8" cy="8" r="6"/><path d="M8 7v4M8 5v.5"/>
  </svg>
);
const ISpin = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    style={{ animation: "spin 1s linear infinite" }}>
    <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    <path d="M8 2a6 6 0 1 1-6 6"/>
  </svg>
);
const IDot = ({ color }: { color: string }) => (
  <svg width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3" fill={color}/></svg>
);
const IShield = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M8 2l5 2v4c0 3-2.5 5.5-5 6-2.5-.5-5-3-5-6V4z"/><path d="M6 8l1.5 1.5L10 7"/>
  </svg>
);

/* ── Wordmark ────────────────────────────────────────────────── */
function Wordmark() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, lineHeight: 1 }}>
      <div style={{
        width: 30, height: 30, background: "#0B1026",
        border: "1px solid rgba(255,255,255,.14)", borderRadius: 6,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', sans-serif", fontWeight: 900,
        color: "#fff", fontSize: 18, letterSpacing: -0.5, position: "relative",
      }}>
        <span style={{ position: "relative", zIndex: 2 }}>i</span>
        <span style={{
          position: "absolute", right: 3, bottom: 2,
          width: 9, height: 2, background: "var(--gold-500)",
          transform: "rotate(-55deg)", transformOrigin: "right bottom",
        }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontFamily: "'Inter',sans-serif", fontWeight: 800, fontSize: 14, letterSpacing: -0.3, color: "#FFFFFF" }}>
          intecsa<span style={{ color: "var(--gold-500)" }}>/</span>rag
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 9.5, letterSpacing: 1.2, color: "rgba(255,255,255,.55)", textTransform: "uppercase" }}>
          knowledge
        </div>
      </div>
    </div>
  );
}

/* ── Data (static) ──────────────────────────────────────────── */

const TIPOS_DOC = [
  { v: "procedimiento",        l: "PR · Procedimiento" },
  { v: "instruccion_trabajo",  l: "IN · Instrucción de trabajo" },
  { v: "especificacion",       l: "ES · Especificación técnica" },
  { v: "datasheet",            l: "DS · Datasheet" },
  { v: "pid",                  l: "PID · P&ID / Plano de proceso" },
  { v: "manual",               l: "MN · Manual" },
  { v: "nota_tecnica",         l: "NT · Nota técnica" },
  { v: "anexo",                l: "ANX · Anexo" },
  { v: "informe",              l: "INF · Informe" },
];

const IDIOMAS = [
  { v: "es", l: "es · Español" },
  { v: "en", l: "en · Inglés" },
  { v: "pt", l: "pt · Portugués" },
  { v: "fr", l: "fr · Francés" },
];


interface QueueFile { id: string; name: string; size: string; file: File; status?: "pendiente" | "procesando" | "listo" | "error"; }
interface Meta { empresa: string; proyecto_id: string; tipo_doc: string; idioma: string; }
interface CorpusStat { nombre: string; chunks: number; es_global: boolean; }
interface IndexStats { corpus: CorpusStat[]; total_chunks: number; total_corpus: number; }
interface EmpresaOption { v: string; l: string; }
interface ProyectoOption { v: string; l: string; }

/* ── Shared field styles ─────────────────────────────────────── */
const fieldSelect: React.CSSProperties = {
  width: "100%", height: 34, appearance: "none",
  backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10' fill='none' stroke='%235A607A' stroke-width='1.6'><path d='M2 4l3 3 3-3'/></svg>\")",
  backgroundRepeat: "no-repeat", backgroundPosition: "right 10px center",
  backgroundColor: "#fff", border: "1px solid var(--ink-200)", borderRadius: 5,
  padding: "0 28px 0 10px", fontSize: 12.5, outline: "none",
  color: "var(--ink-900)", fontFamily: "inherit",
};

/* ── AdminHeader ────────────────────────────────────────────── */
function AdminHeader({ user }: { user: UserInfo | null }) {
  const initials = (name: string) =>
    name.split(" ").filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");

  return (
    <header style={{ background: "#0F1733", borderBottom: "1px solid rgba(255,255,255,.06)", color: "#E8EAF2" }}>
      <div style={{ height: 3, background: "var(--gold-500)", width: 96 }} />
      <div style={{ height: 56, display: "flex", alignItems: "center", padding: "0 20px", gap: 16 }}>
        <Wordmark />
        <div style={{ width: 1, height: 24, background: "rgba(255,255,255,.10)" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
          <a href="/" style={{ color: "#A7ACBE", display: "inline-flex", alignItems: "center", gap: 6 }}>
            <IBack /> Volver al chat
          </a>
          <span style={{ color: "#3D4670" }}>/</span>
          <span style={{ color: "#fff", fontWeight: 600 }}>Administración</span>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          fontSize: 10.5, color: "#A7ACBE",
          padding: "4px 9px", border: "1px solid rgba(255,255,255,.12)", borderRadius: 3,
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          <span className="dot-pulse" style={{ color: "var(--ok)", display: "inline-flex" }}>
            <IDot color="var(--ok)" />
          </span>
          entorno: corp
        </div>
        {user && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 26, height: 26, borderRadius: 4,
              background: "linear-gradient(180deg,#24358A,#1B2A6B)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 11, fontWeight: 700,
            }}>{initials(user.full_name)}</div>
            <div style={{ lineHeight: 1.2 }}>
              <div style={{ fontSize: 12, color: "#EEF0F8", fontWeight: 600 }}>{user.full_name}</div>
              <div style={{ fontSize: 9.5, color: "#7B82A0", fontFamily: "'JetBrains Mono', monospace", display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ color: "var(--gold-500)", fontWeight: 600 }}>admin</span>
                <span style={{ color: "#3D4670" }}>·</span>
                <span>permisos: todos</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

/* ── FileQueue ──────────────────────────────────────────────── */
function FileQueue({ files, setFiles }: { files: QueueFile[]; setFiles: React.Dispatch<React.SetStateAction<QueueFile[]>> }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const addFiles = (raw: FileList | null) => {
    if (!raw) return;
    const list = Array.from(raw).map(f => ({
      id: crypto.randomUUID(),
      name: f.name,
      size: f.size > 1024 * 1024 ? (f.size / 1024 / 1024).toFixed(1) + " MB" : Math.round(f.size / 1024) + " KB",
      file: f,
    }));
    setFiles(prev => [...prev, ...list]);
  };

  return (
    <section style={{ background: "#fff", border: "1px solid var(--ink-100)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--ink-100)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: "var(--navy-700)" }}><IUpload /></span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--ink-900)" }}>Fuente</div>
          <div style={{ fontSize: 10.5, color: "var(--ink-400)" }}>
            Sube uno o varios ficheros · pdf, docx, xlsx, pptx, md (máx. 80 MB por archivo)
          </div>
        </div>
        <span style={{ fontSize: 10, color: "var(--ink-500)", padding: "2px 6px", border: "1px solid var(--ink-200)", borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>
          paso 1 / 2
        </span>
      </div>

      <div
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        style={{
          margin: 14,
          border: "1.5px dashed " + (drag ? "var(--gold-500)" : "var(--ink-200)"),
          background: drag ? "var(--gold-050)" : "#FAFBFD",
          borderRadius: 6, padding: "26px 16px",
          display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
          cursor: "pointer", transition: "all .15s",
        }}>
        <span style={{ color: drag ? "var(--gold-600)" : "var(--navy-700)" }}><IUploadBig /></span>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-900)", textAlign: "center" }}>
          Arrastra ficheros aquí o <span style={{ color: "var(--navy-600)", textDecoration: "underline" }}>selecciónalos del disco</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-500)" }}>
          Los metadatos del panel derecho se aplicarán al lote completo.
        </div>
        <input ref={inputRef} type="file" multiple style={{ display: "none" }} onChange={e => addFiles(e.target.files)} />
      </div>

      <div style={{ borderTop: "1px solid var(--ink-100)" }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 14px", fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase" as const,
          color: "var(--ink-500)", fontWeight: 600,
          background: "#FAFBFD", borderBottom: "1px solid var(--ink-100)",
        }}>
          <span>Cola · {files.length} ficheros</span>
          {files.some(f => f.status !== "procesando") && (
            <button onClick={() => setFiles(prev => prev.filter(f => f.status === "procesando"))} style={{ fontSize: 10, color: "var(--ink-500)", letterSpacing: 1.2, textTransform: "uppercase" as const, fontFamily: "inherit", background: "none", border: "none", cursor: "pointer" }}>
              vaciar
            </button>
          )}
        </div>
        {files.length === 0 ? (
          <div style={{ padding: "18px 14px", textAlign: "center", color: "var(--ink-400)", fontSize: 11.5 }}>
            Aún no has añadido ningún fichero.
          </div>
        ) : files.map((f, i) => (
          <div key={f.id} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
            borderBottom: i === files.length - 1 ? "none" : "1px solid var(--ink-100)",
          }}>
            <span style={{ color: "var(--navy-700)" }}><IDoc /></span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, color: "var(--ink-900)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</div>
              <div style={{ fontSize: 10, color: "var(--ink-400)", fontFamily: "'JetBrains Mono', monospace" }}>{f.size}</div>
            </div>
            {f.status === "procesando" ? (
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "var(--gold-600)", padding: "2px 6px", border: "1px solid rgba(180,130,0,.3)", borderRadius: 3, background: "rgba(180,130,0,.06)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                <ISpin /> procesando…
              </span>
            ) : f.status === "listo" ? (
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "var(--ok)", padding: "2px 6px", border: "1px solid rgba(47,163,107,.3)", borderRadius: 3, background: "rgba(47,163,107,.06)" }}>
                listo
              </span>
            ) : f.status === "error" ? (
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "var(--danger)", padding: "2px 6px", border: "1px solid rgba(200,50,50,.3)", borderRadius: 3, background: "rgba(200,50,50,.06)" }}>
                error
              </span>
            ) : (
              <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: "var(--ink-400)", padding: "2px 6px", border: "1px solid var(--ink-200)", borderRadius: 3 }}>
                en cola
              </span>
            )}
            <button
              onClick={() => setFiles(prev => prev.filter(p => p.id !== f.id))}
              disabled={f.status === "procesando"}
              style={{ color: f.status === "procesando" ? "var(--ink-200)" : "var(--ink-400)", padding: 4, background: "none", border: "none", cursor: f.status === "procesando" ? "not-allowed" : "pointer", display: "flex" }}
            >
              <IX />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── MetaField ──────────────────────────────────────────────── */
function MetaField({ code, label, required, hint, children }: {
  code: string; label: string; required?: boolean; hint?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
          <span style={{ fontSize: 10.5, color: "var(--navy-700)", fontWeight: 600, padding: "1px 5px", background: "#EEF1FB", border: "1px solid #C7D0EA", borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>{code}</span>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-900)" }}>{label}</span>
          {required && <span style={{ color: "var(--danger)", fontSize: 12 }}>*</span>}
        </div>
        <span style={{ fontSize: 9.5, color: "var(--gold-600)", fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: 1.1, display: "inline-flex", alignItems: "center", gap: 4, fontFamily: "'JetBrains Mono', monospace" }}>
          <IShield /> administrador
        </span>
      </div>
      {children}
      {hint && (
        <div style={{ fontSize: 11, color: "var(--ink-500)", lineHeight: 1.5, display: "flex", gap: 6 }}>
          <span style={{ color: "var(--ink-400)", paddingTop: 2, flexShrink: 0 }}><IInfo /></span>
          <span>{hint}</span>
        </div>
      )}
    </div>
  );
}

/* ── MetadataForm ───────────────────────────────────────────── */
function MetadataForm({ meta, setMeta, onSubmit, hasPending, submitting, empresas, proyectosByEmpresa }: {
  meta: Meta; setMeta: React.Dispatch<React.SetStateAction<Meta>>;
  onSubmit: () => void; hasPending: boolean; submitting: boolean;
  empresas: EmpresaOption[]; proyectosByEmpresa: Record<string, ProyectoOption[]>;
}) {
  const isGlobal = meta.empresa === "intecsa";
  const proyectos = proyectosByEmpresa[meta.empresa] || [];

  const set = useCallback(<K extends keyof Meta>(k: K, v: Meta[K]) => {
    setMeta(prev => {
      const next = { ...prev, [k]: v };
      if (k === "empresa") next.proyecto_id = "";
      return next;
    });
  }, [setMeta]);

  const slug = useMemo(() => {
    if (!meta.empresa) return "—";
    return meta.empresa === "intecsa" ? "intecsa-global" : `${meta.empresa}${meta.proyecto_id ? "-" + meta.proyecto_id : ""}`;
  }, [meta.empresa, meta.proyecto_id]);

  const docPreview = useMemo(() => {
    if (!meta.tipo_doc) return "—";
    return `${meta.tipo_doc}-XXX`;
  }, [meta.tipo_doc]);

  const metaValid = !!meta.empresa && !!meta.tipo_doc && !!meta.idioma &&
    (meta.empresa === "intecsa" || !!meta.proyecto_id);
  const canSubmit = hasPending && metaValid && !submitting;

  return (
    <section style={{ background: "#fff", border: "1px solid var(--ink-100)", borderRadius: 8 }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--ink-100)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: "var(--navy-700)" }}><IDoc /></span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--ink-900)" }}>Metadatos del lote</div>
          <div style={{ fontSize: 10.5, color: "var(--ink-400)" }}>
            Se aplican a todos los ficheros en cola. Los campos restringidos sólo los puede modificar un administrador.
          </div>
        </div>
        <span style={{ fontSize: 10, color: "var(--ink-500)", padding: "2px 6px", border: "1px solid var(--ink-200)", borderRadius: 3, fontFamily: "'JetBrains Mono', monospace" }}>
          paso 2 / 2
        </span>
      </div>

      <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 18 }}>
        {/* empresa */}
        <MetaField code="empresa" label="Empresa / scope" required
          hint={<><b>intecsa</b> = corpus global; otro valor = cliente. Define el scope del corpus en el que se indexa el documento.</>}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "center" }}>
            <select style={fieldSelect} value={meta.empresa} onChange={e => set("empresa", e.target.value)}>
              <option value="">— seleccionar —</option>
              {empresas.map(e => <option key={e.v} value={e.v}>{e.l}</option>)}
            </select>
            {meta.empresa && (
              <span style={{ fontSize: 10.5, padding: "4px 8px", borderRadius: 3, fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, color: isGlobal ? "var(--navy-700)" : "var(--gold-600)", background: isGlobal ? "#EEF1FB" : "var(--gold-050)", border: "1px solid " + (isGlobal ? "#C7D0EA" : "var(--gold-500)"), whiteSpace: "nowrap" as const }}>
                scope: {isGlobal ? "global" : "cliente"}
              </span>
            )}
          </div>
        </MetaField>

        {/* proyecto_id */}
        <MetaField code="proyecto_id" label="ID de proyecto"
          hint={<>Déjalo vacío para corpus global de Intecsa. Identifica el proyecto dentro del cliente.</>}>
          {isGlobal ? (
            <div style={{ height: 34, display: "flex", alignItems: "center", padding: "0 10px", borderRadius: 5, border: "1px dashed var(--ink-200)", background: "var(--ink-050)", fontSize: 12, color: "var(--ink-400)", fontFamily: "'JetBrains Mono', monospace" }}>
              vacío · no aplica en corpus global
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}>
              <select style={fieldSelect} value={meta.proyecto_id} onChange={e => set("proyecto_id", e.target.value)} disabled={!meta.empresa}>
                <option value="">{meta.empresa ? "— seleccionar proyecto —" : "— elige primero la empresa —"}</option>
                {proyectos.map(p => <option key={p.v} value={p.v}>{p.v} · {p.l}</option>)}
              </select>
              <button type="button" style={{ height: 34, padding: "0 10px", fontSize: 11.5, fontWeight: 600, border: "1px solid var(--ink-200)", borderRadius: 5, color: "var(--navy-700)", background: "#fff", fontFamily: "inherit", cursor: "pointer" }}>
                + nuevo
              </button>
            </div>
          )}
        </MetaField>

        {/* tipo_doc */}
        <MetaField code="tipo_doc" label="Tipo de documento" required
          hint={<>Procedimiento, instrucción, datasheet, etc. Se <b>embebe como prefijo</b> en los chunks y se muestra al usuario en los chips de fuente.</>}>
          <select style={fieldSelect} value={meta.tipo_doc} onChange={e => set("tipo_doc", e.target.value)}>
            <option value="">— seleccionar tipo —</option>
            {TIPOS_DOC.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select>
        </MetaField>

        {/* idioma */}
        <MetaField code="idioma" label="Idioma (ISO 639-1)" required
          hint={<>Código ISO del idioma del documento. Reservado para filtrado multilingüe futuro.</>}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {IDIOMAS.map(i => (
              <button key={i.v} type="button" onClick={() => set("idioma", i.v)} style={{
                padding: "6px 10px", fontSize: 12,
                border: "1px solid " + (meta.idioma === i.v ? "var(--navy-700)" : "var(--ink-200)"),
                background: meta.idioma === i.v ? "#EEF1FB" : "#fff",
                color: meta.idioma === i.v ? "var(--navy-900)" : "var(--ink-700)",
                fontWeight: meta.idioma === i.v ? 600 : 500,
                borderRadius: 5, fontFamily: "'JetBrains Mono', monospace", cursor: "pointer",
              }}>{i.l}</button>
            ))}
          </div>
        </MetaField>

        {/* Payload preview */}
        <div style={{ marginTop: 6, padding: "10px 12px", background: "#0F1733", color: "#E8EAF2", borderRadius: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 9.5, color: "#7B82A0", letterSpacing: 1.4, textTransform: "uppercase" as const }}>
            previsualización · ingest payload
          </div>
          <div>
            corpus: <span style={{ color: "var(--gold-500)" }}>{slug}</span>{"  ·  "}
            doc: <span style={{ color: "var(--gold-500)" }}>{docPreview}</span>{"  ·  "}
            lang: <span style={{ color: "var(--gold-500)" }}>{meta.idioma || "—"}</span>
          </div>
          <div>
            empresa=<span style={{ color: "#A7ACBE" }}>{meta.empresa || "—"}</span>{"  "}
            proyecto_id=<span style={{ color: "#A7ACBE" }}>{meta.proyecto_id || "∅"}</span>{"  "}
            tipo_doc=<span style={{ color: "#A7ACBE" }}>{meta.tipo_doc || "—"}</span>
          </div>
        </div>
      </div>

      <div style={{ borderTop: "1px solid var(--ink-100)", padding: "12px 16px", display: "flex", alignItems: "center", gap: 10, background: "#FAFBFD" }}>
        <div style={{ fontSize: 11.5, color: "var(--ink-500)", flex: 1 }}>
          {hasPending ? <><span style={{ fontWeight: 600, color: "var(--ink-700)" }}>Pendientes</span> · se indexarán con estos metadatos</> : "Sin ficheros pendientes"}
        </div>
        <button onClick={onSubmit} disabled={!canSubmit} style={{
          height: 34, padding: "0 16px", display: "inline-flex", alignItems: "center", gap: 8,
          background: !canSubmit ? "#FBE5AB" : "var(--gold-500)",
          color: "var(--navy-900)", borderRadius: 5, fontWeight: 700, fontSize: 12,
          cursor: !canSubmit ? "not-allowed" : "pointer", fontFamily: "inherit", border: "none",
        }}>
          {submitting ? <><ISpin /> Procesando…</> : <><IUpload /> Indexar lote</>}
        </button>
      </div>
    </section>
  );
}

/* ── StatsPanel ─────────────────────────────────────────────── */
function StatsPanel({ stats }: { stats: IndexStats | null }) {
  const Stat = ({ n, l, sub }: { n: string; l: string; sub: string }) => (
    <div style={{ padding: "14px 14px 12px" }}>
      <div style={{ fontSize: 11, color: "var(--ink-500)", letterSpacing: 0.3 }}>{l}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: "var(--navy-900)", lineHeight: 1.1, margin: "4px 0 2px" }}>{n}</div>
      <div style={{ fontSize: 10, color: "var(--ink-400)", fontFamily: "'JetBrains Mono', monospace" }}>{sub}</div>
    </div>
  );

  const totalChunks = stats ? stats.total_chunks.toLocaleString("es") : "…";
  const totalCorpus = stats ? String(stats.total_corpus) : "…";
  const globalChunks = stats ? (stats.corpus.find(c => c.es_global)?.chunks ?? 0).toLocaleString("es") : "…";

  return (
    <aside style={{ width: 260, flexShrink: 0, display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Index stats */}
      <section style={{ background: "#fff", border: "1px solid var(--ink-100)", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--ink-100)", fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase" as const, color: "var(--ink-500)", fontWeight: 600 }}>
          Estado del índice
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", borderTop: "1px solid var(--ink-100)" }}>
          <div style={{ borderRight: "1px solid var(--ink-100)", borderBottom: "1px solid var(--ink-100)" }}>
            <Stat n={totalChunks} l="Chunks totales" sub="children vectorizados" />
          </div>
          <div style={{ borderBottom: "1px solid var(--ink-100)" }}>
            <Stat n={totalCorpus} l="Corpus" sub="colecciones activas" />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <Stat n={globalChunks} l="Corpus global Intecsa" sub="chunks indexados" />
          </div>
        </div>

        {/* Per-corpus breakdown */}
        {stats && stats.corpus.length > 0 && (
          <div style={{ borderTop: "1px solid var(--ink-100)", padding: "10px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
            {stats.corpus.map(c => (
              <div key={c.nombre} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11.5 }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: c.es_global ? "var(--navy-700)" : "var(--ink-700)", fontWeight: c.es_global ? 700 : 500, fontSize: 11 }}>
                  {c.nombre}
                </span>
                <span style={{ color: "var(--ink-500)", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
                  {c.chunks.toLocaleString("es")} chunks
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

    </aside>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [files, setFiles] = useState<QueueFile[]>([]);
  const [meta, setMeta] = useState<Meta>({ empresa: "", proyecto_id: "", tipo_doc: "", idioma: "es" });
  const [submitting, setSubmitting] = useState(false);
  const filesRef = useRef<QueueFile[]>([]);
  filesRef.current = files;
  const metaRef = useRef(meta);
  metaRef.current = meta;
  const isProcessingRef = useRef(false);
  const [toast, setToast] = useState<string | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [scopes, setScopes] = useState<Scope[]>([]);

  const empresas = useMemo<EmpresaOption[]>(() => {
    const seen = new Set<string>();
    const result: EmpresaOption[] = [];
    for (const s of scopes) {
      if (!seen.has(s.empresa)) {
        seen.add(s.empresa);
        result.push({
          v: s.empresa,
          l: s.empresa === "intecsa" ? "Intecsa (global)" : s.empresa.charAt(0).toUpperCase() + s.empresa.slice(1),
        });
      }
    }
    return result;
  }, [scopes]);

  const proyectosByEmpresa = useMemo<Record<string, ProyectoOption[]>>(() => {
    const map: Record<string, ProyectoOption[]> = {};
    for (const s of scopes) {
      if (!s.proyecto_id) continue;
      if (!map[s.empresa]) map[s.empresa] = [];
      map[s.empresa].push({ v: s.proyecto_id, l: s.label });
    }
    return map;
  }, [scopes]);

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(r => r.ok ? r.json() : null)
      .then((data: UserInfo | null) => {
        if (!data || data.role !== "admin") {
          router.replace("/");
        } else {
          setUser(data);
          setAuthChecked(true);
        }
      })
      .catch(() => router.replace("/"));
  }, [router]);

  useEffect(() => {
    if (!authChecked) return;
    fetchScopes().then(setScopes).catch(() => {});
    fetch("/api/admin/stats", { credentials: "same-origin" })
      .then(r => r.ok ? r.json() : null)
      .then((data: IndexStats | null) => { if (data) setStats(data); })
      .catch(() => {});
  }, [authChecked]);

  const onSubmit = useCallback(async () => {
    if (isProcessingRef.current) return;
    isProcessingRef.current = true;
    setSubmitting(true);

    let errores = 0;
    let total = 0;

    while (true) {
      const idx = filesRef.current.findIndex(f => !f.status || f.status === "pendiente");
      if (idx === -1) break;

      const f = filesRef.current[idx];
      const fileId = f.id;
      const currentMeta = metaRef.current;

      setFiles(prev => prev.map(p => p.id === fileId ? { ...p, status: "procesando" as const } : p));

      const form = new FormData();
      form.append("files", f.file, f.name);
      form.append("empresa", currentMeta.empresa);
      form.append("proyecto_id", currentMeta.proyecto_id);
      form.append("tipo_doc", currentMeta.tipo_doc);
      form.append("idioma", currentMeta.idioma);

      try {
        const res = await fetch("/api/admin/ingest", { method: "POST", body: form, credentials: "same-origin" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const fileResult = data.results?.[0];
        const ok = !fileResult?.error;
        setFiles(prev => prev.map(p => p.id === fileId ? { ...p, status: ok ? "listo" as const : "error" as const } : p));
        if (!ok) errores++;
      } catch {
        setFiles(prev => prev.map(p => p.id === fileId ? { ...p, status: "error" as const } : p));
        errores++;
      }
      total++;
    }

    isProcessingRef.current = false;
    setSubmitting(false);
    setToast(errores === 0
      ? `Indexación completada · ${total} fichero${total !== 1 ? "s" : ""}`
      : `Completado con ${errores} error${errores !== 1 ? "es" : ""}`);
    setTimeout(() => setToast(null), 4000);
    fetch("/api/admin/stats", { credentials: "same-origin" })
      .then(r => r.ok ? r.json() : null)
      .then((d: IndexStats | null) => { if (d) setStats(d); })
      .catch(() => {});
  }, []);

  if (!authChecked) return null;

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--canvas)", fontFamily: "'Inter', system-ui, sans-serif", fontSize: 12.5, color: "var(--ink-900)" }}>
      <AdminHeader user={user} />

      <main style={{ flex: 1, padding: "18px 20px 28px", display: "flex", flexDirection: "column", gap: 18 }}>
        {/* Intro */}
        <div>
          <div style={{ fontSize: 10, letterSpacing: 1.4, textTransform: "uppercase" as const, color: "var(--ink-500)", fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>
            Ingesta de documentos
          </div>
          <h1 style={{ margin: "4px 0", fontSize: 22, fontWeight: 800, letterSpacing: -0.4, color: "var(--navy-900)" }}>
            Subir y catalogar documentación técnica
          </h1>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-500)", maxWidth: 760 }}>
            Carga uno o varios ficheros, asigna sus metadatos y dispara la indexación en el corpus correspondiente.
            Los campos marcados como <span style={{ fontFamily: "'JetBrains Mono', monospace", color: "var(--gold-600)", fontWeight: 600 }}>administrador</span> solo se pueden editar desde este panel.
          </p>
        </div>

        {/* Three-column area */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 260px", gap: 14, alignItems: "start" }}>
          <FileQueue files={files} setFiles={setFiles} />
          <MetadataForm meta={meta} setMeta={setMeta} onSubmit={onSubmit} hasPending={files.some(f => !f.status || f.status === "pendiente")} submitting={submitting} empresas={empresas} proyectosByEmpresa={proyectosByEmpresa} />
          <StatsPanel stats={stats} />
        </div>
      </main>

      {toast && (
        <div style={{
          position: "fixed", right: 20, bottom: 20, zIndex: 80,
          padding: "10px 14px", background: "var(--navy-900)", color: "#fff",
          borderRadius: 6, fontSize: 12.5, border: "1px solid #2A2F40",
          boxShadow: "0 12px 32px rgba(11,16,38,.3)",
          display: "flex", alignItems: "center", gap: 10, maxWidth: 380,
        }}>
          <span style={{ color: "var(--ok)", display: "flex" }}><ICheck /></span>
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
}

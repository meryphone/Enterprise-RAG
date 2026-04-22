"use client";

const SUGGESTIONS_BY_SCOPE: Record<string, string[]> = {
  intecsa: [
    "¿Cuál es el procedimiento de aprobación de documentos según PR-02?",
    "¿Qué datos debe incluir el plan de calidad y medio ambiente del proyecto?",
    "¿Cuáles son las funciones principales de un Jefe de proyecto?",
    "Procedimiento para la evaluación de oportunidades y preparación de ofertas",
  ],
  repsol: [
    "¿Cómo acceder y aportar documentos al portal IUI en La Pampilla?",
    "Requisitos para la distribución de documentación en Repsol YPF",
    "Proceso de revisión de documentos",
  ],
  dow: [
    "¿Cuáles son los permisos disponibles para el proyecto?",
    "¿Cómo se gestiona el control de documentos en el portal?",
    "Procedimiento para la distribución de documentación",
  ],
  interquisa: [
    "¿Cómo se gestionan los documentos de fabricantes en el portal Interquisa?",
    "Procedimiento de uso del portal de IUI en el proyecto",
    "¿Cuál es el flujo para el control de documentos?",
  ],
  petresa: [
    "¿Cómo enviar documentos de fabricantes en el portal Petresa?",
    "Instrucciones de uso del portal de IUI en el proyecto",
    "Flujo de aprobación y control de documentos en el portal",
  ],
  cepsa_fcc: [
    "¿Cuál es el procedimiento de aprobación de documentos en CEPSA FCC?",
    "Instrucciones para la distribución de documentos del proyecto",
    "Reglas de uso del portal en el proyecto ",
    "¿Cómo se controla y revisa la documentación en el proyecto FCC?",
  ],
  cepsa_hds_v: [
    "Procedimiento de aprobación y distribución de documentos en CEPSA HDS V",
    "¿Cómo usar el portal en el proyecto?",
    "Requisitos para el control de la información del proyecto HDS V",
    "Flujo de revisión y comentarios de la documentación",
  ],
  servicios_rnl: [
    "¿Cómo accede el cliente al portal?",
    "Procedimiento para subir documentos al portal",
    "Reglas para el acceso y uso del portal IUI",
  ],
  enip: [
    "¿Cuál es el procedimiento para peticiones de oferta?",
    "Reglas para el uso del portal en el proyecto de Argelia",
    "¿Cómo funciona el control de documentos en el proyecto?",
  ],
  pars: [
    "Procedimiento de control de documentos en el portal",
    "¿Qué documentos deben ser incluidos en el portal?",
    "¿Qué funciones tiene el administardor del proyecto?",
  ],
  indorama: [
    "Uso del portal de gestión documental del proyecto",
    "Instrucciones de control de documentos para Indorama",
    "¿Qué estructura debe tener la documentación del portal?",
  ]
};

interface Props {
  label: string;
  scopeId: string;
  empresa: string;
  onSuggest: (q: string) => void;
}

export function EmptyState({ label, scopeId, empresa, onSuggest }: Props) {
  const suggestions = SUGGESTIONS_BY_SCOPE[empresa] || SUGGESTIONS_BY_SCOPE.intecsa;

  return (
    <div style={{
      height: "100%",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 24,
    }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
        {/* Monogram mark */}
        <div style={{
          width: 96, height: 96, borderRadius: 14,
          background: "var(--navy-700)", position: "relative",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 12px 32px rgba(27,42,107,0.22), inset 0 -3px 0 rgba(0,0,0,.18)",
        }}>
          <span style={{
            fontFamily: "'Inter', sans-serif", fontWeight: 900,
            fontSize: 68, color: "#fff", letterSpacing: -2,
            position: "relative", zIndex: 2,
          }}>
            i
          </span>
          <span style={{
            position: "absolute", right: 14, bottom: 12,
            width: 36, height: 4, background: "var(--gold-500)",
            transform: "rotate(-55deg)", transformOrigin: "right bottom",
          }} />
        </div>

        {/* Heading + subtext */}
        <div style={{ textAlign: "center" }}>
          <div style={{
            fontFamily: "'Inter', sans-serif", fontWeight: 800, fontSize: 22,
            color: "var(--navy-900)", letterSpacing: -0.3,
          }}>
            Consulta la documentación técnica de Intecsa
          </div>
          <div style={{
            marginTop: 8, color: "var(--ink-500)", fontSize: 13,
            maxWidth: 480, textAlign: "center",
          }}>
            Busca en especificaciones, procedimientos, datasheets y anexos de{" "}
            <strong style={{ color: "var(--ink-700)" }}>{label}</strong>.
            Las respuestas citan la fuente exacta — sección y páginas.
          </div>
        </div>

        {/* Suggested queries */}
        <div style={{
          display: "flex", gap: 8, flexWrap: "wrap",
          justifyContent: "center", maxWidth: 640,
        }}>
          {suggestions.map((q) => (
            <button
              key={q}
              onClick={() => onSuggest(q)}
              style={{
                fontSize: 12, padding: "7px 10px",
                border: "1px solid var(--ink-200)",
                background: "#fff",
                borderRadius: 6, color: "var(--ink-700)",
                cursor: "pointer", fontFamily: "inherit",
                transition: "border-color .1s, background .1s",
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--navy-500)";
                e.currentTarget.style.background = "var(--ink-050)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--ink-200)";
                e.currentTarget.style.background = "#fff";
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

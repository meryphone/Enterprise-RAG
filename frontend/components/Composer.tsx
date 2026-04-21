"use client";

import { useRef, useLayoutEffect } from "react";

const ISend = () => (
  <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 10l14-6-5 14-3-6-6-2z"/>
  </svg>
);

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: (text: string) => void;
  disabled: boolean;
  scopeLabel: string;
}

export function Composer({ value, onChange, onSend, disabled, scopeLabel }: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    if (!taRef.current) return;
    taRef.current.style.height = "auto";
    taRef.current.style.height = Math.min(160, taRef.current.scrollHeight) + "px";
  }, [value]);

  const submit = () => {
    if (!value.trim() || disabled) return;
    onSend(value.trim());
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div style={{
      borderTop: "1px solid var(--ink-100)",
      background: "#FFFFFF",
      padding: "10px 22px 14px",
      flexShrink: 0,
    }}>
      <div style={{
        maxWidth: 960, margin: "0 auto",
        border: "1px solid var(--ink-200)",
        borderRadius: 8,
        background: "#FFFFFF",
        boxShadow: "0 1px 2px rgba(14,18,32,.03)",
      }}>
        {/* Textarea + send */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 10, padding: "10px 12px" }}>
          <textarea
            ref={taRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            placeholder="Pregunta a la documentación técnica de Intecsa…   (Enter para enviar, Shift+Enter nueva línea)"
            disabled={disabled}
            style={{
              flex: 1, resize: "none", outline: "none", border: "none",
              fontSize: 13.5, lineHeight: 1.55,
              minHeight: 28, maxHeight: 160,
              color: "var(--ink-900)", background: "transparent",
              fontFamily: "inherit",
              opacity: disabled ? 0.6 : 1,
            }}
          />
          <button
            onClick={submit}
            disabled={!canSend}
            style={{
              flexShrink: 0,
              height: 32, minWidth: 72,
              display: "inline-flex", alignItems: "center",
              justifyContent: "center", gap: 6,
              padding: "0 12px",
              background: canSend ? "var(--gold-500)" : "#FBE5AB",
              color: "var(--navy-900)",
              borderRadius: 6, fontWeight: 700, fontSize: 12,
              cursor: canSend ? "pointer" : "not-allowed",
              border: "none", fontFamily: "inherit",
              transition: "background .12s",
            }}
            onMouseEnter={(e) => { if (canSend) e.currentTarget.style.background = "var(--gold-600)"; }}
            onMouseLeave={(e) => { if (canSend) e.currentTarget.style.background = "var(--gold-500)"; }}
          >
            <ISend /> Enviar
          </button>
        </div>
      </div>

      {/* Disclaimer + corpus activo */}
      <div style={{
        maxWidth: 960, margin: "6px auto 0",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        fontSize: 10.5, color: "var(--ink-400)",
        fontFamily: "'JetBrains Mono', monospace",
      }}>
        <span>Las respuestas citan fuente exacta · verifique siempre antes de emitir documento oficial</span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "var(--ink-300)" }}>corpus:</span>
          <span style={{
            color: "var(--navy-700)", fontWeight: 600,
            background: "#EEF1FB",
            padding: "1px 6px", borderRadius: 3,
            border: "1px solid #C7D0EA",
          }}>
            {scopeLabel}
          </span>
        </span>
      </div>
    </div>
  );
}

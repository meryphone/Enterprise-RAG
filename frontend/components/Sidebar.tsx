"use client";

import { useEffect, useState } from "react";
import { fetchScopes } from "@/lib/api";
import type { Scope } from "@/lib/types";

/* ── Inline SVG icons ─────────────────────────────────────── */
const ISearch = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="7" cy="7" r="4.5"/><path d="M13.5 13.5 10.5 10.5"/>
  </svg>
);
const IPlus = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M8 3v10M3 8h10"/>
  </svg>
);
const IChevron = () => (
  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3 2l3 3-3 3"/>
  </svg>
);
const IFolder = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M2 4h4l1 1h7v7H2z"/>
  </svg>
);
const IBuilding = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="2" y="3" width="12" height="11" rx="1"/>
    <path d="M6 8h1M9 8h1M6 11h1M9 11h1M7 14v-3h2v3"/>
  </svg>
);
const ISettings = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="8" cy="8" r="2"/>
    <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5 13 13M13 3l-1.5 1.5M4.5 11.5 3 13"/>
  </svg>
);
const ILoader = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    style={{ animation: "spin 1s linear infinite" }}>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
  </svg>
);

/* ── Wordmark ─────────────────────────────────────────────── */
function Wordmark() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, lineHeight: 1 }}>
      <div style={{
        width: 34, height: 34,
        background: "#0B1026",
        border: "1px solid rgba(255,255,255,.14)",
        borderRadius: 6,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', sans-serif", fontWeight: 900,
        color: "#FFFFFF", fontSize: 22,
        letterSpacing: -0.5, position: "relative",
        flexShrink: 0,
      }}>
        <span style={{ position: "relative", zIndex: 2 }}>i</span>
        <span style={{
          position: "absolute", right: 3, bottom: 3,
          width: 10, height: 2, background: "var(--gold-500)",
          transform: "rotate(-55deg)", transformOrigin: "right bottom",
        }} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{
          fontFamily: "'Inter', sans-serif", fontWeight: 800,
          fontSize: 14.5, letterSpacing: -0.3,
          color: "#FFFFFF",
        }}>
          intecsa<span style={{ color: "var(--gold-500)" }}>/</span>rag
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9, letterSpacing: 1.2,
          color: "rgba(255,255,255,.45)", textTransform: "uppercase",
        }}>
          knowledge · v1.4
        </div>
      </div>
    </div>
  );
}

/* ── Props ────────────────────────────────────────────────── */
interface Props {
  activeScope: Scope;
  onScopeChange: (scope: Scope) => void;
  onNewChat: () => void;
}

interface UserInfo {
  full_name: string;
  email: string;
  role: string;
}

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}


export function Sidebar({ activeScope, onScopeChange, onNewChat }: Props) {
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [user, setUser] = useState<UserInfo | null>(null);

  useEffect(() => {
    fetchScopes()
      .then(setScopes)
      .catch(() => {
        setScopes([{ coleccion: "intecsa", proyecto_id: null, empresa: "intecsa", label: "Intecsa (Global)" }]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data) setUser(data); })
      .catch(() => {});
  }, []);

  /* Build groups */
  const globalScopes = scopes.filter((s) => s.proyecto_id === null);
  const projectScopes = scopes.filter((s) => s.proyecto_id !== null);
  const byEmpresa = projectScopes.reduce<Record<string, Scope[]>>((acc, s) => {
    if (!acc[s.empresa]) acc[s.empresa] = [];
    acc[s.empresa].push(s);
    return acc;
  }, {});

  const groups: { group: string; items: Scope[] }[] = [];
  if (globalScopes.length > 0) groups.push({ group: "General", items: globalScopes });
  Object.entries(byEmpresa).forEach(([empresa, items]) => {
    groups.push({
      group: `Proyectos · ${empresa.charAt(0).toUpperCase() + empresa.slice(1)}`,
      items,
    });
  });

  const ql = q.toLowerCase();
  const filtered = groups
    .map((g) => {
      const groupMatch = g.group.toLowerCase().includes(ql);
      return {
        ...g,
        items: groupMatch
          ? g.items
          : g.items.filter(
              (i) =>
                i.label.toLowerCase().includes(ql) ||
                i.empresa.toLowerCase().includes(ql),
            ),
      };
    })
    .filter((g) => g.items.length > 0);

  const toggleGroup = (group: string) =>
    setCollapsed((s) => ({ ...s, [group]: !s[group] }));

  return (
    <aside className="sidebar" style={{
      width: "var(--sidebar-w)",
      flex: "0 0 var(--sidebar-w)",
      background: "var(--navy-900)",
      borderRight: "1px solid #0A0F24",
      display: "flex", flexDirection: "column",
      color: "#D7DBEA", overflow: "hidden", minHeight: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 14px 12px",
        background: "#0B1026",
        borderBottom: "1px solid rgba(255,255,255,.06)",
        flexShrink: 0,
      }}>
        <Wordmark />
      </div>

      {/* Search + new chat */}
      <div style={{ padding: "10px 10px 8px", display: "flex", flexDirection: "column", gap: 8, flexShrink: 0 }}>
        <div style={{ position: "relative" }}>
          <span style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: "#8B92AE", display: "flex" }}>
            <ISearch />
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filtrar corpus…"
            style={{
              width: "100%", height: 28,
              background: "rgba(255,255,255,.04)",
              border: "1px solid rgba(255,255,255,.08)",
              borderRadius: 6, padding: "0 10px 0 26px",
              color: "#E8EAF2", fontSize: 12, outline: "none",
              fontFamily: "inherit",
            }}
          />
        </div>
        <button
          onClick={onNewChat}
          style={{
            display: "flex", alignItems: "center", gap: 7,
            height: 28, padding: "0 10px",
            background: "var(--gold-500)",
            color: "var(--navy-900)",
            borderRadius: 6, fontSize: 12, fontWeight: 700,
            letterSpacing: 0.1, justifyContent: "center",
            cursor: "pointer", border: "none", fontFamily: "inherit",
          }}
        >
          <IPlus /> Nueva consulta
        </button>
      </div>

      {/* Groups list */}
      <div style={{ flex: 1, overflow: "auto", padding: "4px 6px 10px" }}>
        {loading ? (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 8px", color: "#7B82A0", fontSize: 12,
          }}>
            <ILoader /> Cargando corpus...
          </div>
        ) : filtered.map((g) => {
          const open = !collapsed[g.group];
          return (
            <div key={g.group} style={{ marginTop: 10 }}>
              <button
                onClick={() => toggleGroup(g.group)}
                style={{
                  width: "100%", display: "flex", alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 8px", color: "#8B92AE",
                  fontSize: 10, letterSpacing: 1.2, textTransform: "uppercase",
                  fontWeight: 600, background: "none", border: "none",
                  cursor: "pointer", fontFamily: "inherit",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{
                    display: "inline-block",
                    transform: open ? "rotate(90deg)" : "rotate(0deg)",
                    transition: "transform .12s",
                  }}>
                    <IChevron />
                  </span>
                  {g.group}
                </span>
                <span style={{ color: "#5B6384", fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>
                  {g.items.length}
                </span>
              </button>

              {open && g.items.map((it) => {
                const isActive = it.coleccion === activeScope.coleccion;
                const isProject = it.proyecto_id !== null;
                return (
                  <button
                    key={it.coleccion}
                    onClick={() => onScopeChange(it)}
                    style={{
                      width: "100%", textAlign: "left", display: "block",
                      padding: "7px 10px", borderRadius: 4, marginBottom: 1,
                      position: "relative",
                      background: isActive ? "rgba(255,255,255,.05)" : "transparent",
                      color: isActive ? "#FFFFFF" : "#B8BED6",
                      border: "none", cursor: "pointer", fontFamily: "inherit",
                    }}
                    onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,.035)"; }}
                    onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                  >
                    {isActive && (
                      <span style={{
                        position: "absolute", left: 0, top: 4, bottom: 4, width: 3,
                        background: "var(--gold-500)", borderRadius: 2,
                      }} />
                    )}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, lineHeight: 1.2 }}>
                      <span style={{ color: isActive ? "var(--gold-500)" : "#5B6384", flexShrink: 0 }}>
                        {isProject ? <IFolder /> : <IBuilding />}
                      </span>
                      <span style={{
                        fontSize: 12.5, fontWeight: isActive ? 600 : 500,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      }}>
                        {it.label}
                      </span>
                    </div>
                    {it.docs !== undefined && (
                      <div style={{
                        marginTop: 3, paddingLeft: 20,
                        fontSize: 10.5, color: "#7B82A0",
                        fontFamily: "'JetBrains Mono', monospace",
                        display: "flex", gap: 8,
                      }}>
                        <span>{it.docs.toLocaleString("es")} docs</span>
                        {it.updated && (
                          <>
                            <span style={{ color: "#3D4670" }}>·</span>
                            <span>{it.updated}</span>
                          </>
                        )}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {/* User footer */}
      <div style={{
        borderTop: "1px solid rgba(255,255,255,.06)",
        padding: "10px 12px",
        display: "flex", alignItems: "center", gap: 10,
        background: "#0B1026", flexShrink: 0,
      }}>
        <div style={{
          width: 26, height: 26, borderRadius: 4,
          background: "linear-gradient(180deg,#24358A,#1B2A6B)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontSize: 10, fontWeight: 700, flexShrink: 0,
        }}>
          {user ? initials(user.full_name) : "·"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12, color: "#EEF0F8", fontWeight: 600,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {user?.full_name ?? "—"}
          </div>
          <div style={{
            fontSize: 10.5, color: "#7B82A0",
            fontFamily: "'JetBrains Mono', monospace",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {user?.role ?? ""}
          </div>
        </div>
        <button
          style={{ color: "#7B82A0", background: "none", border: "none", cursor: "pointer", display: "flex" }}
          title="Ajustes"
        >
          <ISettings />
        </button>
      </div>
    </aside>
  );
}

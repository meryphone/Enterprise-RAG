"use client";

import { useEffect, useState } from "react";
import { fetchScopes } from "@/lib/api";
import type { Scope } from "@/lib/types";
import { cn } from "@/lib/utils";
import { MessageSquare, Loader2, Building2, FolderOpen } from "lucide-react";

interface Props {
  activeScope: Scope;
  onScopeChange: (scope: Scope) => void;
}

function ScopeButton({ scope, active, onClick }: { scope: Scope; active: boolean; onClick: () => void }) {
  const isProject = scope.proyecto_id !== null;
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-md px-2 py-2 text-sm transition-colors flex items-center gap-2",
        active
          ? "bg-primary/10 text-primary font-medium"
          : "text-foreground hover:bg-accent",
      )}
    >
      {isProject ? (
        <FolderOpen className="h-3.5 w-3.5 shrink-0 opacity-60" />
      ) : (
        <Building2 className="h-3.5 w-3.5 shrink-0 opacity-60" />
      )}
      <span className="truncate">{scope.label}</span>
    </button>
  );
}

export function Sidebar({ activeScope, onScopeChange }: Props) {
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchScopes()
      .then(setScopes)
      .catch(() => {
        setScopes([{ coleccion: "intecsa", proyecto_id: null, empresa: "intecsa", label: "Intecsa (Global)" }]);
      })
      .finally(() => setLoading(false));
  }, []);

  const globalScopes = scopes.filter((s) => s.proyecto_id === null);
  const projectScopes = scopes.filter((s) => s.proyecto_id !== null);

  // Agrupar proyectos por empresa
  const byEmpresa = projectScopes.reduce<Record<string, Scope[]>>((acc, s) => {
    const key = s.empresa;
    if (!acc[key]) acc[key] = [];
    acc[key].push(s);
    return acc;
  }, {});

  return (
    <aside className="flex flex-col w-56 border-r bg-muted/30 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-4 border-b">
        <MessageSquare className="h-5 w-5 text-primary" />
        <span className="font-semibold text-sm">IntecsaRAG</span>
      </div>

      <nav className="flex-1 overflow-y-auto p-2 space-y-3">
        {loading ? (
          <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Cargando corpus...
          </div>
        ) : (
          <>
            {/* Corpus global */}
            {globalScopes.length > 0 && (
              <div>
                <p className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  General
                </p>
                {globalScopes.map((scope) => (
                  <ScopeButton
                    key={scope.coleccion}
                    scope={scope}
                    active={activeScope.coleccion === scope.coleccion}
                    onClick={() => onScopeChange(scope)}
                  />
                ))}
              </div>
            )}

            {/* Proyectos agrupados por empresa */}
            {Object.entries(byEmpresa).map(([empresa, proyectos]) => (
              <div key={empresa}>
                <p className="px-2 py-1 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {empresa.charAt(0).toUpperCase() + empresa.slice(1)}
                </p>
                {proyectos.map((scope) => (
                  <ScopeButton
                    key={scope.coleccion}
                    scope={scope}
                    active={activeScope.coleccion === scope.coleccion}
                    onClick={() => onScopeChange(scope)}
                  />
                ))}
              </div>
            ))}
          </>
        )}
      </nav>
    </aside>
  );
}

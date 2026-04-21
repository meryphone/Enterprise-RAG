"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import type { SourceRef } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  source: SourceRef;
}

export function SourceChip({ source }: Props) {
  const label = source.doc.replace(/\.pdf$/i, "");
  const pages =
    source.pagina_inicio === -1
      ? null
      : source.pagina_inicio === source.pagina_fin || source.pagina_fin === -1
        ? `p. ${source.pagina_inicio}`
        : `pp. ${source.pagina_inicio}–${source.pagina_fin}`;

  const tooltipLines = [
    source.titulo || label,
    source.version ? `Ed. ${source.version}` : null,
    source.seccion || null,
    pages,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium cursor-default select-none",
              source.es_anexo
                ? "border-amber-300 bg-amber-50 text-amber-700"
                : "border-blue-200 bg-blue-50 text-blue-700",
            )}
          >
            <span className="opacity-50">[{source.ref}]</span>
            {label}
            {pages && <span className="opacity-60">{pages}</span>}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            className="z-50 max-w-xs rounded-md bg-gray-900 px-3 py-1.5 text-xs text-white shadow-md"
            sideOffset={4}
          >
            {tooltipLines}
            <Tooltip.Arrow className="fill-gray-900" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

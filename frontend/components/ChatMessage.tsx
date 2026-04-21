import type { Message, SourceRef } from "@/lib/types";
import { SourceChip } from "./SourceChip";
import { cn } from "@/lib/utils";

interface Props {
  message: Message;
}

function parsearRefsUsadas(texto: string): Set<number> {
  const refs = new Set<number>();
  for (const m of texto.matchAll(/\[(\d+)\]/g)) {
    refs.add(parseInt(m[1], 10));
  }
  return refs;
}

function limpiarMarcadores(texto: string): string {
  return texto.replace(/\[(\d+)\]/g, "").replace(/\s{2,}/g, " ").trim();
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";

  const refsUsadas = !message.streaming && message.sources
    ? parsearRefsUsadas(message.content)
    : null;

  const fuentesFiltradas: SourceRef[] = message.sources
    ? refsUsadas && refsUsadas.size > 0
      ? message.sources.filter((s) => refsUsadas.has(s.ref))
      : message.sources
    : [];

  const textoLimpio = !message.streaming && refsUsadas
    ? limpiarMarcadores(message.content)
    : message.content;

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm",
        )}
      >
        <p className={cn("whitespace-pre-wrap", message.streaming && "cursor-blink")}>
          {textoLimpio}
        </p>

        {!message.streaming && fuentesFiltradas.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5 pt-2 border-t border-black/10">
            {fuentesFiltradas.map((s) => (
              <SourceChip key={s.ref} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

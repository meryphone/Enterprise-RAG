"use client";

import { useEffect, useRef, useState } from "react";
import { streamQuery } from "@/lib/api";
import type { Message, Scope, SourceRef } from "@/lib/types";
import { ChatMessage } from "./ChatMessage";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  scope: Scope;
}

export function ChatArea({ scope }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll al último mensaje
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Al cambiar de scope, limpiar el chat
  useEffect(() => {
    setMessages([]);
  }, [scope.coleccion]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query || streaming) return;

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: query };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", streaming: true };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setStreaming(true);

    try {
      await streamQuery(
        query,
        scope,
        (token) => {
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, content: m.content + token } : m),
          );
        },
        (sources: SourceRef[]) => {
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, sources } : m),
          );
        },
        () => {
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, streaming: false } : m),
          );
          setStreaming(false);
          inputRef.current?.focus();
        },
        (error) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: `Error: ${error}`, streaming: false } : m,
            ),
          );
          setStreaming(false);
        },
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Error al conectar con el servidor.", streaming: false }
            : m,
        ),
      );
      setStreaming(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Topbar */}
      <div className="flex items-center gap-2 border-b px-4 py-3 text-sm text-muted-foreground bg-background">
        <span className="font-medium text-foreground">{scope.label}</span>
      </div>

      {/* Mensajes */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground gap-2">
            <p className="text-lg font-medium">IntecsaRAG</p>
            <p className="text-sm">Haz una pregunta sobre la documentación técnica de {scope.label}.</p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t px-4 py-3 bg-background">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe tu pregunta..."
            disabled={streaming}
            className={cn(
              "flex-1 rounded-lg border px-3 py-2 text-sm outline-none transition-colors",
              "placeholder:text-muted-foreground bg-background",
              "focus:ring-2 focus:ring-primary/30 focus:border-primary",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          />
          <button
            type="submit"
            disabled={!input.trim() || streaming}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              "bg-primary text-primary-foreground hover:bg-primary/90",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </div>
    </div>
  );
}

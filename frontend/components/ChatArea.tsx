"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { streamQuery } from "@/lib/api";
import type { Message, Scope, SourceRef } from "@/lib/types";
import { ChatMessage } from "./ChatMessage";
import { Topbar, type SystemStatus } from "./Topbar";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";

interface Props {
  scope: Scope;
}

function nowStr(): string {
  return new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

export function ChatArea({ scope }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<SystemStatus>("connected");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    setMessages([]);
  }, [scope.coleccion]);

  const runQuery = useCallback(async (query: string) => {
    const effectiveScope: Scope = scope;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: nowStr(),
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
      timestamp: nowStr(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);
    setStatus("processing");

    try {
      await streamQuery(
        query,
        effectiveScope,
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
          setStatus("connected");
        },
        (error) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: `Error: ${error}`, streaming: false }
                : m,
            ),
          );
          setStreaming(false);
          setStatus("connected");
        },
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Error al conectar con el servidor.", streaming: false }
            : m,
        ),
      );
      setStreaming(false);
      setStatus("offline");
      setTimeout(() => setStatus("connected"), 3000);
    }
  }, [scope]);

  const handleSend = useCallback((text: string) => {
    if (!text.trim() || streaming) return;
    setInput("");
    runQuery(text, false);
  }, [streaming, runQuery]);

  const handleSuggest = useCallback((q: string) => {
    setInput(q);
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0, overflow: "hidden" }}>
      <Topbar scope={scope} status={status} />

      {/* Messages scroll area */}
      <div style={{
        flex: 1, overflow: "auto", minHeight: 0,
        background: "var(--canvas)",
        paddingTop: 8, paddingBottom: 4,
      }}>
        {messages.length === 0 ? (
          <EmptyState 
            label={scope.label} 
            scopeId={scope.coleccion} 
            empresa={scope.empresa} 
            onSuggest={handleSuggest} 
          />
        ) : (
          <>
            {/* Thread date separator */}
            <div style={{
              padding: "8px 22px 4px",
              display: "flex", alignItems: "center", gap: 10,
              fontSize: 11, color: "var(--ink-400)",
            }}>
              <div style={{ flex: 1, height: 1, background: "var(--ink-100)" }} />
              <span style={{
                fontFamily: "'JetBrains Mono', monospace",
                textTransform: "uppercase", letterSpacing: 1.2,
              }}>
                {new Date().toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" })}
              </span>
              <div style={{ flex: 1, height: 1, background: "var(--ink-100)" }} />
            </div>

            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
              />
            ))}
            <div ref={bottomRef} style={{ height: 4 }} />
          </>
        )}
      </div>

      <Composer
        value={input}
        onChange={setInput}
        onSend={handleSend}
        disabled={streaming}
        scopeLabel={
          scope.proyecto_id !== null && scope.empresa
            ? `${scope.label} · ${scope.empresa.charAt(0).toUpperCase() + scope.empresa.slice(1)}`
            : scope.label
        }
      />
    </div>
  );
}

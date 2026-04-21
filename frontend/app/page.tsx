"use client";

import { Sidebar } from "@/components/Sidebar";
import { ChatArea } from "@/components/ChatArea";
import { useState, useCallback } from "react";
import type { Scope } from "@/lib/types";

export default function Home() {
  const [scope, setScope] = useState<Scope>({
    coleccion: "intecsa",
    proyecto_id: null,
    empresa: "intecsa",
    label: "Intecsa (Global)",
  });
  const [chatKey, setChatKey] = useState(0);

  const handleNewChat = useCallback(() => {
    setChatKey((k) => k + 1);
  }, []);

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--canvas)" }}>
      <Sidebar activeScope={scope} onScopeChange={setScope} onNewChat={handleNewChat} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, overflow: "hidden" }}>
        <ChatArea key={chatKey} scope={scope} />
      </main>
    </div>
  );
}

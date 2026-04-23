"use client";

import { Sidebar } from "@/components/Sidebar";
import { ChatArea } from "@/components/ChatArea";
import { useState, useCallback, useEffect } from "react";
import type { Scope, UserInfo } from "@/lib/types";

export default function Home() {
  const [scope, setScope] = useState<Scope>({
    coleccion: "intecsa",
    proyecto_id: null,
    empresa: "intecsa",
    label: "Intecsa (Global)",
  });
  const [chatKey, setChatKey] = useState(0);
  const [user, setUser] = useState<UserInfo | null>(null);

  useEffect(() => {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => { if (data) setUser(data); })
      .catch(() => {});
  }, []);

  const handleNewChat = useCallback(() => {
    setChatKey((k) => k + 1);
  }, []);

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--canvas)" }}>
      <Sidebar activeScope={scope} onScopeChange={setScope} onNewChat={handleNewChat} user={user} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, overflow: "hidden" }}>
        <ChatArea key={chatKey} scope={scope} user={user} />
      </main>
    </div>
  );
}

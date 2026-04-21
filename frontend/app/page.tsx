"use client";

import { Sidebar } from "@/components/Sidebar";
import { ChatArea } from "@/components/ChatArea";
import { useState } from "react";
import type { Scope } from "@/lib/types";

export default function Home() {
  const [scope, setScope] = useState<Scope>({
    coleccion: "intecsa",
    proyecto_id: null,
    empresa: "intecsa",
    label: "Intecsa (Global)",
  });

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeScope={scope} onScopeChange={setScope} />
      <main className="flex-1 overflow-hidden">
        <ChatArea scope={scope} />
      </main>
    </div>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IntecsaRAG",
  description: "Asistente de documentación técnica de Intecsa",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="antialiased">{children}</body>
    </html>
  );
}

export interface Scope {
  coleccion: string; // The backend collection name representing this scope.
  proyecto_id: string | null; // The ID of the client project, or null if this is the global corpus.
  empresa: string; // The company name associated with the corpus.
  label: string; // Human-readable label for the UI.
  docs?: number;
  updated?: string;
  scope_desc?: string;
}

export interface SourceRef {
  ref: number;
  doc: string;
  titulo: string;
  version: string;
  seccion: string;
  pagina_inicio: number;
  pagina_fin: number;
  score: number;
  es_anexo: boolean;
}

export interface UserInfo {
  full_name: string;
  email: string;
  role: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  streaming?: boolean;
  timestamp?: string;
}

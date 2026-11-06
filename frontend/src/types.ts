/** A knowledge base is a private collection of the user's documents. */
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
}

/** Metadata returned by the document upload and listing endpoints. */
export interface DocumentRecord {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  created_at: string;
  page_count: number | null;
  status: string;
  chunk_count: number;
  processing_error: string | null;
}

/** One source passage supporting an AI answer. */
export interface AnswerSource {
  document_id: string;
  filename: string;
  page_number: number | null;
  excerpt: string;
}

/** One message displayed in the chat panel. */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: AnswerSource[];
}

export interface AuthenticationResponse {
  access_token: string;
}

export interface KnowledgeBaseListResponse {
  items: KnowledgeBase[];
  total: number;
}

export interface DocumentListResponse {
  items: DocumentRecord[];
  total: number;
}

export interface DocumentUploadResponse {
  document: DocumentRecord;
  message: string;
}

export interface ChatResponse {
  answer: string;
  conversation_id: string;
  sources: AnswerSource[];
}

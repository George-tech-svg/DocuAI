/** A knowledge base is a private collection of the user's documents. */
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  is_archived: boolean;
  is_pinned: boolean;
  is_sensitive?: boolean;
  organization_id?: string | null;
  user_id?: string;
}

/** Metadata returned by the document upload and listing endpoints. */
export interface DocumentRecord {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  created_at: string;
  page_count: number | null;
  status: string;
  progress_stage: string;
  ocr_used: boolean;
  ocr_confidence: number | null;
  low_ocr_confidence: boolean;
  chunk_count: number;
  processing_error: string | null;
  is_archived: boolean;
  is_pinned: boolean;
  uploaded_by_user_id?: string | null;
  uploaded_by_name?: string | null;
  uploaded_by_email?: string | null;
}

/** One source passage supporting an AI answer. */
export interface AnswerSource {
  document_id: string | null;
  filename: string;
  page_number: number | null;
  excerpt: string;
  source_type?: "document" | "library";
  version_label?: string | null;
  section_title?: string | null;
  source_url?: string | null;
}

/** One message displayed in the chat panel. */
export interface ChatMessage {
  message_id?: string;
  role: "user" | "assistant";
  content: string;
  sources?: AnswerSource[];
  actor_name?: string | null;
  confidence_label?: "Strong match" | "Partial match" | "Weak match";
  confidence_score?: number;
  answer_language?: "en" | "sw" | "mixed";
  feedback_status?: "up" | "down" | "report";
}

export interface ConversationRecord {
  id: string;
  user_id?: string;
  title: string;
  knowledge_base_id: string | null;
  document_id: string | null;
  scope_type: "document" | "folder" | "library" | "folder_library";
  library_collection_id?: string | null;
  visibility?: "private" | "shared";
  created_at: string;
  is_archived: boolean;
  is_pinned: boolean;
}

export interface SavedChatMessage extends ChatMessage {
  id: string;
  created_at: string;
  metadata?: { search_query?: string; answer_language?: "en" | "sw" | "mixed"; confidence_score?: number; confidence_label?: "Strong match" | "Partial match" | "Weak match" };
  actor_user_id?: string | null;
  actor_email?: string | null;
  feedback_status?: "up" | "down" | "report";
}

export interface AuthenticationResponse {
  access_token?: string;
  user: UserProfile;
}

export interface UserProfile {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  answer_language?: "auto" | "en" | "sw";
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
  assistant_message_id: string;
  sources: AnswerSource[];
  answer_language: "en" | "sw" | "mixed";
  confidence_score: number;
  confidence_label: "Strong match" | "Partial match" | "Weak match";
  search_query: string;
}

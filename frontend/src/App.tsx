import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  LogOut,
  Menu,
  MessageCircle,
  Plus,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { getErrorMessage, request } from "./api";
import type {
  AuthenticationResponse,
  ChatMessage,
  ChatResponse,
  DocumentListResponse,
  DocumentRecord,
  DocumentUploadResponse,
  KnowledgeBase,
  KnowledgeBaseListResponse,
} from "./types";

/** The main application: sign in, manage documents, and chat with them. */
export default function App() {
  // Authentication form and saved session.
  const [token, setToken] = useState(
    localStorage.getItem("documind_token") ?? ""
  );
  const [isRegistering, setIsRegistering] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Knowledge bases and documents in the selected workspace.
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [expandedKnowledgeBaseIds, setExpandedKnowledgeBaseIds] = useState<Set<string>>(() => new Set());
  const [folderDocuments, setFolderDocuments] = useState<Record<string, { items: DocumentRecord[]; loading: boolean; error: string }>>({});
  const [isUploadPanelOpen, setIsUploadPanelOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");

  // Chat messages and current conversation.
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Shared feedback for network operations.
  const [isBusy, setIsBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("Processing...");
  const [errorMessage, setErrorMessage] = useState("");

  /** Load the current user's knowledge bases from the API. */
  async function refreshKnowledgeBases() {
    if (!token) return;

    try {
      const response = await request<KnowledgeBaseListResponse>(
        "/knowledge-bases",
        token
      );

      setKnowledgeBases(response.items);
      setSelectedKnowledgeBaseId((previousId) => {
        const previousStillExists = response.items.some(
          (knowledgeBase) => knowledgeBase.id === previousId
        );

        return previousStillExists ? previousId : response.items[0]?.id ?? "";
      });
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  /** Load documents belonging to the currently selected knowledge base. */
  async function refreshDocuments() {
    if (!token || !selectedKnowledgeBaseId) {
      setDocuments([]);
      return;
    }

    try {
      const response = await request<DocumentListResponse>(
        `/knowledge-bases/${selectedKnowledgeBaseId}/documents`,
        token
      );
      setDocuments(response.items);
      setFolderDocuments((previous) => ({
        ...previous,
        [selectedKnowledgeBaseId]: { items: response.items, loading: false, error: "" },
      }));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  /** Expand a folder and load its document names for the sidebar tree. */
  async function toggleKnowledgeBase(knowledgeBaseId: string) {
    const isExpanded = expandedKnowledgeBaseIds.has(knowledgeBaseId);
    setExpandedKnowledgeBaseIds((previous) => {
      const next = new Set(previous);
      if (next.has(knowledgeBaseId)) next.delete(knowledgeBaseId);
      else next.add(knowledgeBaseId);
      return next;
    });
    if (isExpanded) return;

    setFolderDocuments((previous) => ({
      ...previous,
      [knowledgeBaseId]: { items: previous[knowledgeBaseId]?.items ?? [], loading: true, error: "" },
    }));
    try {
      const response = await request<DocumentListResponse>(
        `/knowledge-bases/${knowledgeBaseId}/documents`,
        token
      );
      setFolderDocuments((previous) => ({
        ...previous,
        [knowledgeBaseId]: { items: response.items, loading: false, error: "" },
      }));
      if (knowledgeBaseId === selectedKnowledgeBaseId) setDocuments(response.items);
    } catch (error) {
      setFolderDocuments((previous) => ({
        ...previous,
        [knowledgeBaseId]: {
          items: previous[knowledgeBaseId]?.items ?? [],
          loading: false,
          error: getErrorMessage(error),
        },
      }));
    }
  }

  // Refresh data after login or when the selected knowledge base changes.
  useEffect(() => {
    void refreshKnowledgeBases();
  }, [token]);

  useEffect(() => {
    void refreshDocuments();
    setMessages([]);
    setConversationId(null);
  }, [token, selectedKnowledgeBaseId]);

  // Uploads are processed synchronously by the API, so poll the document list
  // after an upload response or a page reload until the saved status changes.
  const hasProcessingDocuments = documents.some(
    (document) => document.status === "pending" || document.status === "processing"
  );
  useEffect(() => {
    if (!token || !selectedKnowledgeBaseId || !hasProcessingDocuments) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await request<DocumentListResponse>(
          `/knowledge-bases/${selectedKnowledgeBaseId}/documents`,
          token
        );
        setDocuments(response.items);
        setFolderDocuments((previous) => ({
          ...previous,
          [selectedKnowledgeBaseId]: { items: response.items, loading: false, error: "" },
        }));
      } catch {
        // Keep the last known document statuses; the next poll can recover.
      }
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [token, selectedKnowledgeBaseId, hasProcessingDocuments]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isBusy]);

  useEffect(() => {
    if (!isMobileSidebarOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setIsMobileSidebarOpen(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isMobileSidebarOpen]);

  /** Register a new user or sign in an existing user. */
  async function handleAuthentication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setBusyMessage(isRegistering ? "Creating your account..." : "Signing you in...");
    setErrorMessage("");

    try {
      const endpoint = isRegistering ? "/auth/register" : "/auth/login";
      const credentials = isRegistering
        ? { full_name: fullName, email, password }
        : { email, password };

      const response = await request<AuthenticationResponse>(endpoint, "", {
        method: "POST",
        body: JSON.stringify(credentials),
      });

      localStorage.setItem("documind_token", response.access_token);
      setToken(response.access_token);
      setPassword("");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  /** Clear all user-specific data when signing out. */
  function handleLogout() {
    localStorage.removeItem("documind_token");
    setToken("");
    setKnowledgeBases([]);
    setSelectedKnowledgeBaseId("");
    setSelectedDocumentId("");
    setDocuments([]);
    setExpandedKnowledgeBaseIds(new Set());
    setFolderDocuments({});
    setMessages([]);
    setConversationId(null);
    setIsMobileSidebarOpen(false);
  }

  /** Create a private knowledge base for the current user. */
  async function handleCreateKnowledgeBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newKnowledgeBaseName.trim()) return;

    setIsBusy(true);
    setBusyMessage("Preparing your knowledge base...");
    setErrorMessage("");

    try {
      const created = await request<KnowledgeBase>("/knowledge-bases", token, {
        method: "POST",
        body: JSON.stringify({ name: newKnowledgeBaseName.trim() }),
      });

      setNewKnowledgeBaseName("");
      await refreshKnowledgeBases();
      setSelectedKnowledgeBaseId(created.id);
      setSelectedDocumentId("");
      setExpandedKnowledgeBaseIds((previous) => new Set(previous).add(created.id));
      setFolderDocuments((previous) => ({
        ...previous,
        [created.id]: { items: [], loading: false, error: "" },
      }));
      setIsMobileSidebarOpen(false);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  /** Upload selected files one by one and report any that fail. */
  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length || !selectedKnowledgeBaseId) return;

    setIsBusy(true);
    setBusyMessage(`Preparing ${files.length} file${files.length === 1 ? "" : "s"}...`);
    setErrorMessage("");

    let uploaded = 0;
    const failures: string[] = [];
    try {
      for (const [index, file] of files.entries()) {
        setBusyMessage(`Uploading file ${index + 1} of ${files.length}: ${file.name}`);
        const formData = new FormData();
        formData.append("file", file);

        try {
          const response = await request<DocumentUploadResponse>(
            `/knowledge-bases/${selectedKnowledgeBaseId}/documents`,
            token,
            { method: "POST", body: formData }
          );
          if (response.document.status === "ready") {
            uploaded += 1;
          } else {
            failures.push(`${file.name}: ${response.document.processing_error ?? "Processing failed."}`);
          }
        } catch (error) {
          failures.push(`${file.name}: ${getErrorMessage(error)}`);
        }
      }
      await refreshDocuments();
      if (failures.length) {
        const shownFailures = failures.slice(0, 3).join("; ");
        const remaining = failures.length > 3 ? `; and ${failures.length - 3} more` : "";
        setErrorMessage(`${uploaded} of ${files.length} files uploaded. ${shownFailures}${remaining}`);
      }
    } finally {
      setIsBusy(false);
      event.target.value = "";
    }
  }

  /** Delete one document after the user confirms the action. */
  async function handleDeleteDocument(documentId: string) {
    if (!window.confirm("Delete this document?")) return;

    try {
      await request<void>(
        `/knowledge-bases/${selectedKnowledgeBaseId}/documents/${documentId}`,
        token,
        { method: "DELETE" }
      );
      if (selectedDocumentId === documentId) setSelectedDocumentId("");
      await refreshDocuments();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  /** Send a question and display the AI answer with its document sources. */
  async function handleSendQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim() || !selectedKnowledgeBaseId || isBusy) return;

    const submittedQuestion = question.trim();
    setQuestion("");
    setMessages((previous) => [
      ...previous,
      { role: "user", content: submittedQuestion },
    ]);
    setIsBusy(true);
    setBusyMessage("Searching your documents and preparing an answer...");
    setErrorMessage("");

    try {
      const response = await request<ChatResponse>("/chat", token, {
        method: "POST",
        body: JSON.stringify({
          knowledge_base_id: selectedKnowledgeBaseId,
          document_id: selectedDocumentId || null,
          question: submittedQuestion,
          conversation_id: conversationId,
        }),
      });

      setConversationId(response.conversation_id);
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: response.answer,
          sources: response.sources,
        },
      ]);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  // Before login, show only the authentication form.
  if (!token) {
    return (
      <div className="auth-wrap">
        <form className="auth-card" onSubmit={handleAuthentication}>
          <div className="brand">
            <BookOpen /> DocuMind <span>AI</span>
          </div>

          <h1>{isRegistering ? "Create your account" : "Welcome back"}</h1>
          <p>Turn your documents into trusted answers.</p>

          {isRegistering && (
            <input
              required
              minLength={2}
              maxLength={150}
              placeholder="Full name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          )}

          <input
            type="email"
            required
            placeholder="Email address"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <input
            type="password"
            required
            minLength={isRegistering ? 4 : undefined}
            maxLength={isRegistering ? 128 : undefined}
            autoComplete={isRegistering ? "new-password" : "current-password"}
            title={
              isRegistering
                ? "Use at least 4 characters. Numbers are allowed."
                : undefined
            }
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {isRegistering && (
            <p className="muted">
              Use at least 4 characters. Numbers are allowed.
            </p>
          )}

          {errorMessage && <p className="error">{errorMessage}</p>}

          <button disabled={isBusy}>
            {isBusy
              ? "Please wait..."
              : isRegistering
                ? "Create account"
                : "Sign in"}
          </button>

          <p>
            <button
              type="button"
              className="auth-toggle"
              onClick={() => {
                setIsRegistering(!isRegistering);
                setErrorMessage("");
              }}
            >
              {isRegistering
                ? "Already have an account? Sign in"
                : "New here? Create an account"}
            </button>
          </p>
        </form>
      </div>
    );
  }

  const selectedKnowledgeBase = knowledgeBases.find(
    (knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId
  );

  // After login, show the sidebar, document list, and chat panel.
  return (
    <div className="shell">
      <div className="mobile-topbar">
        <div className="brand">
          <BookOpen /> DocuMind <span>AI</span>
        </div>
        <button
          className="folder-menu-trigger"
          type="button"
          aria-label="Open folder sidebar"
          aria-expanded={isMobileSidebarOpen}
          onClick={() => setIsMobileSidebarOpen(true)}
        >
          <Menu size={19} />
          <span>{selectedKnowledgeBase?.name ?? "Folders"}</span>
        </button>
      </div>

      {isMobileSidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Close folder sidebar"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      <aside className={isMobileSidebarOpen ? "mobile-sidebar-open" : ""}>
        <div className="brand">
          <BookOpen /> DocuMind <span>AI</span>
        </div>
        <button
          className="sidebar-close"
          type="button"
          aria-label="Close folder sidebar"
          onClick={() => setIsMobileSidebarOpen(false)}
        ><X size={20} /></button>

        <div className="smalltitle">FOLDERS</div>

        <form className="newkb" onSubmit={handleCreateKnowledgeBase}>
          <input
            placeholder="New folder name"
            value={newKnowledgeBaseName}
            onChange={(event) => setNewKnowledgeBaseName(event.target.value)}
          />
          <button title="Create" disabled={isBusy}>
            <Plus size={18} />
          </button>
        </form>

        <nav className="folder-tree" aria-label="Folders and files">
          {knowledgeBases.map((knowledgeBase) => {
            const isExpanded = expandedKnowledgeBaseIds.has(knowledgeBase.id);
            const folder = folderDocuments[knowledgeBase.id];
            return (
              <div className="folder-tree-item" key={knowledgeBase.id}>
                <div className="folder-tree-row">
                  <button
                    className="folder-expand"
                    type="button"
                    aria-label={`${isExpanded ? "Collapse" : "Expand"} ${knowledgeBase.name}`}
                    aria-expanded={isExpanded}
                    onClick={() => void toggleKnowledgeBase(knowledgeBase.id)}
                  >
                    {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  </button>
                  <button
                    type="button"
                    className={`folder-select ${selectedKnowledgeBaseId === knowledgeBase.id ? "selected" : ""}`}
                    onClick={() => {
                      setSelectedKnowledgeBaseId(knowledgeBase.id);
                      setSelectedDocumentId("");
                      setIsMobileSidebarOpen(false);
                    }}
                  >
                    <BookOpen size={16} />
                    <span>{knowledgeBase.name}</span>
                  </button>
                </div>
                {isExpanded && (
                  <div className="folder-file-tree" aria-label={`Files in ${knowledgeBase.name}`}>
                    {folder?.loading && <small className="folder-tree-note">Loading files…</small>}
                    {folder?.error && <small className="folder-tree-note error">{folder.error}</small>}
                    {!folder?.loading && !folder?.error && folder?.items.map((document) => (
                      <button
                        className={`folder-file-row ${selectedDocumentId === document.id ? "selected" : ""}`}
                        key={document.id}
                        title={document.original_filename}
                        type="button"
                        disabled={document.status !== "ready"}
                        aria-pressed={selectedDocumentId === document.id}
                        onClick={() => {
                          setSelectedKnowledgeBaseId(knowledgeBase.id);
                          setSelectedDocumentId((current) => current === document.id ? "" : document.id);
                          setIsMobileSidebarOpen(false);
                        }}
                      >
                        <FileText size={14} />
                        <span>{document.original_filename}</span>
                        {document.status !== "ready" && (
                          <small>{document.status === "pending" ? "waiting" : document.status}</small>
                        )}
                      </button>
                    ))}
                    {!folder?.loading && !folder?.error && folder?.items.length === 0 && (
                      <small className="folder-tree-note">No files yet</small>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="sidebottom">
          <div className="workspace-label"><ShieldCheck size={16} /> Private workspace</div>
          <button onClick={handleLogout}>
            <LogOut size={17} /> Sign out
          </button>
        </div>
      </aside>

      <main>
        <section className="chat">
          <div className="chat-heading">
            <div>
              <h2>{selectedKnowledgeBase?.name ?? "Your workspace"}</h2>
              <p>{selectedDocumentId
                ? `Questions will use ${documents.find((document) => document.id === selectedDocumentId)?.original_filename ?? "the selected file"}. Click it again to search the whole folder.`
                : "Ask questions about files in this folder."}</p>
            </div>
            <div className="chat-actions">
              <span className="pill">{documents.length} file{documents.length === 1 ? "" : "s"}</span>
              <button className="upload-trigger" onClick={() => setIsUploadPanelOpen(true)} disabled={!selectedKnowledgeBaseId}>
                <Upload size={17} /> Add files
              </button>
            </div>
          </div>

          {errorMessage && (
            <div className="error banner" role="alert">
              {errorMessage}
              <button aria-label="Dismiss error" onClick={() => setErrorMessage("")}><X size={16} /></button>
            </div>
          )}

          <div className="messages">
            {messages.length === 0 && (
              <div className="empty">
                <BookOpen size={36} />
                <h2>Ask about your files</h2>
                <p>{documents.length ? "Ask a question to search this folder." : "Add a file, then ask a question about it."}</p>
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className={`bubble ${message.role}`}>
                <div>{message.content}</div>
                {message.sources && message.sources.length > 0 && (
                  <div className="sources">
                    <strong>Sources</strong>
                    {message.sources.map((source, sourceIndex) => (
                      <div className="source" key={`${source.document_id}-${sourceIndex}`}>
                        <span className="source-title">
                          {source.filename}{source.page_number != null ? ` · page ${source.page_number}` : ""}
                        </span>
                        <p>{source.excerpt}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {isBusy && <div className="muted" role="status" aria-live="polite">{busyMessage}</div>}
            <div ref={messagesEndRef} />
          </div>

          <form className="composer" onSubmit={handleSendQuestion}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about your documents..."
              disabled={!selectedKnowledgeBaseId || isBusy}
            />
            <button disabled={!selectedKnowledgeBaseId || isBusy || !question.trim()} aria-label="Send question">
              <Send size={19} />
            </button>
          </form>
        </section>
      </main>

      {isUploadPanelOpen && (
        <div className="upload-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !isBusy) setIsUploadPanelOpen(false); }}>
          <section className="upload-panel" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <div className="upload-panel-heading">
              <div>
                <h2 id="upload-title">Files in {selectedKnowledgeBase?.name ?? "this folder"}</h2>
                <p>PDF, DOCX, or TXT · up to 5 GB per file</p>
              </div>
              <button className="icon-button" aria-label="Close uploads" onClick={() => setIsUploadPanelOpen(false)} disabled={isBusy}><X /></button>
            </div>
            <label className={`upload ${isBusy ? "disabled" : ""}`}>
              <Upload size={21} />
              <strong>{isBusy ? busyMessage : "Choose files to upload"}</strong>
              <small>Files are added to the selected folder.</small>
              <input type="file" accept=".pdf,.docx,.txt" multiple onChange={handleUpload} disabled={isBusy} />
            </label>
            {errorMessage && <div className="error banner upload-error" role="alert">{errorMessage}</div>}
            <div className="filelist upload-filelist">
              {documents.map((document) => (
                <div className="file" key={document.id}>
                  <FileText size={20} />
                  <div>
                    <strong title={document.original_filename}>{document.original_filename}</strong>
                    <small>{document.status} · {document.chunk_count} passages · {(document.file_size_bytes / 1024).toFixed(0)} KB</small>
                    {document.processing_error && <small className="error document-error">{document.processing_error}</small>}
                  </div>
                  <button onClick={() => void handleDeleteDocument(document.id)} title="Delete file" aria-label={`Delete ${document.original_filename}`}><Trash2 size={16} /></button>
                </div>
              ))}
              {documents.length === 0 && <p className="muted">No files in this folder yet.</p>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

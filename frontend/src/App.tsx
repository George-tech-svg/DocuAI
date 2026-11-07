import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import {
  BookOpen,
  FileText,
  LogOut,
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
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isUploadPanelOpen, setIsUploadPanelOpen] = useState(false);
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
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isBusy]);

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
    setDocuments([]);
    setMessages([]);
    setConversationId(null);
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
      <aside>
        <div className="brand">
          <BookOpen /> DocuMind <span>AI</span>
        </div>

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

        <nav>
          {knowledgeBases.map((knowledgeBase) => (
            <button
              key={knowledgeBase.id}
              className={
                selectedKnowledgeBaseId === knowledgeBase.id ? "selected" : ""
              }
              onClick={() => setSelectedKnowledgeBaseId(knowledgeBase.id)}
            >
              <BookOpen size={16} />
              {knowledgeBase.name}
            </button>
          ))}
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
              <p>Ask questions about files in this folder.</p>
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

import { useEffect, useState } from "react";
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
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");

  // Chat messages and current conversation.
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);

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

  /** Upload one file and let the backend extract and index its contents. */
  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedKnowledgeBaseId) return;

    setIsBusy(true);
    setBusyMessage("Uploading and indexing your document. The first upload may take a little longer...");
    setErrorMessage("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await request<DocumentUploadResponse>(
        `/knowledge-bases/${selectedKnowledgeBaseId}/documents`,
        token,
        { method: "POST", body: formData }
      );

      await refreshDocuments();

      if (response.document.status === "failed") {
        setErrorMessage(
          response.document.processing_error ?? "Document processing failed."
        );
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
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

        <div className="smalltitle">KNOWLEDGE BASES</div>

        <form className="newkb" onSubmit={handleCreateKnowledgeBase}>
          <input
            placeholder="New knowledge base"
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
          <ShieldCheck size={16} /> Private workspace
          <button onClick={handleLogout}>
            <LogOut size={17} /> Sign out
          </button>
        </div>
      </aside>

      <main>
        <header>
          <div>
            <h2>{selectedKnowledgeBase?.name ?? "Your workspace"}</h2>
            <p>Upload documents, then ask questions grounded in their contents.</p>
          </div>
          <div className="pill">RAG workspace</div>
        </header>

        {errorMessage && (
          <div className="error banner">
            {errorMessage}
            <button onClick={() => setErrorMessage("")}>×</button>
          </div>
        )}

        <div className="columns">
          <section className="documents">
            <h3>
              <FileText size={19} /> Documents
            </h3>

            <label className={`upload ${isBusy ? "disabled" : ""}`}>
              <Upload size={21} />
              <strong>Upload a document</strong>
              <small>PDF, DOCX, TXT · up to 20 MB</small>
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={handleUpload}
                disabled={!selectedKnowledgeBaseId || isBusy}
              />
            </label>
            {!selectedKnowledgeBaseId && (
              <p className="muted">Create a knowledge base from the left panel before uploading.</p>
            )}

            <div className="filelist">
              {documents.map((document) => (
                <div className="file" key={document.id}>
                  <FileText size={20} />
                  <div>
                    <strong>{document.original_filename}</strong>
                    <small>
                      {document.status} · {document.chunk_count} passages · {(document.file_size_bytes / 1024).toFixed(0)} KB · {new Date(document.created_at).toLocaleDateString()}
                    </small>
                    {document.processing_error && (
                      <small className="error document-error">{document.processing_error}</small>
                    )}
                  </div>
                  <button
                    onClick={() => void handleDeleteDocument(document.id)}
                    title="Delete"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}

              {documents.length === 0 && (
                <p className="muted">No documents yet.</p>
              )}
            </div>
          </section>

          <section className="chat">
            <h3>
              <MessageCircle size={19} /> Ask your documents
            </h3>

            <div className="messages">
              {messages.length === 0 && (
                <div className="empty">
                  <BookOpen size={36} />
                  <h2>Answers from your knowledge</h2>
                  <p>Choose a knowledge base, upload a document, and ask a question.</p>
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
                            {source.filename}
                            {source.page_number != null
                              ? ` · page ${source.page_number}`
                              : ""}
                          </span>
                          <p>{source.excerpt}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {isBusy && <div className="muted" role="status" aria-live="polite">{busyMessage}</div>}
            </div>

            <form className="composer" onSubmit={handleSendQuestion}>
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask a question about your documents..."
                disabled={!selectedKnowledgeBaseId || isBusy}
              />
              <button
                disabled={!selectedKnowledgeBaseId || isBusy || !question.trim()}
              >
                <Send size={19} />
              </button>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}

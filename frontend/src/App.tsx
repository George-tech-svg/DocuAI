import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, FormEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  BookOpen,
  Archive,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Download,
  HelpCircle,
  FileText,
  LogOut,
  Menu,
  MoreVertical,
  Pencil,
  Pin,
  MessageCircle,
  Plus,
  Send,
  Settings as SettingsIcon,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { getErrorMessage, request } from "./api";
import AssistantMessage from "./AssistantMessage";
import AdminDashboard from "./AdminDashboard";
import BillingPage from "./BillingPage";
import TermsPrivacy from "./TermsPrivacy";
import GoogleSignIn from "./GoogleSignIn";
import { downloadAnswerPdf, downloadConversationPdf } from "./pdfExport";
import type {
  AuthenticationResponse,
  ChatMessage,
  ChatResponse,
  DocumentListResponse,
  DocumentRecord,
  DocumentUploadResponse,
  KnowledgeBase,
  KnowledgeBaseListResponse,
  ConversationRecord,
  SavedChatMessage,
  UserProfile,
} from "./types";

type ItemAction = { label: string; icon: ReactNode; onClick: () => void; danger?: boolean };

function ItemActionMenu({ label, open, onToggle, onClose, items }: {
  label: string;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  items: ItemAction[];
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open) return;
    function positionMenu() {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const menuHeight = items.length * 40 + 12;
      setMenuPosition({
        top: window.innerHeight - rect.bottom >= menuHeight ? rect.bottom + 4 : Math.max(8, rect.top - menuHeight - 4),
        left: Math.min(window.innerWidth - 188, Math.max(8, rect.right - 180)),
      });
    }
    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [open, items.length]);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !triggerRef.current?.contains(target) && !menuRef.current?.contains(target)) onClose();
    }
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    document.addEventListener("pointerdown", dismiss);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, onClose]);

  return (
    <div className="item-menu-wrap">
      <button ref={triggerRef} className="item-menu-trigger" type="button" aria-label={`More actions for ${label}`} aria-haspopup="menu" aria-expanded={open} title={`More actions for ${label}`} onClick={onToggle}>
        <MoreVertical size={17} />
      </button>
      {open && createPortal(
        <div ref={menuRef} className="item-menu" role="menu" aria-label={`Actions for ${label}`} style={{ top: menuPosition.top, left: menuPosition.left }}>
          {items.map((item) => (
            <button className={item.danger ? "danger-action" : ""} key={item.label} type="button" role="menuitem" onClick={() => { onClose(); item.onClick(); }}>
              {item.icon}<span>{item.label}</span>
            </button>
          ))}
        </div>, document.body,
      )}
    </div>
  );
}

/** The main application: sign in, manage documents, and chat with them. */
export default function App() {
  // Authentication form and saved session.
  const [token, setToken] = useState(
    localStorage.getItem("documind_token") ?? ""
  );
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [activePage, setActivePage] = useState<"workspace" | "admin" | "billing" | "settings">("workspace");
  const [legalPage, setLegalPage] = useState<"terms" | "privacy" | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [hasAcceptedTerms, setHasAcceptedTerms] = useState(false);
  const [adminBootstrapAvailable, setAdminBootstrapAvailable] = useState(false);
  const [showAdminBootstrap, setShowAdminBootstrap] = useState(false);
  const [adminSetupCode, setAdminSetupCode] = useState("");

  useEffect(() => {
    if (token) return;
    let cancelled = false;
    void request<{ available: boolean }>("/auth/admin/bootstrap/status", "")
      .then((status) => { if (!cancelled) setAdminBootstrapAvailable(status.available); })
      .catch(() => { if (!cancelled) setAdminBootstrapAvailable(false); });
    return () => { cancelled = true; };
  }, [token]);

  // Knowledge bases and documents in the selected workspace.
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [expandedKnowledgeBaseIds, setExpandedKnowledgeBaseIds] = useState<Set<string>>(() => new Set());
  const [expandedDocumentIds, setExpandedDocumentIds] = useState<Set<string>>(() => new Set());
  const [folderDocuments, setFolderDocuments] = useState<Record<string, { items: DocumentRecord[]; loading: boolean; error: string }>>({});
  const [isUploadPanelOpen, setIsUploadPanelOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const savedWidth = Number(localStorage.getItem("documind_sidebar_width"));
    return Number.isFinite(savedWidth) && savedWidth >= 240 && savedWidth <= 560 ? savedWidth : 285;
  });
  const [openItemMenuId, setOpenItemMenuId] = useState<string | null>(null);
  const [isHelpPanelOpen, setIsHelpPanelOpen] = useState(false);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");
  const [conversationHistory, setConversationHistory] = useState<ConversationRecord[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);

  // Chat messages and current conversation.
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const questionInputRef = useRef<HTMLInputElement>(null);

  // Shared feedback for network operations.
  const [isBusy, setIsBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("Processing...");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => { localStorage.setItem("documind_sidebar_width", String(sidebarWidth)); }, [sidebarWidth]);

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

  /** Load saved conversations for the history panel. */
  async function refreshConversationHistory() {
    if (!token) {
      setConversationHistory([]);
      return;
    }
    setIsHistoryLoading(true);
    try {
      const history = await request<ConversationRecord[]>("/conversations", token);
      setConversationHistory(history);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsHistoryLoading(false);
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
    void refreshConversationHistory();
  }, [token]);

  useEffect(() => {
    if (!token) { setUserProfile(null); return; }
    let cancelled = false;
    void request<UserProfile>("/auth/me", token)
      .then((profile) => { if (!cancelled) setUserProfile(profile); })
      .catch((error) => { if (!cancelled) setErrorMessage(getErrorMessage(error)); });
    return () => { cancelled = true; };
  }, [token]);

  useEffect(() => {
    void refreshDocuments();
    setMessages([]);
    setConversationId(null);
  }, [token, selectedKnowledgeBaseId]);

  // Uploads are indexed in the background; poll until the saved status changes.
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
    if (!isMobileSidebarOpen && !isHelpPanelOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMobileSidebarOpen(false);
        setIsHelpPanelOpen(false);
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isMobileSidebarOpen, isHelpPanelOpen]);

  /** Register a new user or sign in an existing user. */
  async function handleAuthentication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    if ((isRegistering && !fullName.trim()) || !email.trim() || !password || (isRegistering && !confirmPassword)) {
      setErrorMessage(isRegistering ? "Please fill in all fields." : "Please enter both email and password.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setErrorMessage("Please enter a valid email address.");
      return;
    }
    if (isRegistering && password !== confirmPassword) {
      setErrorMessage("Passwords do not match. Please check and try again.");
      return;
    }
    if (isRegistering && password.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }
    if (isRegistering && !hasAcceptedTerms) {
      setErrorMessage("Accept the Terms of Service and Privacy Notice to create your account.");
      return;
    }
    setIsBusy(true);
    setBusyMessage(isRegistering ? "Creating your account..." : "Signing you in...");
    setErrorMessage("");

    try {
      const endpoint = isRegistering ? "/auth/register" : "/auth/login";
      const credentials = isRegistering
        ? { full_name: fullName.trim(), email: email.trim(), password, accept_terms: hasAcceptedTerms }
        : { email: email.trim(), password };

      const response = await request<AuthenticationResponse>(endpoint, "", {
        method: "POST",
        body: JSON.stringify(credentials),
      });

      if (isRegistering) {
        setIsRegistering(false);
        setPassword("");
        setConfirmPassword("");
        setHasAcceptedTerms(false);
        setSuccessMessage("Account created successfully!");
        return;
      }
      localStorage.setItem("documind_token", response.access_token);
      setToken(response.access_token);
      setPassword("");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleAdminBootstrap(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasAcceptedTerms) {
      setErrorMessage("Accept the Terms of Service and Privacy Notice to create an account.");
      return;
    }
    setIsBusy(true);
    setBusyMessage("Creating the first administrator...");
    setErrorMessage("");
    try {
      const response = await request<AuthenticationResponse>("/auth/admin/bootstrap", "", {
        method: "POST",
        body: JSON.stringify({ full_name: fullName, email, password, setup_code: adminSetupCode, accept_terms: hasAcceptedTerms }),
      });
      localStorage.setItem("documind_token", response.access_token);
      setAdminBootstrapAvailable(false);
      setToken(response.access_token);
      setPassword("");
      setAdminSetupCode("");
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleGoogleSignIn(credential: string, mode: "login" | "register", acceptedTerms: boolean) {
    if (mode === "register" && !acceptedTerms) {
      setErrorMessage("Accept the Terms of Service and Privacy Notice before creating your account.");
      return;
    }
    setIsBusy(true);
    setBusyMessage(mode === "register" ? "Creating your account with Google..." : "Signing you in with Google...");
    setErrorMessage("");
    try {
      const response = await request<AuthenticationResponse>("/auth/google", "", {
        method: "POST",
        body: JSON.stringify({ credential, mode, accept_terms: acceptedTerms }),
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
    setConversationHistory([]);
    setIsMobileSidebarOpen(false);
    setUserProfile(null);
    setActivePage("workspace");
    setLegalPage(null);
    setErrorMessage("");
  }

  function openLegalPage(page: "terms" | "privacy") {
    setLegalPage(page);
    setIsMobileSidebarOpen(false);
  }

  /** Start an empty conversation while keeping the selected folder and file. */
  function handleNewChat() {
    if (isBusy) return;
    setConversationId(null);
    setMessages([]);
    setQuestion("");
    setErrorMessage("");
    setIsHelpPanelOpen(false);
    setIsMobileSidebarOpen(false);
    window.setTimeout(() => questionInputRef.current?.focus(), 0);
  }

  /** Reopen a saved conversation, including the source excerpts for each answer. */
  async function handleOpenConversation(conversation: ConversationRecord) {
    if (isBusy) return;
    setIsBusy(true);
    setBusyMessage("Opening saved conversation...");
    setErrorMessage("");
    if (conversation.knowledge_base_id) {
      setSelectedKnowledgeBaseId(conversation.knowledge_base_id);
    }
    setSelectedDocumentId(conversation.document_id ?? "");
    if (conversation.document_id && conversation.knowledge_base_id) {
      setExpandedKnowledgeBaseIds((previous) => new Set(previous).add(conversation.knowledge_base_id!));
      setExpandedDocumentIds((previous) => new Set(previous).add(conversation.document_id!));
    }
    try {
      const saved = await request<SavedChatMessage[]>(
        `/conversations/${conversation.id}/messages`,
        token,
      );
      setMessages(saved.map(({ role, content, sources }) => ({
        role: role === "assistant" ? "assistant" : "user",
        content,
        sources,
      })));
      setConversationId(conversation.id);
      setIsMobileSidebarOpen(false);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  /** Download a history item without first navigating into it. */
  async function handleDownloadConversation(conversation: ConversationRecord) {
    try {
      const saved = await request<SavedChatMessage[]>(
        `/conversations/${conversation.id}/messages`,
        token,
      );
      await downloadConversationPdf(conversation.title, saved);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  function chooseExamplePrompt(prompt: string) {
    setQuestion(prompt);
    setIsHelpPanelOpen(false);
    window.setTimeout(() => questionInputRef.current?.focus(), 0);
  }

  function clearCurrentConversation() {
    setConversationId(null);
    setMessages([]);
    setQuestion("");
  }

  function handleSelectKnowledgeBase(knowledgeBaseId: string) {
    if (knowledgeBaseId !== selectedKnowledgeBaseId || selectedDocumentId) {
      clearCurrentConversation();
    }
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setSelectedDocumentId("");
    setIsMobileSidebarOpen(false);
  }

  function handleSelectDocument(knowledgeBaseId: string, documentId: string) {
    if (knowledgeBaseId !== selectedKnowledgeBaseId || documentId !== selectedDocumentId) {
      clearCurrentConversation();
    }
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setSelectedDocumentId(documentId);
    setExpandedKnowledgeBaseIds((previous) => new Set(previous).add(knowledgeBaseId));
    setExpandedDocumentIds((previous) => new Set(previous).add(documentId));
    setIsMobileSidebarOpen(false);
  }

  function toggleDocumentHistory(documentId: string) {
    setExpandedDocumentIds((previous) => {
      const next = new Set(previous);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
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
        if (!/\.(pdf|txt)$/i.test(file.name)) {
          failures.push("Invalid file type. Please upload a PDF or TXT file.");
          continue;
        }
        if (file.size > 10_000_000) {
          failures.push("File is too large. Maximum size is 10MB.");
          continue;
        }
        const formData = new FormData();
        formData.append("file", file);

        try {
          const response = await request<DocumentUploadResponse>(
            `/knowledge-bases/${selectedKnowledgeBaseId}/documents`,
            token,
            { method: "POST", body: formData }
          );
          if (response.document.status === "ready" || response.document.status === "pending" || response.document.status === "processing") {
            uploaded += 1;
          } else {
            failures.push("Failed to process the file. Please try again.");
          }
        } catch (error) {
          failures.push(getErrorMessage(error));
        }
      }
      await refreshDocuments();
      if (failures.length) {
        const shownFailures = failures.slice(0, 3).join("; ");
        const remaining = failures.length > 3 ? `; and ${failures.length - 3} more` : "";
        setErrorMessage(uploaded ? `${uploaded} of ${files.length} files uploaded. ${shownFailures}${remaining}` : shownFailures);
      }
    } finally {
      setIsBusy(false);
      event.target.value = "";
    }
  }

  /** Delete one document after the user confirms the action. */
  async function handleDeleteDocument(knowledgeBaseId: string, documentId: string) {
    if (!window.confirm("Delete this file and its saved chats? This cannot be undone.")) return;

    try {
      await request<void>(
        `/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
        token,
        { method: "DELETE" }
      );
      if (selectedDocumentId === documentId) { setSelectedDocumentId(""); setConversationId(null); setMessages([]); }
      await refreshDocuments();
      await refreshConversationHistory();
      const refreshed = await request<DocumentListResponse>(`/knowledge-bases/${knowledgeBaseId}/documents`, token);
      setFolderDocuments((previous) => ({ ...previous, [knowledgeBaseId]: { items: refreshed.items, loading: false, error: "" } }));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function updateItem(path: string, data: Record<string, string | boolean>) {
    try {
      await request(path, token, { method: "PATCH", body: JSON.stringify(data) });
      await Promise.all([refreshKnowledgeBases(), refreshDocuments(), refreshConversationHistory()]);
      await Promise.all(Array.from(expandedKnowledgeBaseIds).map(async (knowledgeBaseId) => {
        const refreshed = await request<DocumentListResponse>(`/knowledge-bases/${knowledgeBaseId}/documents`, token);
        setFolderDocuments((previous) => ({ ...previous, [knowledgeBaseId]: { items: refreshed.items, loading: false, error: "" } }));
      }));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function handleDeleteConversation(conversation: ConversationRecord) {
    if (!window.confirm(`Delete chat “${conversation.title}”? This cannot be undone.`)) return;
    try {
      await request<void>(`/conversations/${conversation.id}`, token, { method: "DELETE" });
      if (conversationId === conversation.id) { setConversationId(null); setMessages([]); }
      await refreshConversationHistory();
    } catch (error) { setErrorMessage(getErrorMessage(error)); }
  }

  async function handleDeleteKnowledgeBase(knowledgeBase: KnowledgeBase) {
    if (!window.confirm(`Delete folder “${knowledgeBase.name}” and all its files and chats? This cannot be undone.`)) return;
    try {
      await request<void>(`/knowledge-bases/${knowledgeBase.id}`, token, { method: "DELETE" });
      if (selectedKnowledgeBaseId === knowledgeBase.id) {
        setSelectedKnowledgeBaseId(""); setSelectedDocumentId(""); setConversationId(null); setMessages([]);
      }
      await Promise.all([refreshKnowledgeBases(), refreshConversationHistory()]);
    } catch (error) { setErrorMessage(getErrorMessage(error)); }
  }

  function promptRename(label: string, currentName: string, save: (name: string) => void) {
    const value = window.prompt(`Rename ${label}`, currentName);
    if (value?.trim() && value.trim() !== currentName) save(value.trim());
  }

  /** Send a question and display the AI answer with its document sources. */
  async function handleSendQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDocumentId) {
      setErrorMessage("Please select a file to use the chatbot.");
      return;
    }
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
          document_id: selectedDocumentId,
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
      void refreshConversationHistory();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  if (legalPage) {
    return <TermsPrivacy document={legalPage} onOpen={setLegalPage} onBack={() => setLegalPage(null)} />;
  }

  // Before login, show only the authentication form.
  if (!token) {
    return (
      <div className="auth-wrap">
        {adminBootstrapAvailable && <button className="admin-setup-dot" type="button" aria-label="Open one-time administrator setup" title="Administrator setup" onClick={() => { setShowAdminBootstrap(true); setErrorMessage(""); }} />}
        {showAdminBootstrap && adminBootstrapAvailable ? (
        <form className="auth-card" onSubmit={handleAdminBootstrap}>
          <div className="brand"><BookOpen /> DocuMind <span>AI</span></div>
          <h1>First administrator setup</h1>
          <p>This one-time setup is available until the first super administrator is registered.</p>
          <input required minLength={2} maxLength={150} placeholder="Full name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          <input type="email" required placeholder="Email address" value={email} onChange={(event) => setEmail(event.target.value)} />
          <input type="password" required minLength={8} maxLength={128} autoComplete="new-password" placeholder="Password (at least 8 characters)" value={password} onChange={(event) => setPassword(event.target.value)} />
          <input type="password" required minLength={16} maxLength={256} autoComplete="off" placeholder="Private setup code" value={adminSetupCode} onChange={(event) => setAdminSetupCode(event.target.value)} />
          <div className="auth-terms">
            <label><input type="checkbox" required checked={hasAcceptedTerms} onChange={(event) => setHasAcceptedTerms(event.target.checked)} /><span>I agree to the</span></label>
            <button type="button" onClick={() => openLegalPage("terms")}>Terms of Service</button><span>and</span>
            <button type="button" onClick={() => openLegalPage("privacy")}>Privacy Notice</button><span>.</span>
          </div>
          {errorMessage && <p className="error">{errorMessage}</p>}
          <button disabled={isBusy}>{isBusy ? "Please wait..." : "Register first administrator"}</button>
          <p><button type="button" className="auth-toggle" onClick={() => { setShowAdminBootstrap(false); setErrorMessage(""); }}>Back to sign in</button></p>
        </form>
        ) : <form className="auth-card" noValidate onSubmit={handleAuthentication}>
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
            minLength={isRegistering ? 8 : undefined}
            maxLength={isRegistering ? 128 : undefined}
            autoComplete={isRegistering ? "new-password" : "current-password"}
            title={
              isRegistering
                ? "Use at least 8 characters."
                : undefined
            }
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {isRegistering && (
            <>
              <input
                type="password"
                required
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="error password-mismatch" role="status">Passwords do not match. Please check and try again.</p>
              )}
              <div className="auth-terms">
                <label>
                  <input type="checkbox" required checked={hasAcceptedTerms} onChange={(event) => setHasAcceptedTerms(event.target.checked)} />
                  <span>I agree to the</span>
                </label>
                <button type="button" onClick={() => openLegalPage("terms")}>Terms of Service</button>
                <span>and</span>
                <button type="button" onClick={() => openLegalPage("privacy")}>Privacy Notice</button>
                <span>.</span>
              </div>
            </>
          )}

          {isRegistering && (
            <p className="muted">
              Use at least 8 characters.
            </p>
          )}

          {errorMessage && <p className="error">{errorMessage}</p>}
          {successMessage && <p className="success" role="status">{successMessage}</p>}

          <button disabled={isBusy}>
            {isBusy
              ? isRegistering ? "Creating account..." : "Signing in..."
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
                setConfirmPassword("");
                setHasAcceptedTerms(false);
                setErrorMessage("");
                setSuccessMessage("");
              }}
            >
              {isRegistering
                ? "Already have an account? Sign in"
                : "New here? Create an account"}
            </button>
          </p>
        </form>}
        {!showAdminBootstrap && (
          <GoogleSignIn
            mode={isRegistering ? "register" : "login"}
            acceptedTerms={hasAcceptedTerms}
            onCredential={(credential, mode, accepted) => void handleGoogleSignIn(credential, mode, accepted)}
          />
        )}
        <nav className="auth-legal-nav" aria-label="Legal information">
          <button type="button" onClick={() => openLegalPage("terms")}>Terms of service</button>
          <span aria-hidden="true">·</span>
          <button type="button" onClick={() => openLegalPage("privacy")}>Privacy notice</button>
        </nav>
      </div>
    );
  }

  if (activePage === "settings") return (
    <main className="settings-wrap">
      <section className="settings-card">
        <button className="legal-back" type="button" onClick={() => setActivePage("workspace")}><ChevronLeft size={17} /> Back to workspace</button>
        <div className="settings-heading"><SettingsIcon size={23} /><div><h1>Account settings</h1><p>Manage your session and find service information.</p></div></div>
        <section className="settings-detail"><h2>Signed-in account</h2><p><strong>Name</strong><span>{userProfile?.full_name ?? "Loading account…"}</span></p><p><strong>Email</strong><span>{userProfile?.email ?? ""}</span></p></section>
        <section className="settings-detail"><h2>Plan and billing</h2><p>Review your plan or subscription payment status.</p><button type="button" onClick={() => setActivePage("billing")}><CreditCard size={16} /> Open plan &amp; billing</button></section>
        <section className="settings-detail"><h2>Legal and privacy</h2><div className="settings-links"><button type="button" onClick={() => openLegalPage("terms")}>Read Terms of service</button><button type="button" onClick={() => openLegalPage("privacy")}>Read Privacy notice</button></div></section>
        <button className="settings-signout" type="button" onClick={handleLogout}><LogOut size={17} /> Sign out of this account</button>
      </section>
    </main>
  );

  if (activePage === "admin") return <AdminDashboard token={token} onBack={() => setActivePage("workspace")} />;
  if (activePage === "billing") return <BillingPage token={token} onBack={() => setActivePage("workspace")} />;

  const selectedKnowledgeBase = knowledgeBases.find(
    (knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId
  );
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId);
  const examplePrompts = [
    { label: "Prepare a teaching pack", prompt: "Using only the selected document, prepare a practical teacher-ready lesson pack. Include: topic and learning objectives (mark anything the source does not specify as 'Teacher to fill in'), a brief lesson sequence, a clear explanation with examples, one activity requiring few or no special materials, practice at support/standard/challenge levels, a short formative quiz with answer key, and likely misconceptions with follow-up suggestions. Cite source numbers like [1] beside claims. Keep it clear, printable, and easy to adapt. Do not invent curriculum requirements." },
    { label: "Make a teaching summary", prompt: "Create a clear teaching summary of this document: main ideas, learning objectives only where stated, key terms, worked examples, and a short recap. Use plain language and cite source numbers like [1]." },
    { label: "Create learner practice", prompt: "Create a short practice sheet from this document with questions at three difficulty levels, then provide a separate answer key with source citations. Do not introduce facts outside the document." },
    { label: "Create a quick quiz", prompt: "Create 8 questions from this document: a mix of multiple-choice and short-answer questions, followed by a cited answer key. Keep the questions suitable for classroom formative assessment." },
    { label: "Explain the key ideas", prompt: "Explain the most important ideas in this document in simple language, using examples from the document where helpful. Cite the supporting source numbers like [1]." },
  ];

  // After login, show the sidebar, document list, and chat panel.
  return (
    <div className="shell">
      <div className="mobile-topbar">
        <button
          className="folder-menu-trigger"
          type="button"
          aria-label="Open folder sidebar"
          aria-expanded={isMobileSidebarOpen}
          onClick={() => setIsMobileSidebarOpen(true)}
        >
          <Menu size={19} />
          <span>{selectedDocument?.original_filename ?? selectedKnowledgeBase?.name ?? "Choose a file"}</span>
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

      <aside
        className={isMobileSidebarOpen ? "mobile-sidebar-open" : ""}
        style={{ "--sidebar-width": `${sidebarWidth}px` } as CSSProperties}
      >
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
                    onClick={() => handleSelectKnowledgeBase(knowledgeBase.id)}
                  >
                    <BookOpen size={16} />
                    <span>{knowledgeBase.name}</span>
                    {knowledgeBase.is_archived && <small>Archived</small>}
                    {knowledgeBase.is_pinned && <Pin size={13} aria-label="Pinned" />}
                  </button>
                  <ItemActionMenu
                    label={knowledgeBase.name}
                    open={openItemMenuId === `folder-${knowledgeBase.id}`}
                    onToggle={() => setOpenItemMenuId((current) => current === `folder-${knowledgeBase.id}` ? null : `folder-${knowledgeBase.id}`)}
                    onClose={() => setOpenItemMenuId(null)}
                    items={[
                      { label: knowledgeBase.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { is_pinned: !knowledgeBase.is_pinned }) },
                      { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("folder", knowledgeBase.name, (name) => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { name })) },
                      { label: knowledgeBase.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { is_archived: !knowledgeBase.is_archived }) },
                      { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => void handleDeleteKnowledgeBase(knowledgeBase) },
                    ]}
                  />
                </div>
                {isExpanded && (
                  <div className="folder-file-tree" aria-label={`Files in ${knowledgeBase.name}`}>
                    {folder?.loading && <small className="folder-tree-note">Loading files…</small>}
                    {folder?.error && <small className="folder-tree-note error">{folder.error}</small>}
                    {!folder?.loading && !folder?.error && folder?.items.map((document) => {
                      const isDocumentExpanded = expandedDocumentIds.has(document.id);
                      const documentChats = conversationHistory.filter((conversation) => conversation.document_id === document.id);
                      return (
                        <div className="document-tree-node" key={document.id}>
                          <div className="document-tree-row">
                            <button
                              className="document-expand"
                              type="button"
                              aria-label={`${isDocumentExpanded ? "Collapse" : "Expand"} chat history for ${document.original_filename}`}
                              aria-expanded={isDocumentExpanded}
                              onClick={() => toggleDocumentHistory(document.id)}
                            >
                              {isDocumentExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            </button>
                            <button
                              className={`folder-file-row ${selectedDocumentId === document.id ? "selected" : ""}`}
                              title={document.original_filename}
                              type="button"
                              disabled={document.status !== "ready"}
                              aria-pressed={selectedDocumentId === document.id}
                              onClick={() => handleSelectDocument(knowledgeBase.id, document.id)}
                            >
                              <FileText size={14} />
                              <span>{document.original_filename}</span>
                              {document.is_archived && <small>archived</small>}
                              {document.is_pinned && <Pin size={12} aria-label="Pinned" />}
                              {document.status !== "ready" && (
                                <small>{document.status === "pending" ? "waiting" : document.status}</small>
                              )}
                            </button>
                            <ItemActionMenu
                              label={document.original_filename}
                              open={openItemMenuId === `document-${document.id}`}
                              onToggle={() => setOpenItemMenuId((current) => current === `document-${document.id}` ? null : `document-${document.id}`)}
                              onClose={() => setOpenItemMenuId(null)}
                              items={[
                                { label: document.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { is_pinned: !document.is_pinned }) },
                                { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("file", document.original_filename, (original_filename) => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { original_filename })) },
                                { label: document.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { is_archived: !document.is_archived }) },
                                { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => void handleDeleteDocument(knowledgeBase.id, document.id) },
                              ]}
                            />
                          </div>
                          {isDocumentExpanded && (
                            <div className="document-chat-list" aria-label={`Chats about ${document.original_filename}`}>
                              {isHistoryLoading && <small className="history-empty">Loading chats…</small>}
                              {!isHistoryLoading && documentChats.length === 0 && (
                                <small className="history-empty">No chats for this document yet.</small>
                              )}
                              {documentChats.map((conversation) => (
                                <div className={`history-row ${conversationId === conversation.id ? "selected" : ""} ${conversation.is_archived ? "archived" : ""}`} key={conversation.id}>
                                  <button
                                    className="history-open"
                                    type="button"
                                    title={conversation.title}
                                    disabled={isBusy}
                                    onClick={() => void handleOpenConversation(conversation)}
                                  >
                                    <MessageCircle size={13} />
                                    <span>{conversation.title || "New conversation"}</span>
                                    {conversation.is_pinned && <Pin size={12} aria-label="Pinned" />}
                                  </button>
                                  <ItemActionMenu
                                    label={conversation.title}
                                    open={openItemMenuId === `chat-${conversation.id}`}
                                    onToggle={() => setOpenItemMenuId((current) => current === `chat-${conversation.id}` ? null : `chat-${conversation.id}`)}
                                    onClose={() => setOpenItemMenuId(null)}
                                    items={[
                                      { label: conversation.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/conversations/${conversation.id}`, { is_pinned: !conversation.is_pinned }) },
                                      { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("chat", conversation.title, (title) => void updateItem(`/conversations/${conversation.id}`, { title })) },
                                      { label: conversation.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/conversations/${conversation.id}`, { is_archived: !conversation.is_archived }) },
                                      { label: "Download", icon: <Download size={15} />, onClick: () => void handleDownloadConversation(conversation) },
                                      { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => void handleDeleteConversation(conversation) },
                                    ]}
                                  />
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
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
          <button type="button" onClick={() => { setActivePage("billing"); setIsMobileSidebarOpen(false); }}>
            <CreditCard size={17} /> Plan &amp; billing
          </button>
          <button type="button" onClick={() => { setActivePage("settings"); setIsMobileSidebarOpen(false); }}>
            <SettingsIcon size={17} /> Account settings
          </button>
          {userProfile?.is_superuser && (
            <button type="button" onClick={() => { setActivePage("admin"); setIsMobileSidebarOpen(false); }}>
              <ShieldCheck size={17} /> Admin console
            </button>
          )}
          <button onClick={handleLogout}>
            <LogOut size={17} /> Sign out
          </button>
          <div className="sidebar-legal-links">
            <button type="button" onClick={() => openLegalPage("terms")}>Terms</button>
            <span aria-hidden="true">·</span>
            <button type="button" onClick={() => openLegalPage("privacy")}>Privacy</button>
          </div>
        </div>
      </aside>

      <div
        className="workspace-resizer"
        role="separator"
        aria-label="Resize folder sidebar and chat area"
        aria-orientation="vertical"
        aria-valuemin={240}
        aria-valuemax={Math.max(240, Math.min(560, window.innerWidth - 360))}
        aria-valuenow={sidebarWidth}
        tabIndex={0}
        title="Drag to resize the folder sidebar"
        onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            setSidebarWidth(Math.max(240, Math.min(Math.min(560, window.innerWidth - 360), event.clientX)));
          }
        }}
        onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setSidebarWidth((width) => Math.max(240, width - 20));
          if (event.key === "ArrowRight") setSidebarWidth((width) => Math.min(Math.min(560, window.innerWidth - 360), width + 20));
        }}
      />

      <main>
        <section className="chat">
          <div className="chat-heading">
            <div>
              <h2>{selectedDocument?.original_filename ?? selectedKnowledgeBase?.name ?? "Your workspace"}</h2>
              <p>{selectedDocumentId
                ? "Questions and saved chats are tied to this file. Expand it in the sidebar to reopen a chat."
              : "Please select a file to use the chatbot."}</p>
            </div>
            <div className="chat-actions">
              <span className="pill">{documents.length} file{documents.length === 1 ? "" : "s"}</span>
              <button className="chat-tool-button" type="button" onClick={handleNewChat} title="New chat" aria-label="Start a new chat" disabled={isBusy || !selectedDocumentId}>
                <Plus size={17} />
              </button>
              {conversationId && messages.length > 0 && (
                <button
                  className="chat-tool-button"
                  type="button"
                  title="Download this conversation"
                  aria-label="Download this conversation"
                  disabled={isBusy}
                  onClick={() => void downloadConversationPdf(
                    conversationHistory.find((item) => item.id === conversationId)?.title ?? "DocuMind conversation",
                    messages,
                  ).catch((error) => setErrorMessage(getErrorMessage(error)))}
                >
                  <Download size={17} />
                </button>
              )}
              <button className="chat-tool-button" type="button" onClick={() => setIsHelpPanelOpen(true)} title="Help and examples" aria-label="Open help and examples">
                <HelpCircle size={17} />
              </button>
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
                <h2>What would you like to learn?</h2>
                <p>{selectedDocumentId
                  ? "Ask about this file or choose a ready-made task. Your chats stay under the file, and you can download useful answers as PDFs."
                  : "Choose a ready file from the folder sidebar. Each file keeps its own chat history."}</p>
                {selectedDocumentId && (
                  <div className="prompt-suggestions">
                    {examplePrompts.map((example) => (
                      <button key={example.label} type="button" onClick={() => chooseExamplePrompt(example.prompt)}>
                        {example.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className={`bubble ${message.role}`}>
                {message.role === "assistant"
                  ? <AssistantMessage content={message.content} />
                  : <div>{message.content}</div>}
                {message.role === "assistant" && (
                  <button
                    className="answer-print"
                    type="button"
                    title="Download this answer as PDF"
                    onClick={() => void downloadAnswerPdf(
                      message,
                      conversationHistory.find((item) => item.id === conversationId)?.title ?? "DocuMind teaching notes",
                    ).catch((error) => setErrorMessage(getErrorMessage(error)))}
                  ><Download size={14} /> Download PDF</button>
                )}
                {message.sources && message.sources.length > 0 && (
                  <div className="sources">
                    <strong>Sources</strong>
                    {message.sources.map((source, sourceIndex) => (
                      <div className="source" key={`${source.document_id}-${sourceIndex}`}>
                        <span className="source-title">
                          [{sourceIndex + 1}] {source.filename}{source.page_number != null ? ` · page ${source.page_number}` : ""}
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
              ref={questionInputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={selectedDocumentId ? "Ask a question about the selected file…" : "Choose a file to start chatting…"}
              disabled={!selectedDocumentId || isBusy}
            />
            <button disabled={!selectedDocumentId || isBusy || !question.trim()} aria-label="Send question">
              <Send size={19} />
            </button>
          </form>
        </section>
      </main>

      {isHelpPanelOpen && (
        <div className="help-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setIsHelpPanelOpen(false); }}>
          <section className="help-panel" role="dialog" aria-modal="true" aria-labelledby="help-title">
            <div className="help-panel-heading">
              <div>
                <h2 id="help-title">Help with your documents</h2>
                <p>Turn your files into clear, useful work.</p>
              </div>
              <button className="icon-button" type="button" aria-label="Close help" onClick={() => setIsHelpPanelOpen(false)}><X size={19} /></button>
            </div>
            <div className="help-panel-content">
              <h3>Try an example</h3>
              {examplePrompts.map((example) => (
                <button className="help-example" key={example.label} type="button" onClick={() => chooseExamplePrompt(example.prompt)}>
                  <strong>{example.label}</strong>
                  <span>{example.prompt}</span>
                </button>
              ))}
              <div className="help-note">
                <strong>Your work is saved</strong>
                <p>Each question and answer is stored in Chat History for this folder. Select a past chat to reopen it, or download the full exchange and cited sources as a PDF.</p>
              </div>
            </div>
          </section>
        </div>
      )}

      {isUploadPanelOpen && (
        <div className="upload-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !isBusy) setIsUploadPanelOpen(false); }}>
          <section className="upload-panel" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <div className="upload-panel-heading">
              <div>
                <h2 id="upload-title">Files in {selectedKnowledgeBase?.name ?? "this folder"}</h2>
                <p>PDF or TXT · up to 10 MB per file</p>
              </div>
              <button className="icon-button" aria-label="Close uploads" onClick={() => setIsUploadPanelOpen(false)} disabled={isBusy}><X /></button>
            </div>
            <label className={`upload ${isBusy ? "disabled" : ""}`}>
              <Upload size={21} />
              <strong>{isBusy ? busyMessage : "Choose files to upload"}</strong>
              <small>Files are added to the selected folder.</small>
              <input type="file" accept=".pdf,.txt" multiple onChange={handleUpload} disabled={isBusy} />
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
                  <button onClick={() => void handleDeleteDocument(selectedKnowledgeBaseId, document.id)} title="Delete file" aria-label={`Delete ${document.original_filename}`}><Trash2 size={16} /></button>
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

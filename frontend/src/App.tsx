import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, FormEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  BookOpen,
  Briefcase,
  Archive,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  CalendarDays,
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
  ThumbsUp,
  ThumbsDown,
  Flag,
  Upload,
  X,
} from "lucide-react";

import { getErrorMessage, request } from "./api";
import AssistantMessage from "./AssistantMessage";
const AdminDashboard = lazy(() => import("./AdminDashboard"));
const BillingPage = lazy(() => import("./BillingPage"));
const TermsPrivacy = lazy(() => import("./TermsPrivacy"));
const GoogleSignIn = lazy(() => import("./GoogleSignIn"));
const ImportantDates = lazy(() => import("./ImportantDates"));
const WhatsAppSettings = lazy(() => import("./WhatsAppSettings"));
const AnswerLanguageSettings = lazy(() => import("./AnswerLanguageSettings"));
import { downloadAnswerPdf, downloadConversationPdf, downloadConversationsPdf } from "./pdfExport";
const LibraryPage = lazy(() => import("./LibraryPage"));
const OrganizationsPage = lazy(() => import("./OrganizationsPage"));
const DataProcessingPage = lazy(() => import("./DataProcessingPage"));
const BusinessToolsPage = lazy(() => import("./BusinessToolsPage"));
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
type DeleteTarget =
  | { kind: "document"; knowledgeBaseId: string; document: DocumentRecord }
  | { kind: "folder"; knowledgeBase: KnowledgeBase };
type DeleteDialogState = {
  target: DeleteTarget;
  conversations: ConversationRecord[] | null;
  documentCount: number | null;
  loading: boolean;
  deleting: boolean;
  error: string;
};

function friendlyProcessingError(reason: string | null): string {
  const normalized = (reason ?? "").toLowerCase();
  if (normalized.includes("could not read text") || normalized.includes("no readable text")) {
    return "We could not read the text clearly. Try a clearer scan or photo, or upload a text-based document.";
  }
  if (normalized.includes("too large") || normalized.includes("maximum") || normalized.includes("characters")) {
    return "This file is too large to process. Choose a smaller supported file.";
  }
  if (normalized.includes("cloudinary") || normalized.includes("storage is not configured")) {
    return "The file could not be saved. Document storage may need attention. Please try again later or contact support.";
  }
  if (normalized.includes("invalid pdf") || normalized.includes("pdf header") || normalized.includes("damaged")) {
    return "This file could not be opened. It may be damaged or password-protected. Try another supported file.";
  }
  return "We could not read or process this file. It may be damaged, protected, or unreadable. Try another supported file.";
}

function friendlyUploadError(error: unknown): string {
  const message = getErrorMessage(error);
  if (/\b413\b/.test(message)) {
    return "The upload service could not accept this file because it is too large. Choose a smaller supported file.";
  }
  if (/network error/i.test(message)) {
    return "Network error. Please check your connection and try again.";
  }
  if (/\b5\d\d\b|something went wrong on our end/i.test(message)) {
    return "Something went wrong while uploading this file. Please try again later.";
  }
  return message || "The upload could not be completed. Please try again.";
}

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
  const [token, setToken] = useState("");
  const [sessionChecking, setSessionChecking] = useState(true);
  const [consentRequired, setConsentRequired] = useState(false);
  const [consentLoaded, setConsentLoaded] = useState(false);
  const [consentVersions, setConsentVersions] = useState({terms_version:"", privacy_version:""});
  const [consentBusy, setConsentBusy] = useState(false);
  const [privacyExports,setPrivacyExports]=useState<{id:string;status:string;error:string|null;created_at:string;expires_at:string|null;download_url:string|null}[]>([]);
  const [privacyExportBusy,setPrivacyExportBusy]=useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [activePage, setActivePage] = useState<"workspace" | "admin" | "billing" | "settings" | "upcoming" | "library" | "organizations" | "data-processing" | "tools">("workspace");
  const [legalPage, setLegalPage] = useState<"terms" | "privacy" | null>(null);
  const [isRegistering, setIsRegistering] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [hasAcceptedTerms, setHasAcceptedTerms] = useState(false);
  const [adminBootstrapAvailable, setAdminBootstrapAvailable] = useState(false);
  const [adminBootstrapConfigured, setAdminBootstrapConfigured] = useState(false);
  const [adminAccountExists, setAdminAccountExists] = useState(false);
  const [adminBootstrapStatus, setAdminBootstrapStatus] = useState<"loading" | "ready" | "error">("loading");
  const [showAdminMenu, setShowAdminMenu] = useState(false);
  const [isAdminLogin, setIsAdminLogin] = useState(false);
  const [showAdminBootstrap, setShowAdminBootstrap] = useState(false);
  const [adminSetupCode, setAdminSetupCode] = useState("");

  useEffect(() => {
    if (token) return;
    let cancelled = false;
    void request<{ available: boolean; configured: boolean; has_admin: boolean }>("/auth/admin/bootstrap/status", "")
      .then((status) => {
        if (cancelled) return;
        setAdminBootstrapAvailable(status.available);
        setAdminBootstrapConfigured(status.configured);
        setAdminAccountExists(status.has_admin);
        setAdminBootstrapStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setAdminBootstrapAvailable(false);
        setAdminBootstrapStatus("error");
      });
    return () => { cancelled = true; };
  }, [token]);

  // Knowledge bases and documents in the selected workspace.
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [organizations, setOrganizations] = useState<{ id: string; name: string; type: string; role: string }[]>([]);
  const [activeOrganizationId, setActiveOrganizationId] = useState("");
  const [billingOrganizationId, setBillingOrganizationId] = useState<string | null>(null);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [expandedKnowledgeBaseIds, setExpandedKnowledgeBaseIds] = useState<Set<string>>(() => new Set());
  const [expandedDocumentIds, setExpandedDocumentIds] = useState<Set<string>>(() => new Set());
  const [folderDocuments, setFolderDocuments] = useState<Record<string, { items: DocumentRecord[]; loading: boolean; error: string }>>({});
  const [isUploadPanelOpen, setIsUploadPanelOpen] = useState(false);
  const [uploadLimitMb, setUploadLimitMb] = useState(10);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const savedWidth = Number(localStorage.getItem("documind_sidebar_width"));
    return Number.isFinite(savedWidth) && savedWidth >= 240 && savedWidth <= 560 ? savedWidth : 285;
  });
  const [openItemMenuId, setOpenItemMenuId] = useState<string | null>(null);
  const [isHelpPanelOpen, setIsHelpPanelOpen] = useState(false);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");
  const [newKnowledgeBaseSensitive, setNewKnowledgeBaseSensitive] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<ConversationRecord[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    localStorage.removeItem('documind_token');
    let cancelled = false;
    void request<UserProfile>("/auth/me")
      .then((profile) => {
        if (cancelled) return;
        setToken("cookie-session");
        setUserProfile(profile);
        setActivePage(profile.is_superuser ? "admin" : "workspace");
        return request<{required:boolean;terms_version:string;privacy_version:string}>("/privacy/consent/status")
          .then((status) => { if (!cancelled) { setConsentRequired(status.required); setConsentVersions(status); setConsentLoaded(true); } });
      })
      .catch(() => { if (!cancelled) setToken(""); })
      .finally(() => { if (!cancelled) setSessionChecking(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(()=>{
    if(!token || !consentLoaded || consentRequired)return;
    let cancelled=false;
    void request<{items:typeof privacyExports}>('/privacy/exports',token).then(result=>{if(!cancelled)setPrivacyExports(result.items);}).catch(()=>{});
    return()=>{cancelled=true;};
  },[token, consentLoaded, consentRequired]);

  // Chat messages and current conversation.
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatScope, setChatScope] = useState<"document" | "folder" | "library" | "folder_library">("folder");
  const [libraryCollectionId, setLibraryCollectionId] = useState<string | null>(null);
  const [conversationVisibility, setConversationVisibility] = useState<"private" | "shared">("private");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const questionInputRef = useRef<HTMLInputElement>(null);

  // Shared feedback for network operations.
  const [isBusy, setIsBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("Processing...");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState | null>(null);

  useEffect(() => { localStorage.setItem("documind_sidebar_width", String(sidebarWidth)); }, [sidebarWidth]);

  /** Load the current user's knowledge bases from the API. */
  async function refreshKnowledgeBases() {
    if (!token || !consentLoaded || consentRequired) return;

    try {
      const response = await request<KnowledgeBaseListResponse>(
        "/knowledge-bases",
        token
      );

      setKnowledgeBases(response.items);
      const visible = response.items.filter((knowledgeBase) => (knowledgeBase.organization_id ?? "") === activeOrganizationId);
      setSelectedKnowledgeBaseId((previousId) => {
        const previousStillExists = visible.some(
          (knowledgeBase) => knowledgeBase.id === previousId
        );
        return previousStillExists ? previousId : visible[0]?.id ?? "";
      });
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function refreshOrganizations() {
    if (!token) { setOrganizations([]); setActiveOrganizationId(""); return; }
    if (!consentLoaded || consentRequired) { setOrganizations([]); setActiveOrganizationId(""); return; }
    try {
      const result = await request<{ id: string; name: string; type: string; role: string }[]>("/organizations", token);
      setOrganizations(result);
      setActiveOrganizationId((current) => result.some((org) => org.id === current) ? current : "");
    } catch (error) { setErrorMessage(getErrorMessage(error)); }
  }

  async function recordOrganizationExport(resourceType: string, resourceId: string, knowledgeBaseId: string | null) {
    const folder = knowledgeBases.find((item) => item.id === knowledgeBaseId);
    if (folder?.organization_id) await request(`/organizations/${folder.organization_id}/exports`, token, { method: "POST", body: JSON.stringify({ resource_type: resourceType, resource_id: resourceId }) });
  }

  const inviteHandled = useRef(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const inviteToken = params.get("organization_invite");
    if (!inviteToken) { inviteHandled.current = false; return; }
    if (!token) { setSuccessMessage("You have an organization invitation. Sign in or create an account with the invited email to accept it."); return; }
    if (!consentLoaded || consentRequired) return;
    if (inviteHandled.current) return;
    inviteHandled.current = true;
    void request<{ organization_id: string; message: string }>(`/organizations/invites/${encodeURIComponent(inviteToken)}/accept`, token, { method: "POST" })
      .then((result) => { setSuccessMessage(result.message); setActiveOrganizationId(result.organization_id); setActivePage("workspace"); void refreshOrganizations(); window.history.replaceState({}, "", window.location.pathname); })
      .catch((error) => setErrorMessage(getErrorMessage(error)));
  }, [token, consentLoaded, consentRequired]);

  /** Load saved conversations for the history panel. */
  async function refreshConversationHistory() {
    if (!token || !consentLoaded || consentRequired) {
      setConversationHistory([]);
      setHistoryLoaded(false);
      return;
    }
    setIsHistoryLoading(true);
    try {
      const history = await request<ConversationRecord[]>("/conversations", token);
      setConversationHistory(history);
      setHistoryLoaded(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsHistoryLoading(false);
    }
  }

  /** Load documents belonging to the currently selected knowledge base. */
  async function refreshDocuments() {
    if (!token || !consentLoaded || consentRequired || !selectedKnowledgeBaseId) {
      setDocuments([]);
      return;
    }

    setDocuments([]);
    setFolderDocuments((previous) => ({
      ...previous,
      [selectedKnowledgeBaseId]: { items: previous[selectedKnowledgeBaseId]?.items ?? [], loading: true, error: "" },
    }));
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
      setFolderDocuments((previous) => ({
        ...previous,
        [selectedKnowledgeBaseId]: { items: previous[selectedKnowledgeBaseId]?.items ?? [], loading: false, error: getErrorMessage(error) },
      }));
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

    // Chat history is only needed after opening a folder. Keep the initial
    // workspace render independent of this larger, optional request.
    if (!historyLoaded && !isHistoryLoading) void refreshConversationHistory();

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
    setConversationHistory([]);
    setHistoryLoaded(false);
  }, [token, activeOrganizationId, consentLoaded, consentRequired]);

  useEffect(() => { void refreshOrganizations(); }, [token, consentLoaded, consentRequired]);

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
  }, [token, selectedKnowledgeBaseId, consentLoaded, consentRequired]);

  async function openUploadPanel() {
    setUploadError("");
    setUploadSuccess("");
    setIsUploadPanelOpen(true);
    if (!selectedKnowledgeBaseId) return;
    try {
      const config = await request<{ max_upload_mb: number }>(`/knowledge-bases/${selectedKnowledgeBaseId}/documents/upload-config`, token);
      setUploadLimitMb(config.max_upload_mb);
    } catch (error) {
      setUploadError(getErrorMessage(error));
    }
  }

  // Uploads are indexed in the background; poll until the saved status changes.
  const hasProcessingDocuments = documents.some(
    (document) => document.status === "pending" || document.status === "processing"
  );
  useEffect(() => {
    if (!token || !consentLoaded || consentRequired || !selectedKnowledgeBaseId || !hasProcessingDocuments) return;
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
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [token, selectedKnowledgeBaseId, hasProcessingDocuments, consentLoaded, consentRequired]);

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

  useEffect(() => {
    if (!deleteDialog || deleteDialog.deleting) return;
    function cancelOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setDeleteDialog(null);
    }
    window.addEventListener("keydown", cancelOnEscape);
    return () => window.removeEventListener("keydown", cancelOnEscape);
  }, [deleteDialog]);

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
        : { email: email.trim(), password, admin_login: isAdminLogin, totp_code: totpCode || undefined };

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
      if (isAdminLogin && !response.user.is_superuser) {
        setErrorMessage("This account does not have administrator access. Sign in with an administrator account.");
        setPassword("");
        return;
      }
      setToken("cookie-session");
      setUserProfile(response.user);
      setActivePage(response.user.is_superuser ? "admin" : "workspace");
      setPassword("");
      setTotpCode("");
      const consent = await request<{required:boolean;terms_version:string;privacy_version:string}>("/privacy/consent/status");
      setConsentRequired(consent.required); setConsentVersions(consent);
      setConsentLoaded(true);
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
      setAdminBootstrapAvailable(false);
      setToken("cookie-session");
      setUserProfile(response.user);
      setActivePage("admin");
      setPassword("");
      setAdminSetupCode("");
      setConsentRequired(false);
      setConsentLoaded(true);
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
        body: JSON.stringify({ credential, mode, accept_terms: acceptedTerms, totp_code:totpCode || undefined }),
      });
      setToken("cookie-session");
      setUserProfile(response.user);
      setActivePage(response.user.is_superuser ? "admin" : "workspace");
      setPassword("");
      setTotpCode("");
      const consent = await request<{required:boolean;terms_version:string;privacy_version:string}>("/privacy/consent/status");
      setConsentRequired(consent.required); setConsentVersions(consent);
      setConsentLoaded(true);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  /** Clear all user-specific data when signing out. */
  async function handleLogout() {
    try { await request("/auth/logout", token, {method:"POST"}); } catch { /* Clear local state even if the server is unreachable. */ }
    setToken("");
    setConsentRequired(false);
    setConsentLoaded(false);
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

  async function acceptCurrentNotices() {
    setConsentBusy(true); setErrorMessage("");
    try {
      await request('/privacy/consent', token, {method:'POST', body:JSON.stringify({accept_terms:true,accept_privacy:true})});
      setConsentRequired(false); setSuccessMessage('Current Terms and Privacy Notice accepted.');
    } catch (error) { setErrorMessage(getErrorMessage(error)); }
    finally { setConsentBusy(false); }
  }

  async function refreshPrivacyExports(){
    const result=await request<{items:typeof privacyExports}>('/privacy/exports',token);
    setPrivacyExports(result.items);
  }
  async function requestPersonalExport(){
    setPrivacyExportBusy(true);setErrorMessage('');setSuccessMessage('');
    try{const created=await request<{id:string;message:string}>('/privacy/exports',token,{method:'POST'});setSuccessMessage(created.message);await refreshPrivacyExports();}
    catch(error){setErrorMessage(getErrorMessage(error));}finally{setPrivacyExportBusy(false);}
  }
  async function requestAccountDeletion(){
    const confirmation=window.prompt('This queues deletion of your personal folders, original files, extracted text and vectors, conversations, reminders, WhatsApp link, sign-in factors, and account profile. Required audit references remain. Type DELETE MY ACCOUNT to continue.');
    if(confirmation!=='DELETE MY ACCOUNT')return;
    try{await request('/privacy/account',token,{method:'DELETE',body:JSON.stringify({confirmation})});setSuccessMessage('Your account deletion request is queued. Your personal data will be removed by the background worker.');await request('/auth/logout',token,{method:'POST'});setToken('');setUserProfile(null);}
    catch(error){setErrorMessage(getErrorMessage(error));}
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
    setChatScope(conversation.scope_type ?? (conversation.document_id ? "document" : "folder"));
    setLibraryCollectionId(conversation.library_collection_id ?? null);
    setConversationVisibility(conversation.visibility ?? "private");
    if (conversation.document_id && conversation.knowledge_base_id) {
      setExpandedKnowledgeBaseIds((previous) => new Set(previous).add(conversation.knowledge_base_id!));
      setExpandedDocumentIds((previous) => new Set(previous).add(conversation.document_id!));
    }
    try {
      const saved = await request<SavedChatMessage[]>(
        `/conversations/${conversation.id}/messages`,
        token,
      );
      setMessages(saved.map(({ id, role, content, sources, actor_name, metadata, feedback_status }) => ({
        message_id: id,
        role: role === "assistant" ? "assistant" : "user",
        content,
        sources,
        actor_name,
        confidence_label: metadata?.confidence_label,
        confidence_score: metadata?.confidence_score,
        answer_language: metadata?.answer_language,
        feedback_status,
      })));
      setConversationId(conversation.id);
      setIsMobileSidebarOpen(false);
      if (conversation.knowledge_base_id) await recordOrganizationExport("conversation", conversation.id, conversation.knowledge_base_id);
      await downloadConversationPdf(conversation.title, saved);
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
      if (conversation.knowledge_base_id) await recordOrganizationExport("conversation", conversation.id, conversation.knowledge_base_id);
      await downloadConversationPdf(conversation.title, saved);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function changeConversationVisibility(next: "private" | "shared") {
    if (conversationId) {
      try {
        const result = await request<ConversationRecord>(`/conversations/${conversationId}`, token, {
          method: "PATCH",
          body: JSON.stringify({ visibility: next }),
        });
        setConversationVisibility(result.visibility ?? next);
        await refreshConversationHistory();
      } catch (error) { setErrorMessage(getErrorMessage(error)); }
      return;
    }
    setConversationVisibility(next);
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
    if (knowledgeBaseId !== selectedKnowledgeBaseId || selectedDocumentId || chatScope !== "folder") {
      clearCurrentConversation();
    }
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setSelectedDocumentId("");
    setChatScope("folder");
    setIsMobileSidebarOpen(false);
  }

  function handleSelectDocument(knowledgeBaseId: string, documentId: string) {
    if (["folder", "folder_library"].includes(chatScope) && selectedKnowledgeBaseId) {
      const folderName = knowledgeBases.find((folder) => folder.id === selectedKnowledgeBaseId)?.name ?? "this folder";
      const confirmed = window.confirm(`Switch to This document? Your current chat across ${folderName} will remain saved in the folder's chat history.`);
      if (!confirmed) return;
    }
    if (knowledgeBaseId !== selectedKnowledgeBaseId || documentId !== selectedDocumentId || chatScope !== "document") {
      clearCurrentConversation();
    }
    setSelectedKnowledgeBaseId(knowledgeBaseId);
    setSelectedDocumentId(documentId);
    setChatScope("document");
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
        body: JSON.stringify({ name: newKnowledgeBaseName.trim(), organization_id: activeOrganizationId || null, is_sensitive:newKnowledgeBaseSensitive }),
      });

      setNewKnowledgeBaseName("");
      setNewKnowledgeBaseSensitive(false);
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
    const selectedFiles = Array.from(event.target.files ?? []);
    if (!selectedFiles.length || !selectedKnowledgeBaseId) return;

    setIsBusy(true);
    setBusyMessage(`Preparing ${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"}...`);
    setUploadError("");
    setUploadSuccess("");
    const mergeablePhotos = selectedFiles.filter((file) => /\.(jpe?g|png)$/i.test(file.name));
    let combinedPhotos: File | null = null;
    if (mergeablePhotos.length > 1) {
      try {
        combinedPhotos = await import("./photoPdf").then(({ combinePhotosIntoPdf }) => combinePhotosIntoPdf(mergeablePhotos));
      } catch (error) {
        setUploadError(`${getErrorMessage(error)} Select JPG or PNG photos and try again.`);
        setIsBusy(false);
        event.target.value = "";
        return;
      }
    }
    const files: File[] = [];
    let photosInserted = false;
    for (const file of selectedFiles) {
      if (combinedPhotos && /\.(jpe?g|png)$/i.test(file.name)) {
        if (!photosInserted) files.push(combinedPhotos);
        photosInserted = true;
      } else files.push(file);
    }

    setBusyMessage(`Preparing ${files.length} file${files.length === 1 ? "" : "s"}...`);

    let uploaded = 0;
    const failures: string[] = [];
    try {
      for (const [index, file] of files.entries()) {
        setBusyMessage(`Uploading file ${index + 1} of ${files.length}: ${file.name}`);
        if (!/\.(pdf|txt|docx|jpe?g|png|heic)$/i.test(file.name)) {
          failures.push(`${file.name}: Invalid file type. Please choose a PDF, TXT, DOCX, JPG, PNG, or HEIC file.`);
          continue;
        }
        if (file.size > uploadLimitMb * 1_000_000) {
          failures.push(`${file.name}: This file is too large. The maximum size is ${uploadLimitMb} MB.`);
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
            failures.push(`${file.name}: ${friendlyProcessingError(response.document.processing_error)}`);
          }
        } catch (error) {
          failures.push(`${file.name}: ${friendlyUploadError(error)}`);
        }
      }
      await refreshDocuments();
      if (failures.length) {
        const shownFailures = failures.slice(0, 3).join("; ");
        const remaining = failures.length > 3 ? `; and ${failures.length - 3} more` : "";
        setUploadError(uploaded ? `${uploaded} of ${files.length} files uploaded. ${shownFailures}${remaining}` : `${shownFailures}${remaining}`);
      } else if (uploaded) {
        setUploadSuccess(`${uploaded} document${uploaded === 1 ? " was" : "s were"} uploaded. Processing continues in the background.`);
      }
    } catch (error) {
      setUploadError(friendlyUploadError(error));
    } finally {
      setIsBusy(false);
      event.target.value = "";
    }
  }

  function deleteTargetKey(target: DeleteTarget) {
    return target.kind === "document" ? `document:${target.document.id}` : `folder:${target.knowledgeBase.id}`;
  }

  /** Fetch the current history before showing any destructive action. */
  async function openDeleteConfirmation(target: DeleteTarget, retry = false) {
    if (deleteDialog && !retry) return;
    if (isBusy) {
      const message = "Please wait for the current action to finish before deleting a file or folder.";
      if (isUploadPanelOpen) setUploadError(message);
      else setErrorMessage(message);
      return;
    }
    const targetKey = deleteTargetKey(target);
    setDeleteDialog({ target, conversations: null, documentCount: null, loading: true, deleting: false, error: "" });
    try {
      const savedConversations = await request<ConversationRecord[]>("/conversations", token);
      let conversations: ConversationRecord[];
      let documentCount: number | null = null;
      if (target.kind === "document") {
        conversations = savedConversations.filter((conversation) => conversation.document_id === target.document.id);
      } else {
        const listing = await request<DocumentListResponse>(`/knowledge-bases/${target.knowledgeBase.id}/documents`, token);
        conversations = savedConversations.filter((conversation) => conversation.knowledge_base_id === target.knowledgeBase.id);
        documentCount = listing.total;
      }
      setDeleteDialog((current) => current && deleteTargetKey(current.target) === targetKey
        ? { ...current, conversations, documentCount, loading: false }
        : current);
    } catch (error) {
      setDeleteDialog((current) => current && deleteTargetKey(current.target) === targetKey
        ? { ...current, loading: false, error: getErrorMessage(error) }
        : current);
    }
  }

  function handleDeleteDocument(knowledgeBaseId: string, document: DocumentRecord) {
    void openDeleteConfirmation({ kind: "document", knowledgeBaseId, document });
  }

  async function confirmDeleteWithHistory(downloadHistory: boolean) {
    const pending = deleteDialog;
    if (!pending || pending.loading || pending.deleting || pending.error || !pending.conversations) return;
    const targetKey = deleteTargetKey(pending.target);
    setDeleteDialog({ ...pending, deleting: true, error: "" });
    let historyDownloaded = false;
    try {
      if (downloadHistory && pending.conversations.length) {
        const conversationsWithMessages = await Promise.all(pending.conversations.map(async (conversation) => {
          const messages = await request<SavedChatMessage[]>(`/conversations/${conversation.id}/messages`, token);
          if (conversation.knowledge_base_id) await recordOrganizationExport("conversation", conversation.id, conversation.knowledge_base_id);
          return { title: conversation.title || "Saved conversation", messages };
        }));
        const title = pending.target.kind === "document"
          ? pending.target.document.original_filename
          : pending.target.knowledgeBase.name;
        await downloadConversationsPdf(title, conversationsWithMessages);
        historyDownloaded = true;
      }

      if (pending.target.kind === "document") {
        await request<void>(
          `/knowledge-bases/${pending.target.knowledgeBaseId}/documents/${pending.target.document.id}`,
          token,
          { method: "DELETE" },
        );
      } else {
        await request<void>(`/knowledge-bases/${pending.target.knowledgeBase.id}`, token, { method: "DELETE" });
      }

      setDeleteDialog(null);
      if (pending.target.kind === "document") {
        const knowledgeBaseId = pending.target.knowledgeBaseId;
        if (selectedDocumentId === pending.target.document.id) {
          setSelectedDocumentId(""); setConversationId(null); setMessages([]);
        }
        void refreshDocuments();
        void refreshConversationHistory();
        try {
          const refreshed = await request<DocumentListResponse>(`/knowledge-bases/${knowledgeBaseId}/documents`, token);
          setFolderDocuments((previous) => ({ ...previous, [knowledgeBaseId]: { items: refreshed.items, loading: false, error: "" } }));
        } catch (error) {
          setErrorMessage(getErrorMessage(error));
        }
      } else {
        const folderId = pending.target.knowledgeBase.id;
        if (selectedKnowledgeBaseId === folderId) {
          setSelectedKnowledgeBaseId(""); setSelectedDocumentId(""); setConversationId(null); setMessages([]);
        }
        setFolderDocuments((previous) => {
          const next = { ...previous };
          delete next[folderId];
          return next;
        });
        void Promise.all([refreshKnowledgeBases(), refreshConversationHistory()]);
      }
    } catch (error) {
      const message = historyDownloaded
        ? `The PDF was downloaded, but the item could not be deleted. Your files and chats are still saved. ${getErrorMessage(error)}`
        : getErrorMessage(error);
      setDeleteDialog((current) => current && deleteTargetKey(current.target) === targetKey
        ? { ...current, deleting: false, error: message }
        : current);
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
    void openDeleteConfirmation({ kind: "folder", knowledgeBase });
  }

  function promptRename(label: string, currentName: string, save: (name: string) => void) {
    const value = window.prompt(`Rename ${label}`, currentName);
    if (value?.trim() && value.trim() !== currentName) save(value.trim());
  }

  /** Send a question and display the AI answer with its document sources. */
  async function handleSendQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const readyFolderDocuments = documents.filter((document) => document.status === "ready");
    if (["folder", "folder_library"].includes(chatScope) && !selectedKnowledgeBaseId) {
      setErrorMessage("Please select a folder before starting a chat.");
      return;
    }
    if (chatScope === "folder" && readyFolderDocuments.length === 0) {
      setErrorMessage("This folder has no ready documents yet. Upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file and wait until it is ready before chatting.");
      return;
    }
    if (chatScope === "document" && !selectedDocumentId) {
      if (!question.trim() || isBusy) return;
      const firstName = userProfile?.full_name.trim().split(/\s+/)[0] || "there";
      const whereToFindFiles = window.matchMedia("(max-width: 700px)").matches
        ? "Tap the folder button at the top of the screen to open the file list."
        : "Your files are in the left sidebar.";
      setMessages((previous) => [...previous, {
        role: "assistant",
        content: `# Choose a file first\n\nHello ${firstName}, please choose a file or document that you want to ask about. ${whereToFindFiles} If there is no folder yet, create one in the sidebar first, then use **Add files** to upload a document. After selecting a file, ask for a summary, an explanation, or anything else about it.`,
      }]);
      setQuestion("");
      setErrorMessage("");
      return;
    }
    if (!question.trim() || isBusy) return;
    if (["folder", "folder_library"].includes(chatScope) && !selectedKnowledgeBaseId) { setErrorMessage("Please select a folder before starting a chat."); return; }

    const submittedQuestion = question.trim();
    setQuestion("");
    setMessages((previous) => [
      ...previous,
      { role: "user", content: submittedQuestion, actor_name: userProfile?.full_name },
    ]);
    setIsBusy(true);
    setBusyMessage("Searching your documents and preparing an answer...");
    setErrorMessage("");

    try {
      const response = await request<ChatResponse>("/chat", token, {
        method: "POST",
        body: JSON.stringify({
          scope_type: chatScope,
          scope_id: chatScope === "document" ? selectedDocumentId : chatScope === "library" ? libraryCollectionId : selectedKnowledgeBaseId,
          library_collection_id: chatScope === "library" ? libraryCollectionId : chatScope === "folder_library" ? libraryCollectionId : null,
          question: submittedQuestion,
          conversation_id: conversationId,
          visibility: conversationVisibility,
        }),
      });

      setConversationId(response.conversation_id);
      setMessages((previous) => [
        ...previous,
        {
          message_id: response.assistant_message_id,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          confidence_label: response.confidence_label,
          confidence_score: response.confidence_score,
          answer_language: response.answer_language,
        },
      ]);
      void refreshConversationHistory();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBusy(false);
    }
  }

  async function submitAnswerFeedback(message: ChatMessage, rating: "up" | "down" | "report") {
    if (!message.message_id || !token) return;
    let comment: string | undefined;
    if (rating === "report") {
      comment = window.prompt("What seems wrong with this answer? (Optional)")?.trim() || undefined;
      if (comment === undefined && window.confirm("Send the report without a comment?")) {
        // Continue without a comment.
      } else if (comment === undefined) return;
    }
    try {
      await request(`/messages/${message.message_id}/feedback`, token, { method: "POST", body: JSON.stringify({ rating, comment }) });
      setMessages((previous) => previous.map((item) => item.message_id === message.message_id ? { ...item, feedback_status: rating } : item));
    } catch (error) { setErrorMessage(getErrorMessage(error)); }
  }

  if (legalPage) {
    return <Suspense fallback={<div className="app-loading" role="status">Loading…</div>}><TermsPrivacy document={legalPage} onOpen={setLegalPage} onBack={() => setLegalPage(null)} /></Suspense>;
  }

  if (sessionChecking) return <div className="app-loading" role="status">Checking your secure session…</div>;

  if (activePage === 'data-processing' && token) return <Suspense fallback={<div className="app-loading" role="status">Loading data processing details…</div>}><DataProcessingPage token={token} onBack={() => setActivePage(consentRequired ? 'workspace' : 'settings')} /></Suspense>;

  if (consentRequired && token) return (
    <main className="privacy-consent-screen">
      <section className="privacy-consent-card">
        <ShieldCheck size={30}/><h1>Please review the updated notices</h1>
        <p>To continue using DocuMind AI, review and accept the current Terms and Privacy Notice. Your acceptance is saved with the version and time.</p>
        <p><strong>Terms version:</strong> {consentVersions.terms_version} · <strong>Privacy version:</strong> {consentVersions.privacy_version}</p>
        <div className="settings-links"><button type="button" onClick={() => openLegalPage('terms')}>Read Terms</button><button type="button" onClick={() => openLegalPage('privacy')}>Read Privacy Notice</button><button type="button" onClick={() => setActivePage('data-processing')}>See data processing details</button></div>
        {errorMessage&&<p className="error" role="alert">{errorMessage}</p>}
        <button className="admin-primary" type="button" disabled={consentBusy} onClick={() => void acceptCurrentNotices()}>{consentBusy?'Saving acceptance…':'Accept current notices'}</button>
        <button className="auth-toggle" type="button" onClick={() => void handleLogout()}>Sign out</button>
      </section>
    </main>
  );

  // Before login, show only the authentication form.
  if (!token) {
    return (
      <div className="auth-wrap">
        <div className="auth-admin-entry">
          <button className="auth-admin-dot" type="button" aria-label="Open account tools" aria-expanded={showAdminMenu} title="Account tools" onClick={() => setShowAdminMenu((open) => !open)}><span /></button>
          {showAdminMenu && (
            <div className="auth-admin-menu" role="menu" aria-label="Account tools">
          <button type="button" role="menuitem" onClick={() => { setIsRegistering(false); setIsAdminLogin(true); setShowAdminBootstrap(false); setShowAdminMenu(false); setHasAcceptedTerms(false); setErrorMessage(""); setSuccessMessage(""); setPassword(""); }}>Admin sign in</button>
              {adminBootstrapAvailable
                ? <button type="button" role="menuitem" onClick={() => { setIsAdminLogin(false); setShowAdminBootstrap(true); setShowAdminMenu(false); setHasAcceptedTerms(false); setFullName(""); setEmail(""); setPassword(""); setAdminSetupCode(""); setErrorMessage(""); }}>Set up first administrator</button>
                : <p>{adminBootstrapStatus === "loading"
                  ? "Checking administrator setup…"
                  : adminBootstrapStatus === "error"
                    ? "Could not check setup status. Admin sign-in is still available."
                    : !adminBootstrapConfigured
                      ? "To set up the first admin, configure ADMIN_BOOTSTRAP_CODE on the backend."
                      : adminAccountExists
                        ? "An administrator is already set up. Sign in with that account."
                        : "First-time setup is unavailable."}</p>}
            </div>
          )}
        </div>
        <div className="auth-content">
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
        ) : <form className={`auth-card ${isRegistering ? "auth-card-register" : ""}`} autoComplete="off" noValidate onSubmit={handleAuthentication}>
          <div className="brand">
            <BookOpen /> DocuMind <span>AI</span>
          </div>

          <h1>{isRegistering ? "Create your account" : isAdminLogin ? "Administrator sign in" : "Welcome back"}</h1>
          <p>{isAdminLogin ? "Sign in with the email and password for your administrator account." : "Turn your documents into trusted answers."}</p>

          {isRegistering && (
            <div className="auth-terms auth-google-terms">
              <label>
                <input type="checkbox" required checked={hasAcceptedTerms} onChange={(event) => setHasAcceptedTerms(event.target.checked)} />
                <span>I agree to the</span>
              </label>
              <button type="button" onClick={() => openLegalPage("terms")}>Terms of Service</button>
              <span>and</span>
              <button type="button" onClick={() => openLegalPage("privacy")}>Privacy Notice</button>
              <span>.</span>
            </div>
          )}

          {!isAdminLogin && <Suspense fallback={<div className="google-options-loading" role="status">Loading sign-in options…</div>}><GoogleSignIn
            mode={isRegistering ? "register" : "login"}
            acceptedTerms={hasAcceptedTerms}
            onCredential={(credential, mode, accepted) => void handleGoogleSignIn(credential, mode, accepted)}
          /></Suspense>}

          {isRegistering ? (
            <div className="auth-register-fields">
              <label>Full name<input required minLength={2} maxLength={150} autoComplete="off" placeholder="Your full name" value={fullName} onChange={(event) => setFullName(event.target.value)} /></label>
              <label>Email address<input type="email" required autoComplete="off" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
              <label>Password<input type="password" required minLength={8} maxLength={128} autoComplete="new-password" placeholder="At least 8 characters" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
              <label>Confirm password<input type="password" required minLength={8} maxLength={128} autoComplete="new-password" placeholder="Enter your password again" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
              {confirmPassword && password !== confirmPassword && (
                <p className="error password-mismatch" role="status">Passwords do not match. Please check and try again.</p>
              )}
            </div>
          ) : (
            <>
              <input type="email" required autoComplete="off" placeholder="Email address" value={email} onChange={(event) => setEmail(event.target.value)} />
              <input type="password" required autoComplete="current-password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} />
              <input type="text" inputMode="numeric" autoComplete="one-time-code" placeholder="Authenticator code (admins only, if enabled)" value={totpCode} onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, '').slice(0,6))} />
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
                setIsAdminLogin(false);
                setConfirmPassword("");
                setHasAcceptedTerms(false);
                setErrorMessage("");
                setSuccessMessage("");
              }}
            >
                {isRegistering
                ? "Already have an account? Sign in"
                : isAdminLogin ? "Back to regular sign in" : "New here? Create an account"}
            </button>
          </p>
        </form>}
        <nav className="auth-legal-nav" aria-label="Legal information">
          <button type="button" onClick={() => openLegalPage("terms")}>Terms of service</button>
          <span aria-hidden="true">·</span>
          <button type="button" onClick={() => openLegalPage("privacy")}>Privacy notice</button>
        </nav>
        </div>
      </div>
    );
  }

  if (activePage === "library") return <Suspense fallback={<div className="app-loading" role="status">Loading library…</div>}><LibraryPage token={token} onBack={() => setActivePage("workspace")} onAsk={(collectionId) => { setLibraryCollectionId(collectionId); setSelectedKnowledgeBaseId(""); setSelectedDocumentId(""); setChatScope("library"); clearCurrentConversation(); setActivePage("workspace"); }} /></Suspense>;
  if (activePage === "settings") return (
    <main className="settings-wrap">
      <section className="settings-card">
        <button className="legal-back" type="button" onClick={() => setActivePage("workspace")}><ChevronLeft size={17} /> Back to workspace</button>
        <div className="settings-heading"><SettingsIcon size={23} /><div><h1>Account settings</h1><p>Manage your session and find service information.</p></div></div>
        <section className="settings-detail"><h2>Signed-in account</h2><p><strong>Name</strong><span>{userProfile?.full_name ?? "Loading account…"}</span></p><p><strong>Email</strong><span>{userProfile?.email ?? ""}</span></p></section>
        <Suspense fallback={<section className="settings-detail" role="status">Loading answer language settings…</section>}><AnswerLanguageSettings token={token} /></Suspense>
        <section className="settings-detail"><h2>Plan and billing</h2><p>Review your plan or subscription payment status.</p><button type="button" onClick={() => { setBillingOrganizationId(null); setActivePage("billing"); }}><CreditCard size={16} /> Open plan &amp; billing</button></section>
        <Suspense fallback={<section className="settings-detail" role="status">Loading WhatsApp settings…</section>}><WhatsAppSettings token={token} /></Suspense>
        <section className="settings-detail"><h2>Legal and privacy</h2><div className="settings-links"><button type="button" onClick={() => openLegalPage("terms")}>Read Terms of service</button><button type="button" onClick={() => openLegalPage("privacy")}>Read Privacy notice</button></div></section>
        <section className="settings-detail"><h2>Data processing</h2><p>Review which service providers process information and what each provider is used for.</p><button type="button" onClick={() => setActivePage("data-processing")}>Open data processing page</button></section>
        <section className="settings-detail privacy-export-card"><h2>Download all my data</h2><p>Prepare a ZIP containing your personal folder metadata, original files, conversation JSON and PDF exports. Organization-owned data is excluded.</p><button className="admin-secondary" type="button" disabled={privacyExportBusy} onClick={()=>void requestPersonalExport()}>{privacyExportBusy?'Requesting export…':'Request my data ZIP'}</button><button type="button" onClick={()=>void refreshPrivacyExports()}>Refresh export status</button><div className="privacy-export-list">{privacyExports.map(item=><p key={item.id}><strong>{item.status}</strong> · {new Date(item.created_at).toLocaleString()} {item.error&&<span className="error"> · {item.error}</span>}{item.download_url&&<a href={item.download_url} rel="noreferrer">Download ZIP</a>}</p>)}</div></section>
        <section className="settings-detail privacy-danger-zone"><h2>Delete my account and personal data</h2><p>This queues removal of your account, personal folders, original files, vectors, conversations, reminders, and linked WhatsApp account. Transfer or delete organizations you own first. Permanent audit records retain minimal identifiers as evidence of the deletion.</p><button className="danger-button" type="button" onClick={()=>void requestAccountDeletion()}>Request account deletion</button>{errorMessage&&<p className="error" role="alert">{errorMessage}</p>}{successMessage&&<p role="status">{successMessage}</p>}</section>
        <button className="settings-signout" type="button" onClick={handleLogout}><LogOut size={17} /> Sign out of this account</button>
      </section>
    </main>
  );

  if (activePage === "admin") return <Suspense fallback={<div className="app-loading" role="status">Loading admin tools…</div>}><AdminDashboard token={token} onBack={() => setActivePage("workspace")} /></Suspense>;
  if (activePage === "organizations") return <Suspense fallback={<div className="app-loading" role="status">Loading organizations…</div>}><OrganizationsPage token={token} selectedId={activeOrganizationId} onSelect={(id) => { setActiveOrganizationId(id); void refreshOrganizations(); }} onBack={() => { void refreshOrganizations(); setActivePage("workspace"); }} onBilling={(id) => { setBillingOrganizationId(id); setActivePage("billing"); }} /></Suspense>;
  if (activePage === "billing") return <Suspense fallback={<div className="app-loading" role="status">Loading billing…</div>}><BillingPage token={token} organizationId={billingOrganizationId} onBack={() => setActivePage(billingOrganizationId ? "organizations" : "workspace")} /></Suspense>;
  if (activePage === "upcoming") return <Suspense fallback={<div className="app-loading" role="status">Loading important dates…</div>}><ImportantDates token={token} upcoming onBack={() => setActivePage("workspace")} /></Suspense>;
  if (activePage === "tools") return <Suspense fallback={<div className="app-loading" role="status">Loading business tools…</div>}><BusinessToolsPage token={token} isAdmin={!!userProfile?.is_superuser} onBack={() => setActivePage("workspace")} /></Suspense>;

  const visibleKnowledgeBases = knowledgeBases.filter((knowledgeBase) => (knowledgeBase.organization_id ?? "") === activeOrganizationId);
  const selectedKnowledgeBase = visibleKnowledgeBases.find(
    (knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId
  );
  const activeOrganization = organizations.find((organization) => organization.id === activeOrganizationId);
  const canManageActiveOrg = !activeOrganization || ["owner", "admin"].includes(activeOrganization.role);
  const canUploadToActiveOrg = !activeOrganization || activeOrganization.role !== "viewer";
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId);
  const readyFolderDocuments = documents.filter((document) => document.status === "ready");
  const selectedFolderDocumentsLoading = !!selectedKnowledgeBaseId && !!folderDocuments[selectedKnowledgeBaseId]?.loading;
  const hasValidChatScope = chatScope === "library" ? true : chatScope === "folder_library" ? !!selectedKnowledgeBaseId
    : chatScope === "folder"
    ? !!selectedKnowledgeBaseId && readyFolderDocuments.length > 0
    : !!selectedDocumentId && selectedDocument?.status === "ready";
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
        <button type="button" className="sidebar-library-link" onClick={() => { setActivePage("library"); setIsMobileSidebarOpen(false); }}><BookOpen size={17}/> Kenyan library</button>
        <label className="organization-switcher">Workspace
          <select value={activeOrganizationId} onChange={(event) => { clearCurrentConversation(); setActiveOrganizationId(event.target.value); setSelectedKnowledgeBaseId(""); setSelectedDocumentId(""); setDocuments([]); setChatScope("folder"); setConversationVisibility("private"); }}>
            <option value="">Personal folders</option>
            {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
          </select>
        </label>
        <button type="button" className="sidebar-library-link" onClick={() => { setActivePage("organizations"); setIsMobileSidebarOpen(false); }}>Manage organizations</button>

        <form className="newkb" onSubmit={handleCreateKnowledgeBase}>
          <input
            placeholder="New folder name"
            value={newKnowledgeBaseName}
            onChange={(event) => setNewKnowledgeBaseName(event.target.value)}
          />
          <button title="Create" disabled={isBusy || !canManageActiveOrg}>
            <Plus size={18} />
          </button>
          <label className="sensitive-folder-option"><input type="checkbox" checked={newKnowledgeBaseSensitive} onChange={(event)=>setNewKnowledgeBaseSensitive(event.target.checked)}/><span>Mark new folder sensitive</span></label>
        </form>

        <nav className="folder-tree" aria-label="Folders and files">
          {visibleKnowledgeBases.map((knowledgeBase) => {
            const isExpanded = expandedKnowledgeBaseIds.has(knowledgeBase.id);
            const folder = folderDocuments[knowledgeBase.id];
            const folderChats = conversationHistory.filter((conversation) => conversation.knowledge_base_id === knowledgeBase.id && conversation.scope_type === "folder");
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
                  {canManageActiveOrg && <ItemActionMenu
                    label={knowledgeBase.name}
                    open={openItemMenuId === `folder-${knowledgeBase.id}`}
                    onToggle={() => setOpenItemMenuId((current) => current === `folder-${knowledgeBase.id}` ? null : `folder-${knowledgeBase.id}`)}
                    onClose={() => setOpenItemMenuId(null)}
                    items={[
                      { label: knowledgeBase.is_sensitive ? "Remove sensitive warning" : "Mark folder sensitive", icon: <ShieldCheck size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { is_sensitive: !knowledgeBase.is_sensitive }) },
                      { label: knowledgeBase.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { is_pinned: !knowledgeBase.is_pinned }) },
                      { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("folder", knowledgeBase.name, (name) => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { name })) },
                      { label: knowledgeBase.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}`, { is_archived: !knowledgeBase.is_archived }) },
                      { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => void handleDeleteKnowledgeBase(knowledgeBase) },
                    ]}
                  />}
                </div>
                {isExpanded && (
                  <div className="folder-file-tree" aria-label={`Files in ${knowledgeBase.name}`}>
                    {folder?.loading && <small className="folder-tree-note">Loading files…</small>}
                    {folder?.error && <small className="folder-tree-note error">{folder.error}</small>}
                    {folderChats.length > 0 && <div className="folder-scope-history" aria-label={`Folder-wide chats for ${knowledgeBase.name}`}>
                      <small className="history-empty">Folder chats</small>
                      {folderChats.map((conversation) => <div className={`history-row ${conversationId === conversation.id ? "selected" : ""} ${conversation.is_archived ? "archived" : ""}`} key={conversation.id}>
                        <button className="history-open" type="button" title={conversation.title} disabled={isBusy} onClick={() => void handleOpenConversation(conversation)}><MessageCircle size={13} /><span>{conversation.title || "New folder chat"}</span>{conversation.is_pinned && <Pin size={12} aria-label="Pinned" />}</button>
                        <ItemActionMenu label={conversation.title} open={openItemMenuId === `chat-${conversation.id}`} onToggle={() => setOpenItemMenuId((current) => current === `chat-${conversation.id}` ? null : `chat-${conversation.id}`)} onClose={() => setOpenItemMenuId(null)} items={[
                          { label: conversation.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/conversations/${conversation.id}`, { is_pinned: !conversation.is_pinned }) },
                          { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("chat", conversation.title, (title) => void updateItem(`/conversations/${conversation.id}`, { title })) },
                          { label: conversation.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/conversations/${conversation.id}`, { is_archived: !conversation.is_archived }) },
                          { label: "Download", icon: <Download size={15} />, onClick: () => void handleDownloadConversation(conversation) },
                          { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => void handleDeleteConversation(conversation) },
                        ]} />
                      </div>)}
                    </div>}
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
                              {knowledgeBase.organization_id && document.uploaded_by_name && <small title={document.uploaded_by_email ?? ""}>by {document.uploaded_by_name}</small>}
                              {document.is_archived && <small>archived</small>}
                              {document.is_pinned && <Pin size={12} aria-label="Pinned" />}
                              {document.status !== "ready" && (
                                <small>{document.status === "pending" || document.status === "processing" ? `Processing: ${document.progress_stage}` : document.status}</small>
                              )}
                            </button>
                            {canManageActiveOrg && <ItemActionMenu
                              label={document.original_filename}
                              open={openItemMenuId === `document-${document.id}`}
                              onToggle={() => setOpenItemMenuId((current) => current === `document-${document.id}` ? null : `document-${document.id}`)}
                              onClose={() => setOpenItemMenuId(null)}
                              items={[
                                { label: document.is_pinned ? "Unpin" : "Pin", icon: <Pin size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { is_pinned: !document.is_pinned }) },
                                { label: "Rename", icon: <Pencil size={15} />, onClick: () => promptRename("file", document.original_filename, (original_filename) => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { original_filename })) },
                                { label: document.is_archived ? "Restore" : "Archive", icon: <Archive size={15} />, onClick: () => void updateItem(`/knowledge-bases/${knowledgeBase.id}/documents/${document.id}`, { is_archived: !document.is_archived }) },
                                { label: "Delete", icon: <Trash2 size={15} />, danger: true, onClick: () => handleDeleteDocument(knowledgeBase.id, document) },
                              ]}
                            />}
                          </div>
                          {document.status === "failed" && (
                            <div className="folder-document-failure" role="alert">
                              <small>{friendlyProcessingError(document.processing_error)}</small>
                              <button type="button" onClick={() => handleDeleteDocument(knowledgeBase.id, document)}>
                                Delete and try another file
                              </button>
                            </div>
                          )}
                          {document.status === "ready" && document.low_ocr_confidence && (
                            <div className="ocr-quality-warning" role="status">Some scanned text may be unclear{document.ocr_confidence !== null ? ` (${Math.round(document.ocr_confidence)}% OCR confidence)` : ""}. Check important details against the original.</div>
                          )}
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
          <details className="sidebar-more">
            <summary><MoreVertical size={17} /> More</summary>
            <div className="sidebar-more-content">
              <div className="workspace-label"><ShieldCheck size={16} /> Private workspace</div>
              <button type="button" onClick={() => { setActivePage("upcoming"); setIsMobileSidebarOpen(false); }}>
                <CalendarDays size={17} /> Upcoming dates
              </button>
              <button type="button" onClick={() => { setActivePage("tools"); setIsMobileSidebarOpen(false); }}>
                <Briefcase size={17} /> Business tools
              </button>
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
              <button type="button" onClick={handleLogout}>
                <LogOut size={17} /> Sign out
              </button>
              <div className="sidebar-legal-links">
                <button type="button" onClick={() => openLegalPage("terms")}>Terms</button>
                <span aria-hidden="true">·</span>
                <button type="button" onClick={() => openLegalPage("privacy")}>Privacy</button>
              </div>
            </div>
          </details>
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
              <h2>{chatScope === "library" ? "Kenyan public library" : chatScope === "folder_library" ? selectedKnowledgeBase?.name ?? "Folder + library" : chatScope === "folder" ? selectedKnowledgeBase?.name ?? "Your workspace" : selectedDocument?.original_filename ?? selectedKnowledgeBase?.name ?? "Your workspace"}</h2>
              <p>{chatScope === "library" ? "Searching current official library documents." : chatScope === "folder_library" ? `Asking across: ${selectedKnowledgeBase?.name ?? "selected folder"} (${readyFolderDocuments.length} folder documents) + Kenyan library` : chatScope === "folder"
                ? selectedKnowledgeBase ? selectedFolderDocumentsLoading ? "Checking the files in this folder…" : `Asking across: ${selectedKnowledgeBase.name} (${readyFolderDocuments.length} document${readyFolderDocuments.length === 1 ? "" : "s"})` : "Choose a folder to chat across its ready files."
                : selectedDocument ? "Questions and saved chats are tied to this file. Expand it in the sidebar to reopen a chat." : "Please select a file to use the chatbot."}</p>
            </div>
            <div className="chat-actions">
              <span className="pill">{documents.length} file{documents.length === 1 ? "" : "s"}</span>
              <button className="chat-tool-button" type="button" onClick={handleNewChat} title="New chat" aria-label="Start a new chat" disabled={isBusy || !hasValidChatScope}>
                <Plus size={17} />
              </button>
              {conversationId && messages.length > 0 && (
                <button
                  className="chat-tool-button"
                  type="button"
                  title="Download this conversation"
                  aria-label="Download this conversation"
                  disabled={isBusy}
                  onClick={() => {
                    const currentConversation = conversationHistory.find((item) => item.id === conversationId);
                    const exportKnowledgeBaseId = currentConversation?.knowledge_base_id ?? selectedKnowledgeBaseId;
                    if (conversationId && exportKnowledgeBaseId) void recordOrganizationExport("conversation", conversationId, exportKnowledgeBaseId).catch((error) => setErrorMessage(getErrorMessage(error)));
                    void downloadConversationPdf(currentConversation?.title ?? "DocuMind conversation", messages).catch((error) => setErrorMessage(getErrorMessage(error)));
                  }}
                >
                  <Download size={17} />
                </button>
              )}
              <button className="chat-tool-button" type="button" onClick={() => setIsHelpPanelOpen(true)} title="Help and examples" aria-label="Open help and examples">
                <HelpCircle size={17} />
              </button>
              <button className="upload-trigger" onClick={() => void openUploadPanel()} disabled={!selectedKnowledgeBaseId || !canUploadToActiveOrg}>
                <Upload size={17} /> Add files
              </button>
            </div>
          </div>

          {(chatScope === "library" || chatScope === "folder_library") && <div className="legal-library-banner" role="note">Information only. Not legal or tax advice. Check the official source.</div>}

          {selectedDocument && selectedDocument.status === "ready" && (
            <Suspense fallback={<div className="important-dates-loading" role="status">Loading important dates…</div>}>
              <ImportantDates token={token} documentId={selectedDocument.id} />
            </Suspense>
          )}

          {errorMessage && (
            <div className="error banner" role="alert">
              {errorMessage}
              <button aria-label="Dismiss error" onClick={() => setErrorMessage("")}><X size={16} /></button>
            </div>
          )}

          {chatScope === "folder" && selectedKnowledgeBase && !selectedFolderDocumentsLoading && readyFolderDocuments.length === 0 && (
            <div className="folder-no-ready" role="status">This folder has no ready documents yet. Upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file and wait until it is ready, then ask a question across the folder.</div>
          )}

          <div className="messages">
            {messages.length === 0 && (
              <div className="empty">
                <BookOpen size={36} />
                <h2>What would you like to learn?</h2>
                {chatScope === "folder" && selectedKnowledgeBase && selectedFolderDocumentsLoading
                  ? <p role="status">Checking the files in this folder…</p>
                  : <p>{chatScope === "folder" && selectedKnowledgeBase
                    ? <>Folder mode searches all ready documents in <strong>{selectedKnowledgeBase.name}</strong>. Choose <strong>This document</strong> to focus on one selected file. Answers show source file names and page numbers.</>
                    : selectedDocumentId
                      ? <>Document mode searches only <strong>{selectedDocument?.original_filename}</strong>. Choose <strong>This folder</strong> to search across every ready document in <strong>{selectedKnowledgeBase?.name}</strong>. Your chats stay under their selected scope.</>
                      : <><strong>Hello {userProfile?.full_name.trim().split(/\s+/)[0] || "there"}</strong>, choose a folder to use <strong>This folder</strong> and search across its ready documents, or select a file and use <strong>This document</strong> to focus on that file. <span className="desktop-file-location">Your folders and files are in the left sidebar.</span><span className="mobile-file-location">Tap the folder button at the top to open the file list.</span> Upload PDF, TXT, DOCX, JPG, PNG, or HEIC files if you have not added one yet.</>}</p>}
                {!selectedKnowledgeBase && <button className="mobile-open-files" type="button" onClick={() => setIsMobileSidebarOpen(true)}><Menu size={15} /> Open file list</button>}
                {hasValidChatScope && (
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
                {message.role === "user" && message.actor_name && <small className="message-actor">{message.actor_name}</small>}
                {message.role === "assistant"
                  ? <AssistantMessage content={message.content} />
                  : <div>{message.content}</div>}
                {message.role === "assistant" && (
                  <>
                  <div className={`answer-confidence ${message.confidence_label?.toLowerCase().replaceAll(" ", "-") ?? ""}`} aria-label={`Source match: ${message.confidence_label ?? "not rated"}`}>
                    {message.confidence_label ?? "Answer"}{message.confidence_score != null ? ` · ${Math.round(message.confidence_score * 100)}% retrieval match` : ""}
                  </div>
                  {message.message_id && <div className="answer-feedback" aria-label="Answer feedback">
                    <button type="button" aria-pressed={message.feedback_status === "up"} title="Helpful answer" onClick={() => void submitAnswerFeedback(message, "up")}><ThumbsUp size={14} /> Helpful</button>
                    <button type="button" aria-pressed={message.feedback_status === "down"} title="Not helpful" onClick={() => void submitAnswerFeedback(message, "down")}><ThumbsDown size={14} /> Not helpful</button>
                    <button type="button" aria-pressed={message.feedback_status === "report"} title="Report a wrong answer" onClick={() => void submitAnswerFeedback(message, "report")}><Flag size={14} /> Report a wrong answer</button>
                    {message.feedback_status && <span role="status">Feedback saved</span>}
                  </div>}
                  <button
                    className="answer-print"
                    type="button"
                    title="Download this answer as PDF"
                    onClick={() => {
                      const currentConversation = conversationHistory.find((item) => item.id === conversationId);
                      const exportKnowledgeBaseId = currentConversation?.knowledge_base_id ?? selectedKnowledgeBaseId;
                      if (conversationId && exportKnowledgeBaseId) void recordOrganizationExport("conversation", conversationId, exportKnowledgeBaseId).catch((error) => setErrorMessage(getErrorMessage(error)));
                      void downloadAnswerPdf(message, currentConversation?.title ?? "DocuMind teaching notes").catch((error) => setErrorMessage(getErrorMessage(error)));
                    }}
                  ><Download size={14} /> Download PDF</button>
                  </>
                )}
                {message.sources && message.sources.length > 0 && (
                  <div className="sources">
                    <strong>{chatScope === "folder" || chatScope === "folder_library" ? `Sources from ${new Set(message.sources.filter((source) => source.source_type === "library" ? true : !!source.document_id).map((source) => source.filename)).size} documents` : "Sources"}</strong>
                    {message.sources.map((source, sourceIndex) => (
                      <div className="source" key={`${source.document_id ?? source.filename}-${sourceIndex}`}>
                        <span className="source-title">
                          [{sourceIndex + 1}] {source.filename}{source.section_title ? ` · ${source.section_title}` : ""}{source.page_number != null ? ` · page ${source.page_number}` : ""}{source.version_label ? ` · ${source.version_label}` : ""}
                        </span>
                        {source.source_url && <a className="library-source-link" href={source.source_url} target="_blank" rel="noreferrer">Open official source</a>}
                        <p>{source.excerpt}</p>
                      </div>
                    ))}
                  </div>
                )}
                {message.role === "assistant" && chatScope === "folder" && (!message.sources || message.sources.length === 0) && <div className="sources"><strong>Sources from 0 documents</strong></div>}
              </div>
            ))}
            {isBusy && <div className="muted" role="status" aria-live="polite">{busyMessage}</div>}
            <div ref={messagesEndRef} />
          </div>

              {selectedKnowledgeBase && <div className="chat-scope-row">
            <div className="chat-scope-toggle" role="group" aria-label="Chat search scope" onKeyDown={(event) => {
              if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
              const scopes = selectedDocument ? ["document", "folder", "folder_library"] : ["folder", "folder_library"];
              const currentIndex = Math.max(0, scopes.indexOf(chatScope));
              const nextScope = event.key === "ArrowRight"
                ? scopes[(currentIndex + 1) % scopes.length]
                : scopes[(currentIndex + scopes.length - 1) % scopes.length];
              if (nextScope === "document" && !selectedDocument) return;
              event.preventDefault();
              if (nextScope !== chatScope && !isBusy) { clearCurrentConversation(); setChatScope(nextScope); }
              event.currentTarget.querySelector<HTMLButtonElement>(`[data-chat-scope="${nextScope}"]`)?.focus();
            }}>
              <button data-chat-scope="document" type="button" className={chatScope === "document" ? "active" : ""} aria-pressed={chatScope === "document"} disabled={!selectedDocument || isBusy} onClick={() => { if (chatScope !== "document") { clearCurrentConversation(); setChatScope("document"); } }}>This document</button>
              <button data-chat-scope="folder" type="button" className={chatScope === "folder" ? "active" : ""} aria-pressed={chatScope === "folder"} disabled={isBusy} onClick={() => { if (chatScope !== "folder") { clearCurrentConversation(); setChatScope("folder"); } }}>This folder</button>
              {selectedKnowledgeBase && <button data-chat-scope="folder_library" type="button" className={chatScope === "folder_library" ? "active" : ""} aria-pressed={chatScope === "folder_library"} disabled={isBusy} onClick={() => { if (chatScope !== "folder_library") { clearCurrentConversation(); setChatScope("folder_library"); } }}>Folder + library</button>}
            </div>
            {!!selectedKnowledgeBase.organization_id && <label className="conversation-visibility">Conversation
              <select value={conversationVisibility} onChange={(event) => void changeConversationVisibility(event.target.value as "private" | "shared")} disabled={isBusy}>
                <option value="private">Private to me</option><option value="shared">Shared with organization</option>
              </select>
            </label>}
          </div>}

          <form className="composer" onSubmit={handleSendQuestion}>
            <input
              ref={questionInputRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={chatScope === "folder" && selectedKnowledgeBase ? "Ask a question across this folder…" : selectedDocumentId ? "Ask a question about the selected file…" : "Ask a question (choose a file first)…"}
              disabled={isBusy}
            />
            <button disabled={isBusy || !question.trim() || !hasValidChatScope} aria-label="Send question">
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
                <p>PDF, TXT, DOCX, JPG, PNG, or HEIC · maximum {uploadLimitMb} MB per file</p>
              </div>
              <button className="icon-button" aria-label="Close uploads" onClick={() => setIsUploadPanelOpen(false)} disabled={isBusy}><X /></button>
            </div>
            {selectedKnowledgeBase?.is_sensitive && <p className="sensitive-upload-warning" role="alert"><strong>Sensitive folder.</strong> Uploaded content may be sent to DeepSeek when you use chat. Do not upload sensitive information unless your organization permits this processing. This warning does not block external AI processing.</p>}
            <label className={`upload ${isBusy ? "disabled" : ""}`}>
              <Upload size={21} />
              <strong>{isBusy ? busyMessage : "Choose files to upload"}</strong>
              <small>Scanned PDFs and photos are read with OCR. Clear scans work best. Select several JPG/PNG photos to combine them into one PDF in the order selected.</small>
              <input ref={uploadInputRef} type="file" accept=".pdf,.txt,.docx,.jpg,.jpeg,.png,.heic" multiple onChange={handleUpload} disabled={isBusy} />
            </label>
            <div className="photo-upload-actions">
              <button type="button" onClick={() => photoInputRef.current?.click()} disabled={isBusy}>Select photos</button>
              <button type="button" className="take-photo-action" onClick={() => cameraInputRef.current?.click()} disabled={isBusy}>Take photo</button>
              <input ref={photoInputRef} className="visually-hidden" type="file" accept="image/jpeg,image/png,.heic" multiple onChange={handleUpload} disabled={isBusy} aria-label="Select several photos" />
              <input ref={cameraInputRef} className="visually-hidden" type="file" accept="image/*" capture="environment" multiple onChange={handleUpload} disabled={isBusy} aria-label="Take photos with your camera" />
            </div>
            {uploadError && <div className="error banner upload-error" role="alert"><span>{uploadError}</span><button className="upload-try-another" type="button" disabled={isBusy} onClick={() => { if (uploadInputRef.current) uploadInputRef.current.value = ""; uploadInputRef.current?.click(); }}>Delete and try another file</button></div>}
            {uploadSuccess && <div className="success banner upload-success" role="status">{uploadSuccess}</div>}
            <div className="filelist upload-filelist">
              {documents.map((document) => (
                <div className={`file ${document.status === "failed" ? "file-failed" : ""}`} key={document.id}>
                  <FileText size={20} />
                  <div>
                    <strong title={document.original_filename}>{document.original_filename}</strong>
                    <small>{document.status === "pending" || document.status === "processing" ? `Processing · ${document.progress_stage}` : document.status} · {document.chunk_count} passages · {(document.file_size_bytes / 1024).toFixed(0)} KB</small>
                    {(document.status === "pending" || document.status === "processing") && document.processing_error && <small className="document-retry-note" role="status">A retry is scheduled: {friendlyProcessingError(document.processing_error)}</small>}
                    {document.status === "ready" && document.low_ocr_confidence && <small className="ocr-quality-warning" role="status">OCR confidence is low{document.ocr_confidence !== null ? ` (${Math.round(document.ocr_confidence)}%)` : ""}. Some text may be unclear.</small>}
                    {document.status === "failed" && <small className="error document-error">{friendlyProcessingError(document.processing_error)}</small>}
                    {(document.status === "pending" || document.status === "processing") && document.processing_error && <small className="document-retry-note" role="status">A retry is scheduled: {friendlyProcessingError(document.processing_error)}</small>}
                  </div>
                  {document.status === "failed" ? (
                    <button className="failed-upload-action" type="button" onClick={() => handleDeleteDocument(selectedKnowledgeBaseId, document)} aria-label={`Delete ${document.original_filename} and try another file`}>Delete and try another file</button>
                  ) : (
                    <button type="button" onClick={() => handleDeleteDocument(selectedKnowledgeBaseId, document)} title="Delete file" aria-label={`Delete ${document.original_filename}`}><Trash2 size={16} /></button>
                  )}
                </div>
              ))}
              {documents.length === 0 && <p className="muted">No files in this folder yet.</p>}
            </div>
          </section>
        </div>
      )}

      {deleteDialog && (
        <div className="delete-confirm-backdrop">
          <section className="delete-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-confirm-title" aria-describedby="delete-confirm-description">
            <h2 id="delete-confirm-title">Delete {deleteDialog.target.kind === "document" ? "document" : "folder"}?</h2>
            <p className="delete-confirm-item">{deleteDialog.target.kind === "document" ? deleteDialog.target.document.original_filename : deleteDialog.target.knowledgeBase.name}</p>
            <p id="delete-confirm-description">
              {deleteDialog.loading
                ? "Checking saved conversations before you delete…"
                : deleteDialog.target.kind === "document"
                  ? `This document has ${deleteDialog.conversations?.length ?? 0} saved conversation${deleteDialog.conversations?.length === 1 ? "" : "s"}. Deleting it will permanently delete those conversations.`
                  : `This folder contains ${deleteDialog.documentCount ?? 0} document${deleteDialog.documentCount === 1 ? "" : "s"} and ${deleteDialog.conversations?.length ?? 0} saved conversation${deleteDialog.conversations?.length === 1 ? "" : "s"}. Deleting it will permanently delete its files and conversations.`}
            </p>
            {deleteDialog.loading && <p className="delete-confirm-loading" role="status">Please wait while the history count is checked.</p>}
            {deleteDialog.error && <div className="error delete-confirm-error" role="alert"><span>{deleteDialog.error}</span>
              {!deleteDialog.deleting && <button type="button" className="delete-confirm-retry" onClick={() => void openDeleteConfirmation(deleteDialog.target, true)}>Retry</button>}
            </div>}
            <div className="delete-confirm-actions">
              <button type="button" className="delete-confirm-cancel" autoFocus onClick={() => setDeleteDialog(null)} disabled={deleteDialog.deleting}>Cancel</button>
              <button type="button" className="delete-confirm-download" onClick={() => void confirmDeleteWithHistory(true)} disabled={deleteDialog.loading || deleteDialog.deleting || !!deleteDialog.error || !deleteDialog.conversations?.length} title={!deleteDialog.loading && !deleteDialog.conversations?.length ? "There are no conversations to download." : undefined}>
                {deleteDialog.deleting ? "Working…" : "Download conversations as PDF then delete"}
              </button>
              <button type="button" className="delete-confirm-anyway" onClick={() => void confirmDeleteWithHistory(false)} disabled={deleteDialog.loading || deleteDialog.deleting || !!deleteDialog.error}>
                {deleteDialog.deleting ? "Deleting…" : "Delete anyway"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

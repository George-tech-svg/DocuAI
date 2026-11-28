import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Activity, ArrowLeft, BadgeCheck, CreditCard, FileText, LayoutDashboard, MessageCircle, Package, Plus, Users, BookOpen, Flag, ShieldCheck, ScrollText } from "lucide-react";
import { getErrorMessage, request } from "./api";
import AdminSecuritySettings from "./AdminSecuritySettings";

type Tab = "overview" | "members" | "activity" | "plans" | "subscriptions" | "payments" | "payment-recovery" | "jobs" | "library" | "answer-reports" | "security" | "audit";
type Overview = { members_total: number; members_active: number; documents_total: number; documents_ready: number; documents_failed: number; conversations_total: number; questions_total: number; questions_last_7_days: number; subscriptions_active: number; subscriptions_expiring: number; payments_total: number; payments_pending: number; revenue_kes: number; mpesa_ready: boolean; google_ready: boolean; ai_ready: boolean; storage_ready: boolean };
type Plan = { id: string; name: string; description: string; price_kes: number; duration_days: number; is_active: boolean };
type Member = { id: string; full_name: string; email: string; is_active: boolean; is_superuser: boolean; current_plan: string | null; subscription_status: string | null; expires_at: string | null; created_at: string };
type Subscription = { id: string; full_name: string; email: string; plan_name: string; price_kes: number; status: string; expires_at: string | null; created_at: string };
type Payment = { id: string; full_name: string; email: string; amount_kes: number; phone_number: string; status: string; mpesa_receipt: string | null; result_description: string | null; created_at: string };
type ActivityEvent = { id: string; kind: string; member_name: string; member_email: string; summary: string; created_at: string };
type RecoveryMatch = { payment_id: string; plan_id: string; member_name: string; member_email: string; plan_name: string; amount_kes: number; phone_number: string; status: string; mpesa_receipt: string | null; created_at: string; match_reason: string };
type PaymentRecovery = { id: string; user_id: string; member_name: string; member_email: string; phone_number: string; paid_at: string; mpesa_message: string; status: string; matched_payment_id: string | null; granted_subscription_id: string | null; reviewed_by_user_id: string | null; rejection_reason: string | null; admin_note: string | null; created_at: string; reviewed_at: string | null; matches: RecoveryMatch[] };
type RecoveryAudit = { id: string; admin_user_id: string | null; admin_email: string | null; payment_recovery_request_id: string | null; action: string; reason: string | null; details: string | null; created_at: string };
type ProcessingJob = { id: string; type: string; attempts: number; max_attempts: number; last_error: string | null; created_at: string; updated_at: string; document_id: string | null; document_name: string | null; library_document_id?: string | null };
type JobQueue = { counts: Record<"queued" | "running" | "done" | "failed", number>; failed: ProcessingJob[] };
type LibraryCollection = { id: string; slug: string; name: string; description: string; category: string };
type LibraryAdminDocument = { id: string; collection_id: string; collection_name: string; title: string; short_name: string; publisher: string; source_url: string; version_label: string; is_current: boolean; status: string; processing_error: string | null; content_hash: string | null; created_at: string };
type LibraryVersion = { id: string; title: string; version_label: string; is_current: boolean; status: string; content_hash: string | null; created_at: string };
type AnswerReport = { id: string; member_name: string; member_email: string; question: string; answer: string; sources: { filename: string; page_number: number | null; excerpt: string }[]; model_version: string; comment: string | null; status: string; review_note: string | null; created_at: string; reviewed_at: string | null };
type PlatformAuditEvent = {id:string;actor_email:string|null;action:string;resource_type:string;resource_id:string|null;details:Record<string,unknown>;created_at:string};

const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "members", label: "Members", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "plans", label: "Plans", icon: Package },
  { id: "subscriptions", label: "Subscriptions", icon: BadgeCheck },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "payment-recovery", label: "Payment recovery", icon: CreditCard },
  { id: "jobs", label: "Jobs", icon: Activity },
  { id: "library", label: "Library", icon: BookOpen },
  { id: "answer-reports", label: "Answer reports", icon: Flag },
  { id: "security", label: "Security", icon: ShieldCheck },
  { id: "audit", label: "Audit log", icon: ScrollText },
];

function money(amount: number) { return `KSh ${amount.toLocaleString()}`; }
function date(value: string | null) { return value ? new Date(value).toLocaleDateString() : "—"; }
const retryableJobTypes = new Set(["index_document", "extract_events", "send_due_reminders", "ingest_library_document", "record_library_update", "export_user_data", "export_organization_data", "delete_user_data", "delete_organization_data", "enforce_organization_retention", "cleanup_privacy_exports"]);

function PaymentRecoveryCard({ recovery, plans, busy, onReview }: {
  recovery: PaymentRecovery;
  plans: Plan[];
  busy: boolean;
  onReview: (action: "grant" | "reject", payload: { plan_id?: string; matched_payment_id?: string; reason?: string }) => void;
}) {
  const firstMatch = recovery.matches[0];
  const [matchedPaymentId, setMatchedPaymentId] = useState(firstMatch?.payment_id ?? "");
  const [planId, setPlanId] = useState(firstMatch?.plan_id ?? plans[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState("");
  const pending = recovery.status === "pending";

  function reject() {
    if (!reason.trim()) { setLocalError("Enter a reason before rejecting this request."); return; }
    setLocalError("");
    onReview("reject", { matched_payment_id: matchedPaymentId || undefined, reason: reason.trim() });
  }

  function grant() {
    if (!planId) { setLocalError("Choose a plan to grant access."); return; }
    const selectedPlan = plans.find((plan) => plan.id === planId);
    if (!window.confirm(`Grant ${selectedPlan?.name ?? "the selected plan"} access to ${recovery.member_name}? This decision will be recorded.`)) return;
    setLocalError("");
    onReview("grant", { plan_id: planId, matched_payment_id: matchedPaymentId || undefined, reason: reason.trim() || undefined });
  }

  return (
    <article className="admin-row payment-recovery-card">
      <div className="recovery-card-heading">
        <div className="admin-row-main"><strong>{recovery.member_name} · {recovery.member_email}</strong><span>{recovery.phone_number} · payment time {new Date(recovery.paid_at).toLocaleString()}</span><small>Submitted {new Date(recovery.created_at).toLocaleString()} · {recovery.status}</small></div>
      </div>
      <div className="recovery-evidence"><strong>Member’s M-Pesa message / receipt</strong><p>{recovery.mpesa_message}</p></div>
      {recovery.matches.length > 0 ? <div className="recovery-candidates"><strong>Suggested recorded payment matches</strong>
        <label className="recovery-match">
          <input type="radio" name={`match-${recovery.id}`} checked={!matchedPaymentId} disabled={!pending || busy} onChange={() => setMatchedPaymentId("")} />
          <span><b>No match selected</b><small>Use this if none of the suggestions is the member’s payment.</small></span>
        </label>
        {recovery.matches.map((match) => <label className="recovery-match" key={match.payment_id}>
        <input type="radio" name={`match-${recovery.id}`} checked={matchedPaymentId === match.payment_id} disabled={!pending || busy} onChange={() => { setMatchedPaymentId(match.payment_id); if (plans.some((plan) => plan.id === match.plan_id)) setPlanId(match.plan_id); }} />
        <span><b>{money(match.amount_kes)} · {match.status}</b><small>{match.member_name} · {match.member_email} · {match.phone_number}</small><small>{match.mpesa_receipt ? `Receipt ${match.mpesa_receipt} · ` : ""}{new Date(match.created_at).toLocaleString()} · {match.match_reason}</small></span>
        </label>)}</div> : <p className="admin-note">No matching payment was found in the platform’s Daraja records. Check the receipt details and reconcile against the Safaricom statement before deciding.</p>}
      {pending ? <>
        <label className="recovery-plan-field">Plan to grant if approved<select value={planId} onChange={(event) => setPlanId(event.target.value)} disabled={busy} required><option value="">Choose a plan</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {money(plan.price_kes)} / {plan.duration_days} days{plan.is_active ? "" : " (hidden)"}</option>)}</select></label>
        <label className="recovery-reason-field">Admin note or rejection reason<textarea rows={2} maxLength={1000} value={reason} onChange={(event) => { setReason(event.target.value); setLocalError(""); }} disabled={busy} placeholder="Required when rejecting. Optional note when granting." /></label>
        {localError && <p className="error" role="alert">{localError}</p>}
        <div className="recovery-actions"><button className="admin-primary" type="button" disabled={busy || !plans.length} onClick={grant}>{busy ? "Saving…" : "Grant access"}</button><button className="admin-secondary" type="button" disabled={busy} onClick={reject}>Reject request</button></div>
      </> : <div className="recovery-resolution"><strong>{recovery.status === "granted" ? "Access was granted" : "Request rejected"}</strong>{recovery.admin_note && <p>Admin note: {recovery.admin_note}</p>}{recovery.rejection_reason && <p>Reason: {recovery.rejection_reason}</p>}<small>Reviewed {recovery.reviewed_at ? new Date(recovery.reviewed_at).toLocaleString() : "—"} · Administrator ID {recovery.reviewed_by_user_id ?? "unavailable"} · Audit recorded</small></div>}
    </article>
  );
}

export default function AdminDashboard({ token, onBack }: { token: string; onBack: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [paymentRecovery, setPaymentRecovery] = useState<PaymentRecovery[]>([]);
  const [recoveryAudit, setRecoveryAudit] = useState<RecoveryAudit[]>([]);
  const [jobQueue, setJobQueue] = useState<JobQueue | null>(null);
  const [libraryCollections, setLibraryCollections] = useState<LibraryCollection[]>([]);
  const [libraryDocuments, setLibraryDocuments] = useState<LibraryAdminDocument[]>([]);
  const [libraryForm, setLibraryForm] = useState({ collection_id: "", title: "", short_name: "", source_url: "", publisher: "", version_label: "" });
  const [libraryFile, setLibraryFile] = useState<File | null>(null);
  const [libraryVersions, setLibraryVersions] = useState<Record<string, LibraryVersion[]>>({});
  const [answerReports, setAnswerReports] = useState<AnswerReport[]>([]);
  const [auditEvents,setAuditEvents]=useState<PlatformAuditEvent[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [duration, setDuration] = useState("30");

  async function load(nextTab = tab) {
    setError("");
    setLoading(true);
    try {
      if (nextTab === "overview") setOverview(await request<Overview>("/admin/overview", token));
      if (nextTab === "members") setMembers(await request<Member[]>("/admin/members", token));
      if (nextTab === "activity") setActivities(await request<ActivityEvent[]>("/admin/activity", token));
      if (nextTab === "plans") setPlans(await request<Plan[]>("/admin/plans", token));
      if (nextTab === "subscriptions") setSubscriptions(await request<Subscription[]>("/admin/subscriptions", token));
      if (nextTab === "payments") setPayments(await request<Payment[]>("/admin/payments", token));
      if (nextTab === "jobs") setJobQueue(await request<JobQueue>("/admin/jobs", token));
      if (nextTab === "answer-reports") setAnswerReports((await request<{items:AnswerReport[] }>("/admin/answer-feedback", token)).items);
      if (nextTab === "audit") setAuditEvents((await request<{items:PlatformAuditEvent[]}>("/admin/audit-events", token)).items);
      if (nextTab === "library") {
        const [collections, documents] = await Promise.all([request<LibraryCollection[]>("/admin/library/collections", token), request<LibraryAdminDocument[]>("/admin/library/documents", token)]);
        setLibraryCollections(collections); setLibraryDocuments(documents);
      }
      if (nextTab === "payment-recovery") {
        const [requests, availablePlans, audit] = await Promise.all([
          request<PaymentRecovery[]>("/admin/payment-recovery", token),
          request<Plan[]>("/admin/plans", token),
          request<RecoveryAudit[]>("/admin/payment-recovery/audit", token),
        ]);
        setPaymentRecovery(requests);
        setPlans(availablePlans);
        setRecoveryAudit(audit);
      }
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(tab); }, [tab, token]);

  async function mutate(path: string, method: "POST" | "PATCH", body?: unknown) {
    setBusy(true); setError("");
    try {
      await request(path, token, { method, body: body ? JSON.stringify(body) : undefined });
      setNotice(path.includes("/admin/jobs/") ? "The document processing job has been queued again." : "");
      await load(tab);
      if (tab === "plans") await load("overview");
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  }

  async function reviewAnswerReport(report: AnswerReport) {
    const note = window.prompt("Add a review note (optional):", report.review_note ?? "");
    if (note === null) return;
    await mutate(`/admin/answer-feedback/${report.id}`, "PATCH", { status: "reviewed", review_note: note.trim() || null });
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await mutate("/admin/plans", "POST", { name, description, price_kes: Number(price), duration_days: Number(duration) });
    setName(""); setDescription(""); setPrice(""); setDuration("30");
  }

  async function addLibraryDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      if (!libraryFile) throw new Error("Choose a PDF, TXT, or DOCX file to upload.");
      const form = new FormData();
      Object.entries(libraryForm).forEach(([key, value]) => form.append(key, value));
      form.append("file", libraryFile);
      await request("/admin/library/documents/upload", token, { method: "POST", body: form });
      setNotice("Document uploaded and queued. The worker will index it.");
      setLibraryFile(null);
      setLibraryForm({ collection_id: libraryForm.collection_id, title: "", short_name: "", source_url: "", publisher: "", version_label: "" });
      setLibraryDocuments(await request<LibraryAdminDocument[]>("/admin/library/documents", token));
    } catch (e) { setError(getErrorMessage(e)); } finally { setBusy(false); }
  }

  async function reviewPaymentRecovery(requestId: string, action: "grant" | "reject", payload: { plan_id?: string; matched_payment_id?: string; reason?: string }) {
    setBusy(true); setError(""); setNotice("");
    try {
      await request(`/admin/payment-recovery/${requestId}/review`, token, {
        method: "POST",
        body: JSON.stringify({ action, ...payload }),
      });
      setNotice(action === "grant" ? "Access granted. The decision was recorded in the administrator audit log." : "Request rejected. The reason was recorded in the administrator audit log.");
      await load("payment-recovery");
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <button className="admin-back" type="button" onClick={onBack}><ArrowLeft size={17} /> Workspace</button>
        <div><span>PLATFORM MANAGEMENT</span><h1>Admin console</h1></div>
      </header>
      <nav className="admin-tabs" aria-label="Administration sections">
        {tabs.map(({ id, label, icon: Icon }) => <button type="button" key={id} className={tab === id ? "active" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}><Icon size={17} />{label}</button>)}
      </nav>
      {error && <div className="admin-error" role="alert">{error}<button className="admin-secondary" type="button" onClick={() => void load()} disabled={loading}>Try again</button></div>}
      {notice && <div className="billing-message" role="status">{notice}</div>}
      {loading && <div className="admin-note" role="status" aria-live="polite">Loading {tabs.find((item) => item.id === tab)?.label.toLowerCase()}…</div>}
      <main className="admin-content">
        {tab === "overview" && (
          <>
            <div className="admin-section-heading"><div><h2>Platform overview</h2><p>Members, paid access, and M-Pesa collection activity.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load()}>{loading ? "Refreshing…" : "Refresh"}</button></div>
            <div className="admin-stats">
              {[["Members", overview?.members_total], ["Active members", overview?.members_active], ["Active subscriptions", overview?.subscriptions_active], ["Expiring this week", overview?.subscriptions_expiring], ["Payments awaiting review", overview?.payments_pending], ["Confirmed revenue", overview ? money(overview.revenue_kes) : undefined], ["M-Pesa setup", overview ? (overview.mpesa_ready ? "Ready" : "Needs setup") : undefined]].map(([label, value]) => <article className="admin-stat" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}
            </div>
            <div className="admin-stats admin-usage-stats">
              {[
                ["Uploaded documents", overview?.documents_total], ["Ready documents", overview?.documents_ready],
                ["Failed documents", overview?.documents_failed], ["Chat conversations", overview?.conversations_total],
                ["Chat questions", overview?.questions_total], ["Questions this week", overview?.questions_last_7_days],
                ["Google sign-in", overview ? (overview.google_ready ? "Ready" : "Needs setup") : undefined],
                ["AI responses", overview ? (overview.ai_ready ? "Configured" : "Needs setup") : undefined],
                ["Document storage", overview ? (overview.storage_ready ? "Configured" : "Needs setup") : undefined],
              ].map(([label, value]) => <article className="admin-stat" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}
            </div>
            <p className="admin-note">Revenue counts only payments confirmed by the M-Pesa callback. Reconcile any payment marked for review before granting access.</p>
          </>
        )}
        {tab === "security" && <><div className="admin-section-heading"><div><h2>Administrator security</h2><p>Set up a TOTP authenticator for admin sign-in.</p></div></div><AdminSecuritySettings token={token}/></>}
        {tab === "audit" && <><div className="admin-section-heading"><div><h2>Permanent platform audit log</h2><p>Append-only records of admin actions, consent, data exports, deletions, and security events.</p></div><button className="admin-secondary" disabled={loading} onClick={()=>void load('audit')}>Refresh</button></div><div className="admin-list">{auditEvents.map(item=><article className="admin-row" key={item.id}><div className="admin-row-main"><strong>{item.action.replaceAll('_',' ')}</strong><span>{item.actor_email??'System'} · {item.resource_type}{item.resource_id?` · ${item.resource_id}`:''}</span><small>{JSON.stringify(item.details)}</small></div><time>{new Date(item.created_at).toLocaleString()}</time></article>)}{!loading&&auditEvents.length===0&&<p className="admin-note">No platform audit events recorded.</p>}</div></>}
        {tab === "members" && <>
          <div className="admin-section-heading"><div><h2>Members</h2><p>Review accounts and control workspace access.</p></div></div>
          <div className="admin-list">{members.map((member) => <article className="admin-row" key={member.id}><div className="admin-row-main"><strong>{member.full_name}{member.is_superuser && <span className="admin-tag">Admin</span>}</strong><span>{member.email}</span><small>{member.current_plan ?? "No plan"} · {member.subscription_status ?? "No subscription"}{member.expires_at ? ` · expires ${date(member.expires_at)}` : ""}</small></div><button className="admin-secondary" disabled={busy || member.is_superuser} onClick={() => void mutate(`/admin/members/${member.id}`, "PATCH", { is_active: !member.is_active })}>{member.is_active ? "Disable" : "Enable"}</button></article>)}{!loading && members.length === 0 && <p className="admin-note">No members found.</p>}</div>
        </>}
        {tab === "activity" && <>
          <div className="admin-section-heading"><div><h2>Recent platform activity</h2><p>Registrations, document processing, chatbot questions, and payment events. Chat and document contents stay private.</p></div></div>
          <div className="admin-list">{activities.map((event) => <article className="admin-row activity-row" key={event.id}><div className="activity-kind" aria-hidden="true">{event.kind === "document" ? <FileText size={18} /> : event.kind === "chat" ? <MessageCircle size={18} /> : <Activity size={18} />}</div><div className="admin-row-main"><strong>{event.summary}</strong><span>{event.member_name} · {event.member_email}</span></div><time>{new Date(event.created_at).toLocaleString()}</time></article>)}{!loading && activities.length === 0 && <p className="admin-note">No platform activity yet.</p>}</div>
        </>}
        {tab === "plans" && <>
          <div className="admin-section-heading"><div><h2>Subscription plans</h2><p>Set the monthly price and duration members will pay by M-Pesa.</p></div></div>
          <form className="admin-plan-form" onSubmit={createPlan}>
            <h3><Plus size={17} /> Add a plan</h3>
            <label>Plan name<input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="Monthly access" /></label>
            <label>Description<input maxLength={1000} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Full access to DocuMind AI" /></label>
            <div className="admin-form-pair"><label>Price in KSh<input required type="number" min="1" max="1000000" step="1" value={price} onChange={(e) => setPrice(e.target.value)} /></label><label>Duration in days<input required type="number" min="1" max="366" value={duration} onChange={(e) => setDuration(e.target.value)} /></label></div>
            <button className="admin-primary" disabled={busy}>Create plan</button>
          </form>
          <div className="admin-plan-list">{plans.map((plan) => <article className="admin-plan-card" key={plan.id}><div><strong>{plan.name}</strong><p>{plan.description || "No description"}</p><b>{money(plan.price_kes)} <small>/ {plan.duration_days} days</small></b></div><div className="admin-plan-actions"><span className={plan.is_active ? "status-active" : "status-inactive"}>{plan.is_active ? "Available" : "Hidden"}</span><button className="admin-secondary" disabled={busy} onClick={() => { const value = window.prompt("Monthly plan price in KSh", String(plan.price_kes)); if (value && /^\d+$/.test(value)) void mutate(`/admin/plans/${plan.id}`, "PATCH", { price_kes: Number(value) }); }}>Edit price</button><button className="admin-secondary" disabled={busy} onClick={() => void mutate(`/admin/plans/${plan.id}`, "PATCH", { is_active: !plan.is_active })}>{plan.is_active ? "Hide" : "Publish"}</button></div></article>)}</div>
        </>}
        {tab === "subscriptions" && <>
          <div className="admin-section-heading"><div><h2>Subscriptions</h2><p>Current and previous membership periods.</p></div></div>
          <div className="admin-list">{subscriptions.map((subscription) => <article className="admin-row" key={subscription.id}><div className="admin-row-main"><strong>{subscription.full_name} · {subscription.plan_name}</strong><span>{subscription.email} · {money(subscription.price_kes)}</span><small>{subscription.status} · expires {date(subscription.expires_at)}</small></div>{subscription.status === "active" && <button className="admin-secondary" disabled={busy} onClick={() => void mutate(`/admin/subscriptions/${subscription.id}`, "PATCH", { status: "cancelled" })}>Cancel</button>}</article>)}{!loading && subscriptions.length === 0 && <p className="admin-note">No subscriptions yet.</p>}</div>
        </>}
        {tab === "payments" && <>
          <div className="admin-section-heading"><div><h2>M-Pesa payments</h2><p>Payment requests and confirmed receipts.</p></div></div>
          <div className="admin-list">{payments.map((payment) => <article className="admin-row" key={payment.id}><div className="admin-row-main"><strong>{payment.full_name} · {money(payment.amount_kes)}</strong><span>{payment.email} · {payment.phone_number}</span><small>{payment.status}{payment.mpesa_receipt ? ` · receipt ${payment.mpesa_receipt}` : ""}{payment.result_description ? ` · ${payment.result_description}` : ""}</small></div><time>{date(payment.created_at)}</time></article>)}{!loading && payments.length === 0 && <p className="admin-note">No M-Pesa payments yet.</p>}</div>
        </>}
        {tab === "payment-recovery" && <>
          <div className="admin-section-heading"><div><h2>Payment recovery</h2><p>Review claims manually. Suggested matches are based on recorded phone, receipt, and payment time; they are not proof of payment. This form never grants access by itself.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load("payment-recovery")}>{loading ? "Loading…" : "Refresh"}</button></div>
          <div className="payment-recovery-admin-list">{paymentRecovery.map((recovery) => <PaymentRecoveryCard key={recovery.id} recovery={recovery} plans={plans} busy={busy} onReview={(action, payload) => void reviewPaymentRecovery(recovery.id, action, payload)} />)}{!loading && paymentRecovery.length === 0 && <p className="admin-note">No payment recovery requests have been submitted.</p>}</div>
          <section className="recovery-audit-section"><h2>Decision audit</h2><p>Administrator actions are recorded with the request, decision, reason, and time.</p><div className="admin-list">{recoveryAudit.map((entry) => <article className="admin-row" key={entry.id}><div className="admin-row-main"><strong>{entry.action === "payment_recovery_access_granted" ? "Access granted" : "Request rejected"}</strong><span>{entry.admin_email ?? `Administrator ${entry.admin_user_id ?? "removed"}`} · request {entry.payment_recovery_request_id}</span>{entry.reason && <small>{entry.reason}</small>}</div><time>{new Date(entry.created_at).toLocaleString()}</time></article>)}{!loading && recoveryAudit.length === 0 && <p className="admin-note">No recovery decisions have been recorded.</p>}</div></section>
        </>}
        {tab === "jobs" && <>
          <div className="admin-section-heading"><div><h2>Background jobs</h2><p>Document indexing, reminders, privacy exports, and deletion run on the worker. Failed jobs show an error and supported jobs can be queued again.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load("jobs")}>Refresh</button></div>
          <div className="admin-stats job-counts">{(["queued", "running", "done", "failed"] as const).map((status) => <article className="admin-stat" key={status}><span>{status === "done" ? "Done" : status[0].toUpperCase() + status.slice(1)}</span><strong>{jobQueue?.counts[status] ?? "—"}</strong></article>)}</div>
          <h3>Last 50 failed jobs</h3>
          <div className="admin-list">{jobQueue?.failed.map((job) => <article className="admin-row job-row" key={job.id}><div className="admin-row-main"><strong>{job.document_name ?? (job.type.includes("user_data") ? "Personal data operation" : job.type.includes("organization_data") ? "Organization data operation" : "Document removed")}</strong><span>{job.type} · attempts {job.attempts}/{job.max_attempts}</span><small className="job-error">{job.last_error ?? "Processing failed without a detailed message."}</small><small>Updated {new Date(job.updated_at).toLocaleString()} · Job {job.id}</small></div><button className="admin-primary" type="button" disabled={busy || !retryableJobTypes.has(job.type) || (!job.document_id && !job.library_document_id && !retryableJobTypes.has(job.type))} onClick={() => void mutate(`/admin/jobs/${job.id}/retry`, "POST")}>{busy ? "Queuing…" : "Retry"}</button></article>)}{!loading && (jobQueue?.failed.length ?? 0) === 0 && <p className="admin-note">No failed jobs.</p>}</div>
        </>}
        {tab === "answer-reports" && <>
          <div className="admin-section-heading"><div><h2>Reported chatbot answers</h2><p>Reports include the submitted question, answer, cited passages, and model version for review.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load("answer-reports")}>Refresh</button></div>
          <div className="admin-list">{answerReports.map((report) => <article className="admin-row answer-report" key={report.id}><div className="admin-row-main"><strong>{report.member_name} · {report.member_email}</strong><small>{new Date(report.created_at).toLocaleString()} · {report.model_version} · {report.status}</small><h3>Question</h3><p>{report.question}</p><h3>Answer</h3><p>{report.answer}</p>{report.comment && <p><strong>Member’s note:</strong> {report.comment}</p>}<h3>Stored sources</h3>{report.sources.map((source,i)=><blockquote key={`${source.filename}-${i}`}>[{i+1}] {source.filename}{source.page_number ? ` · page ${source.page_number}` : ''}: {source.excerpt}</blockquote>)}{report.review_note&&<p><strong>Review note:</strong> {report.review_note}</p>}</div>{report.status === 'new' && <button className="admin-primary" type="button" disabled={busy} onClick={()=>void reviewAnswerReport(report)}>Mark reviewed</button>}</article>)}{!loading&&answerReports.length===0&&<p className="admin-note">No reported answers.</p>}</div>
        </>}
        {tab === "library" && <>
          <div className="admin-section-heading"><div><h2>Shared Kenyan library</h2><p>Only add direct official document links after checking permission and reuse terms. The system does not crawl publisher sites.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load("library")}>Refresh</button></div>
          <form className="admin-library-form" onSubmit={(event) => void addLibraryDocument(event)}>
            <h3>Upload or replace an official document</h3>
            <label>Collection<select required value={libraryForm.collection_id} onChange={(e) => setLibraryForm({ ...libraryForm, collection_id: e.target.value })}><option value="">Choose a collection</option>{libraryCollections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select></label>
            {([['title', 'Document title'], ['short_name', 'Stable document name'], ['source_url', 'Direct official HTTPS PDF, TXT, or DOCX URL'], ['publisher', 'Publisher'], ['version_label', 'Version / effective date label']] as const).map(([key, label]) => <label key={key}>{label}<input required value={libraryForm[key]} onChange={(e) => setLibraryForm({ ...libraryForm, [key]: e.target.value })} /></label>)}
            <label>Official file (PDF, TXT, or DOCX; max 50 MB)<input required type="file" accept=".pdf,.txt,.docx,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => setLibraryFile(e.target.files?.[0] ?? null)} /></label>
            {notice && <p role="status">{notice}</p>}<button className="admin-primary" disabled={busy}>{busy ? "Queuing…" : "Add and index"}</button>
          </form>
          <h3>Library documents and versions</h3><div className="admin-list">{libraryDocuments.map((doc) => <article className="admin-row" key={doc.id}><div className="admin-row-main"><strong>{doc.title} · {doc.version_label}</strong><span>{doc.collection_name} · {doc.publisher} · {doc.is_current ? "Current" : "Historical"} · {doc.status}</span>{doc.processing_error && <small className="job-error">{doc.processing_error}</small>}<small>{doc.source_url}</small>{libraryVersions[doc.id]?.map(v=><small key={v.id}>Version: {v.version_label} · {v.is_current ? "Current" : "Historical"} · {v.status} · {date(v.created_at)}</small>)}</div><div className="admin-row-actions"><button className="admin-secondary" type="button" disabled={busy} onClick={() => void mutate(`/admin/library/documents/${doc.id}/reindex`, "POST")}>Re-index</button><button className="admin-secondary" type="button" onClick={async()=>{try{setLibraryVersions({...libraryVersions,[doc.id]:await request<LibraryVersion[]>(`/admin/library/documents/${doc.id}/versions`,token)});}catch(e){setError(getErrorMessage(e));}}}>Versions</button></div></article>)}{libraryDocuments.length === 0 && <p className="admin-note">No library documents have been added yet.</p>}</div>
        </>}
      </main>
    </div>
  );
}

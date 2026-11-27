import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Activity, ArrowLeft, BadgeCheck, CreditCard, FileText, LayoutDashboard, MessageCircle, Package, Plus, Users } from "lucide-react";
import { getErrorMessage, request } from "./api";

type Tab = "overview" | "members" | "activity" | "plans" | "subscriptions" | "payments" | "payment-recovery";
type Overview = { members_total: number; members_active: number; documents_total: number; documents_ready: number; documents_failed: number; conversations_total: number; questions_total: number; questions_last_7_days: number; subscriptions_active: number; subscriptions_expiring: number; payments_total: number; payments_pending: number; revenue_kes: number; mpesa_ready: boolean; google_ready: boolean; ai_ready: boolean; storage_ready: boolean };
type Plan = { id: string; name: string; description: string; price_kes: number; duration_days: number; is_active: boolean };
type Member = { id: string; full_name: string; email: string; is_active: boolean; is_superuser: boolean; current_plan: string | null; subscription_status: string | null; expires_at: string | null; created_at: string };
type Subscription = { id: string; full_name: string; email: string; plan_name: string; price_kes: number; status: string; expires_at: string | null; created_at: string };
type Payment = { id: string; full_name: string; email: string; amount_kes: number; phone_number: string; status: string; mpesa_receipt: string | null; result_description: string | null; created_at: string };
type ActivityEvent = { id: string; kind: string; member_name: string; member_email: string; summary: string; created_at: string };
type RecoveryMatch = { payment_id: string; plan_id: string; member_name: string; member_email: string; plan_name: string; amount_kes: number; phone_number: string; status: string; mpesa_receipt: string | null; created_at: string; match_reason: string };
type PaymentRecovery = { id: string; user_id: string; member_name: string; member_email: string; phone_number: string; paid_at: string; mpesa_message: string; status: string; matched_payment_id: string | null; granted_subscription_id: string | null; reviewed_by_user_id: string | null; rejection_reason: string | null; admin_note: string | null; created_at: string; reviewed_at: string | null; matches: RecoveryMatch[] };
type RecoveryAudit = { id: string; admin_user_id: string | null; admin_email: string | null; payment_recovery_request_id: string | null; action: string; reason: string | null; details: string | null; created_at: string };

const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "members", label: "Members", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "plans", label: "Plans", icon: Package },
  { id: "subscriptions", label: "Subscriptions", icon: BadgeCheck },
  { id: "payments", label: "Payments", icon: CreditCard },
  { id: "payment-recovery", label: "Payment recovery", icon: CreditCard },
];

function money(amount: number) { return `KSh ${amount.toLocaleString()}`; }
function date(value: string | null) { return value ? new Date(value).toLocaleDateString() : "—"; }

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
      await load(tab);
      if (tab === "plans") await load("overview");
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusy(false); }
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await mutate("/admin/plans", "POST", { name, description, price_kes: Number(price), duration_days: Number(duration) });
    setName(""); setDescription(""); setPrice(""); setDuration("30");
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
      </main>
    </div>
  );
}

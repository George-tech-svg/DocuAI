import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArrowLeft, BadgeCheck, CreditCard, LayoutDashboard, Package, Plus, Users } from "lucide-react";
import { getErrorMessage, request } from "./api";

type Tab = "overview" | "members" | "plans" | "subscriptions" | "payments";
type Overview = { members_total: number; members_active: number; subscriptions_active: number; subscriptions_expiring: number; payments_total: number; payments_pending: number; revenue_kes: number; mpesa_ready: boolean };
type Plan = { id: string; name: string; description: string; price_kes: number; duration_days: number; is_active: boolean };
type Member = { id: string; full_name: string; email: string; is_active: boolean; is_superuser: boolean; current_plan: string | null; subscription_status: string | null; expires_at: string | null; created_at: string };
type Subscription = { id: string; full_name: string; email: string; plan_name: string; price_kes: number; status: string; expires_at: string | null; created_at: string };
type Payment = { id: string; full_name: string; email: string; amount_kes: number; phone_number: string; status: string; mpesa_receipt: string | null; result_description: string | null; created_at: string };

const tabs: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "members", label: "Members", icon: Users },
  { id: "plans", label: "Plans", icon: Package },
  { id: "subscriptions", label: "Subscriptions", icon: BadgeCheck },
  { id: "payments", label: "Payments", icon: CreditCard },
];

function money(amount: number) { return `KSh ${amount.toLocaleString()}`; }
function date(value: string | null) { return value ? new Date(value).toLocaleDateString() : "—"; }

export default function AdminDashboard({ token, onBack }: { token: string; onBack: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [error, setError] = useState("");
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
      if (nextTab === "plans") setPlans(await request<Plan[]>("/admin/plans", token));
      if (nextTab === "subscriptions") setSubscriptions(await request<Subscription[]>("/admin/subscriptions", token));
      if (nextTab === "payments") setPayments(await request<Payment[]>("/admin/payments", token));
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
      {loading && <div className="admin-note" role="status" aria-live="polite">Loading {tabs.find((item) => item.id === tab)?.label.toLowerCase()}…</div>}
      <main className="admin-content">
        {tab === "overview" && (
          <>
            <div className="admin-section-heading"><div><h2>Platform overview</h2><p>Members, paid access, and M-Pesa collection activity.</p></div><button className="admin-secondary" disabled={loading} onClick={() => void load()}>{loading ? "Refreshing…" : "Refresh"}</button></div>
            <div className="admin-stats">
              {[["Members", overview?.members_total], ["Active members", overview?.members_active], ["Active subscriptions", overview?.subscriptions_active], ["Expiring this week", overview?.subscriptions_expiring], ["Payments awaiting review", overview?.payments_pending], ["Confirmed revenue", overview ? money(overview.revenue_kes) : undefined], ["M-Pesa setup", overview ? (overview.mpesa_ready ? "Ready" : "Needs setup") : undefined]].map(([label, value]) => <article className="admin-stat" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}
            </div>
            <p className="admin-note">Revenue counts only payments confirmed by the M-Pesa callback. Reconcile any payment marked for review before granting access.</p>
          </>
        )}
        {tab === "members" && <>
          <div className="admin-section-heading"><div><h2>Members</h2><p>Review accounts and control workspace access.</p></div></div>
          <div className="admin-list">{members.map((member) => <article className="admin-row" key={member.id}><div className="admin-row-main"><strong>{member.full_name}{member.is_superuser && <span className="admin-tag">Admin</span>}</strong><span>{member.email}</span><small>{member.current_plan ?? "No plan"} · {member.subscription_status ?? "No subscription"}{member.expires_at ? ` · expires ${date(member.expires_at)}` : ""}</small></div><button className="admin-secondary" disabled={busy || member.is_superuser} onClick={() => void mutate(`/admin/members/${member.id}`, "PATCH", { is_active: !member.is_active })}>{member.is_active ? "Disable" : "Enable"}</button></article>)}{!loading && members.length === 0 && <p className="admin-note">No members found.</p>}</div>
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
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArrowLeft, CheckCircle2, CreditCard, RefreshCw } from "lucide-react";
import { getErrorMessage, request } from "./api";

type Plan = { id: string; name: string; description: string; price_kes: number; duration_days: number };
type Billing = { subscription: { plan_name: string; status: string; expires_at: string | null } | null; payments: { id: string; amount_kes: number; status: string; mpesa_receipt: string | null; result_description: string | null; created_at: string }[]; mpesa_ready: boolean };

export default function BillingPage({ token, onBack }: { token: string; onBack: () => void }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyPlanId, setBusyPlanId] = useState("");

  async function refresh() {
    setError("");
    try {
      const [availablePlans, current] = await Promise.all([
        request<Plan[]>("/billing/plans", token),
        request<Billing>("/billing/me", token),
      ]);
      setPlans(availablePlans);
      setBilling(current);
    } catch (e) { setError(getErrorMessage(e)); }
  }

  useEffect(() => { void refresh(); }, [token]);

  async function startPayment(event: FormEvent<HTMLFormElement>, planId: string) {
    event.preventDefault();
    setBusyPlanId(planId); setError(""); setMessage("");
    try {
      const response = await request<{ customer_message: string }>("/billing/checkout", token, {
        method: "POST", body: JSON.stringify({ plan_id: planId, phone_number: phone }),
      });
      setMessage(response.customer_message || "Approve the M-Pesa prompt on your phone. Your plan begins once the payment is confirmed.");
      await refresh();
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setBusyPlanId(""); }
  }

  return (
    <div className="admin-shell billing-shell">
      <header className="admin-header">
        <button className="admin-back" type="button" onClick={onBack}><ArrowLeft size={17} /> Workspace</button>
        <div><span>YOUR ACCOUNT</span><h1>Plan &amp; billing</h1></div>
        <button className="admin-secondary" type="button" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button>
      </header>
      {error && <div className="admin-error" role="alert">{error}</div>}
      {message && <div className="billing-message" role="status"><CheckCircle2 size={17} />{message}</div>}
      <main className="admin-content">
        <section className="billing-current">
          <div><span>Current access</span><h2>{billing?.subscription?.plan_name ?? "No active plan"}</h2></div>
          <p>{billing?.subscription ? `${billing.subscription.status}${billing.subscription.expires_at ? ` · valid through ${new Date(billing.subscription.expires_at).toLocaleDateString()}` : ""}` : "Choose a plan below to start using DocuMind AI."}</p>
        </section>
        {!billing?.mpesa_ready && <div className="admin-note">M-Pesa checkout is not enabled yet. The platform administrator needs to finish Daraja configuration before members can pay.</div>}
        <div className="admin-section-heading"><div><h2>Monthly plans</h2><p>Each month, you’ll receive a payment prompt and access renews after confirmation.</p></div></div>
        <label className="billing-phone">M-Pesa phone number<input inputMode="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="0712 345 678" /></label>
        <div className="billing-plan-list">{plans.map((plan) => <article className="admin-plan-card" key={plan.id}><div><strong>{plan.name}</strong><p>{plan.description}</p><b>KSh {plan.price_kes.toLocaleString()} <small>/ {plan.duration_days} days</small></b></div><form onSubmit={(event) => void startPayment(event, plan.id)}><button className="admin-primary" type="submit" disabled={!billing?.mpesa_ready || !phone.trim() || !!busyPlanId}><CreditCard size={16} />{busyPlanId === plan.id ? "Sending prompt…" : "Pay with M-Pesa"}</button></form></article>)}</div>
        {plans.length === 0 && <p className="admin-note">No subscription plans are available yet.</p>}
        <div className="admin-section-heading"><div><h2>Recent payments</h2><p>Pending prompts are not treated as successful payments.</p></div></div>
        <div className="admin-list">{billing?.payments.map((payment) => <article className="admin-row" key={payment.id}><div className="admin-row-main"><strong>KSh {payment.amount_kes.toLocaleString()} · {payment.status}</strong><small>{payment.mpesa_receipt ? `M-Pesa receipt ${payment.mpesa_receipt}` : payment.result_description || "Awaiting M-Pesa confirmation"}</small></div><time>{new Date(payment.created_at).toLocaleDateString()}</time></article>)}</div>
      </main>
    </div>
  );
}

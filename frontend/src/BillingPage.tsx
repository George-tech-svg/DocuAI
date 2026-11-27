import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArrowLeft, CheckCircle2, CreditCard, RefreshCw } from "lucide-react";
import { getErrorMessage, request } from "./api";

type Plan = { id: string; name: string; description: string; price_kes: number; duration_days: number };
type Billing = { subscription: { plan_name: string; status: string; expires_at: string | null } | null; payments: { id: string; amount_kes: number; status: string; mpesa_receipt: string | null; result_description: string | null; created_at: string }[]; mpesa_ready: boolean };
type RecoveryRequest = { id: string; phone_number: string; paid_at: string; mpesa_message: string; status: string; rejection_reason: string | null; created_at: string; reviewed_at: string | null };

function localDateTimeValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export default function BillingPage({ token, onBack }: { token: string; onBack: () => void }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyPlanId, setBusyPlanId] = useState("");
  const [recoveryRequests, setRecoveryRequests] = useState<RecoveryRequest[]>([]);
  const [recoveryPhone, setRecoveryPhone] = useState("");
  const [paidAt, setPaidAt] = useState(localDateTimeValue);
  const [mpesaMessage, setMpesaMessage] = useState("");
  const [recoveryBusy, setRecoveryBusy] = useState(false);

  async function refresh() {
    setError("");
    setLoading(true);
    try {
      const [availablePlans, current, requests] = await Promise.all([
        request<Plan[]>("/billing/plans", token),
        request<Billing>("/billing/me", token),
        request<RecoveryRequest[]>("/billing/payment-recovery", token),
      ]);
      setPlans(availablePlans);
      setBilling(current);
      setRecoveryRequests(requests);
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setLoading(false); }
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

  async function submitRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRecoveryBusy(true); setError(""); setMessage("");
    try {
      const created = await request<RecoveryRequest>("/billing/payment-recovery", token, {
        method: "POST",
        body: JSON.stringify({
          phone_number: recoveryPhone,
          paid_at: new Date(paidAt).toISOString(),
          mpesa_message: mpesaMessage.trim(),
        }),
      });
      setRecoveryRequests((current) => [created, ...current]);
      setMpesaMessage("");
      setMessage("Your payment recovery request was submitted for administrator review. Access is not granted until it is reviewed.");
    } catch (e) { setError(getErrorMessage(e)); }
    finally { setRecoveryBusy(false); }
  }
  const hasPendingRecovery = recoveryRequests.some((request) => request.status === "pending");

  return (
    <div className="admin-shell billing-shell">
      <header className="admin-header">
        <button className="admin-back" type="button" onClick={onBack}><ArrowLeft size={17} /> Workspace</button>
        <div><span>YOUR ACCOUNT</span><h1>Plan &amp; billing</h1></div>
        <button className="admin-secondary" type="button" disabled={loading} onClick={() => void refresh()}><RefreshCw size={15} />{loading ? "Loading…" : "Refresh"}</button>
      </header>
      {error && <div className="admin-error" role="alert">{error}<button className="admin-secondary" type="button" onClick={() => void refresh()} disabled={loading}>Try again</button></div>}
      {loading && <div className="admin-note" role="status" aria-live="polite">Loading your plan and payment details…</div>}
      {message && <div className="billing-message" role="status"><CheckCircle2 size={17} />{message}</div>}
      <main className="admin-content">
        <section className="billing-current">
          <div><span>Current access</span><h2>{billing?.subscription?.plan_name ?? "No active plan"}</h2></div>
          <p>{billing?.subscription ? `${billing.subscription.status}${billing.subscription.expires_at ? ` · valid through ${new Date(billing.subscription.expires_at).toLocaleDateString()}` : ""}` : "Choose a plan below to start using DocuMind AI."}</p>
        </section>
        {!loading && billing && !billing.mpesa_ready && <div className="admin-note billing-warning" role="status">M-Pesa checkout is not enabled yet. The platform administrator needs to finish Daraja configuration before members can pay.</div>}
        <div className="admin-section-heading"><div><h2>Monthly plans</h2><p>Enter your M-Pesa number, choose a plan, then tap Pay with M-Pesa. A payment prompt will be sent to your phone to approve. Access starts after payment is confirmed.</p></div></div>
        <label className="billing-phone">M-Pesa phone number<input inputMode="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="0712 345 678" /></label>
        <div className="billing-plan-list">{plans.map((plan) => <article className="admin-plan-card" key={plan.id}><div><strong>{plan.name}</strong><p>{plan.description}</p><b>KSh {plan.price_kes.toLocaleString()} <small>/ {plan.duration_days} days</small></b></div><form onSubmit={(event) => void startPayment(event, plan.id)}><button className="admin-primary" type="submit" disabled={!billing?.mpesa_ready || !phone.trim() || !!busyPlanId}><CreditCard size={16} />{busyPlanId === plan.id ? "Sending prompt…" : "Pay with M-Pesa"}</button></form></article>)}</div>
        {!loading && plans.length === 0 && <p className="admin-note billing-empty">No subscription plans are available yet.</p>}
        <div className="admin-section-heading"><div><h2>Recent payments</h2><p>Pending prompts are not treated as successful payments.</p></div></div>
        <div className="admin-list">{billing?.payments.map((payment) => <article className="admin-row" key={payment.id}><div className="admin-row-main"><strong>KSh {payment.amount_kes.toLocaleString()} · {payment.status}</strong><small>{payment.mpesa_receipt ? `M-Pesa receipt ${payment.mpesa_receipt}` : payment.result_description || "Awaiting M-Pesa confirmation"}</small></div><time>{new Date(payment.created_at).toLocaleDateString()}</time></article>)}</div>

        <section className="payment-recovery-section" aria-labelledby="payment-recovery-title">
          <div className="admin-section-heading"><div><h2 id="payment-recovery-title">I paid but don’t have access</h2><p>Send your payment details for a manual review. Submitting this form does not grant access.</p></div></div>
          {hasPendingRecovery && <p className="admin-note" role="status">You already have a request waiting for review. You can submit another after it has been resolved.</p>}
          <form className="payment-recovery-form" onSubmit={(event) => void submitRecovery(event)}>
            <label>M-Pesa phone number<input required inputMode="tel" autoComplete="tel" minLength={9} maxLength={16} value={recoveryPhone} onChange={(event) => setRecoveryPhone(event.target.value)} placeholder="0712 345 678" /></label>
            <label>Approximate payment date and time<input required type="datetime-local" value={paidAt} max={localDateTimeValue()} onChange={(event) => setPaidAt(event.target.value)} /></label>
            <label className="recovery-message-field">Paste the M-Pesa confirmation message or receipt<textarea required minLength={5} maxLength={2000} rows={4} value={mpesaMessage} onChange={(event) => setMpesaMessage(event.target.value)} placeholder="Include the receipt code, amount, and payment details from the M-Pesa message." /></label>
            <button className="admin-primary" type="submit" disabled={recoveryBusy || loading || hasPendingRecovery}>{recoveryBusy ? "Submitting request…" : hasPendingRecovery ? "Request awaiting review" : "Submit for review"}</button>
          </form>
          <div className="recovery-request-list">
            <h3>Your recovery requests</h3>
            {recoveryRequests.map((request) => <article className="admin-row" key={request.id}>
              <div className="admin-row-main"><strong>{request.status === "pending" ? "Waiting for review" : request.status === "granted" ? "Access granted" : "Request rejected"}</strong><span>{request.phone_number} · payment time {new Date(request.paid_at).toLocaleString()}</span>{request.rejection_reason && <small>Reason: {request.rejection_reason}</small>}</div>
              <time>Submitted {new Date(request.created_at).toLocaleDateString()}</time>
            </article>)}
            {!loading && recoveryRequests.length === 0 && <p className="admin-note">No payment recovery requests submitted.</p>}
          </div>
        </section>
      </main>
    </div>
  );
}

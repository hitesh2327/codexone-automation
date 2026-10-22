import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Lock, Pencil } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";

export type BillingDetails = { name: string; country: string | null; state: string | null; gstin: string | null; complete: boolean };

type Tax = { name: string; rate: number; amount: number };
type Line = { label: string; from: number; to: number; amount: number };
export type Quote = {
  kind: "new" | "upgrade" | "downgrade" | "resume";
  plan: string; plan_name: string; interval: "month" | "year"; quote_at: number; currency: string;
  lines: Line[]; taxable: number; taxes: Tax[]; total_now: number;
  effective_at: number; renews_at: number; renewal_total: number; renewal_taxes: Tax[]; gst_rate: number;
};
type Checkout = { mode: "razorpay"; key_id: string; subscription_id: string; kind: string; plan: string;
  total_now: number; email: string; name: string };
type RazorpaySuccess = { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string };

declare global {
  interface Window { Razorpay?: new (options: Record<string, unknown>) => { open: () => void } }
}

const COUNTRIES: [string, string][] = [
  ["IN", "India"], ["US", "United States"], ["GB", "United Kingdom"], ["CA", "Canada"], ["AU", "Australia"],
  ["AE", "United Arab Emirates"], ["SG", "Singapore"], ["DE", "Germany"], ["FR", "France"], ["NL", "Netherlands"],
  ["ZZ", "Another country"],
];

/** Downgrades and resuming a cancelled plan start when the paid period ends; nothing is charged today. */
function isScheduled(q: Quote): boolean {
  return q.kind === "downgrade" || q.kind === "resume";
}

export function rupees(paise: number): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 }).format(paise / 100);
}

function day(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/** Razorpay's checkout script, loaded once, the first time someone pays. */
function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load the payment window. Check your connection and try again."));
    document.body.appendChild(s);
  });
}

function TaxRows({ taxes }: { taxes: Tax[] }) {
  return (
    <>
      {taxes.map((t) => (
        <div key={t.name} className="flex justify-between text-muted-foreground">
          <span>{t.name} {t.rate}%</span><span className="tabular-nums">{rupees(t.amount)}</span>
        </div>
      ))}
    </>
  );
}

/**
 * Review a plan change before paying: billing details (country, state, GSTIN decide the GST), an itemised
 * breakdown from the server's quote (prorated lines, taxable value, CGST/SGST or IGST, total due now), what the
 * renewal will cost, then Razorpay Checkout. Nothing is charged until the user confirms here and in Razorpay.
 */
export function PlanReviewDialog({ plan, interval, open, onOpenChange, onDone }: {
  plan: { id: string; name: string } | null; interval: "month" | "year"; open: boolean;
  onOpenChange: (open: boolean) => void; onDone: () => void;
}) {
  const [step, setStep] = useState<"details" | "review">("review");
  const [details, setDetails] = useState<BillingDetails | null>(null);
  const [states, setStates] = useState<{ code: string; name: string }[]>([]);
  const [form, setForm] = useState({ name: "", country: "IN", state: "", gstin: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadQuote() {
    if (!plan) return;
    setQuote(null);
    try {
      setQuote(await api<Quote>("/api/subscription/quote", { method: "POST", body: { plan_id: plan.id, interval } }));
      setStep("review");
    } catch (err) {
      if (err instanceof ApiError && err.code === "billing_details_required") { setStep("details"); return; }
      toast.error(err instanceof ApiError ? err.message : "Couldn't price that plan. Try again.");
      onOpenChange(false);
    }
  }

  useEffect(() => {
    if (!open || !plan) return;
    setFormError(null);
    Promise.all([
      api<{ billing: BillingDetails }>("/api/subscription/status"),
      states.length ? Promise.resolve({ states }) : api<{ states: { code: string; name: string }[] }>("/api/subscription/states"),
    ]).then(([st, sts]) => {
      setStates(sts.states);
      setDetails(st.billing);
      setForm({ name: st.billing.name || "", country: st.billing.country || "IN", state: st.billing.state || "", gstin: st.billing.gstin || "" });
      if (st.billing.complete) void loadQuote(); else setStep("details");
    }).catch(() => { toast.error("Couldn't load your billing details."); onOpenChange(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, plan?.id, interval]);

  async function saveDetails() {
    if (!form.country) { setFormError("Choose your country."); return; }
    if (form.country === "IN" && !form.state) { setFormError("Choose your state. It decides how GST is split."); return; }
    setBusy(true);
    setFormError(null);
    try {
      const saved = await api<BillingDetails>("/api/subscription/billing-details", {
        method: "PUT", body: { name: form.name, country: form.country, state: form.country === "IN" ? form.state : null,
          gstin: form.country === "IN" ? form.gstin.trim() || null : null },
      });
      setDetails(saved);
      await loadQuote();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't save your details. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function pay() {
    if (!plan || !quote) return;
    setBusy(true);
    try {
      const co = await api<Checkout>("/api/subscription/checkout", {
        method: "POST", body: { plan_id: plan.id, interval, quote_at: quote.quote_at, expected_total: quote.total_now },
      });
      await loadRazorpay();
      if (!window.Razorpay) throw new Error("Couldn't load the payment window.");
      onOpenChange(false);   // Razorpay's window takes over
      new window.Razorpay({
        key: co.key_id,
        subscription_id: co.subscription_id,
        name: "Mintly",
        description: isScheduled(quote) ? `${co.plan} from ${day(quote.effective_at)}` : `${co.plan} plan`,
        prefill: { email: co.email, name: co.name },
        theme: { color: "#34E3A4" },
        handler: (resp: RazorpaySuccess) => {
          api<{ outcome: string }>("/api/subscription/verify", { method: "POST", body: resp })
            .then((v) => {
              toast.success(v.outcome === "scheduled"
                ? `Done. You move to ${co.plan} on ${day(quote.effective_at)}.`
                : v.outcome === "activated" ? `You're on ${co.plan} now.`
                  : "Payment received. Your plan updates as soon as Razorpay confirms it.");
              onDone();
            })
            .catch(() => toast.error("Couldn't confirm the payment. Refresh in a minute to check your plan."));
        },
        modal: { ondismiss: () => toast.info("Payment cancelled. Nothing was charged and your plan didn't change.") },
      }).open();
    } catch (err) {
      if (err instanceof ApiError && (err.code === "quote_changed" || err.code === "quote_expired")) {
        toast.info(err.message);
        await loadQuote();
      } else {
        toast.error(err instanceof ApiError || err instanceof Error ? err.message : "Couldn't start the payment.");
      }
    } finally {
      setBusy(false);
    }
  }

  const per = interval === "year" ? "year" : "month";
  const stateName = states.find((s) => s.code === details?.state)?.name;
  const countryName = COUNTRIES.find(([c]) => c === details?.country)?.[1] ?? details?.country;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{step === "details" ? "Billing details" : "Review your plan"}</DialogTitle>
          <DialogDescription>
            {step === "details"
              ? "Used for your GST invoice. Your state decides whether GST is split into CGST and SGST, or charged as IGST."
              : quote && isScheduled(quote)
                ? `Your current plan stays until ${day(quote.effective_at)}, the end of the period you've paid for.`
                : "Check the amount before you pay. Nothing is charged until you confirm."}
          </DialogDescription>
        </DialogHeader>

        {step === "details" && (
          <div className="grid gap-3">
            <label className="grid gap-1.5 text-xs text-muted-foreground">Name or business name
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name or company" />
            </label>
            <label className="grid gap-1.5 text-xs text-muted-foreground">Country
              <Select value={form.country} onValueChange={(v) => setForm({ ...form, country: v })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{COUNTRIES.map(([c, n]) => <SelectItem key={c} value={c}>{n}</SelectItem>)}</SelectContent>
              </Select>
            </label>
            {form.country === "IN" && (
              <>
                <label className="grid gap-1.5 text-xs text-muted-foreground">State
                  <Select value={form.state} onValueChange={(v) => setForm({ ...form, state: v })}>
                    <SelectTrigger className="w-full"><SelectValue placeholder="Choose your state" /></SelectTrigger>
                    <SelectContent>{states.map((s) => <SelectItem key={s.code} value={s.code}>{s.name}</SelectItem>)}</SelectContent>
                  </Select>
                </label>
                <label className="grid gap-1.5 text-xs text-muted-foreground">GSTIN (optional, for businesses claiming input tax credit)
                  <Input value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value.toUpperCase() })}
                         placeholder="27ABCDE1234F1Z5" maxLength={15} className="font-mono" />
                </label>
              </>
            )}
            {form.country !== "IN" && (
              <p className="text-xs text-muted-foreground">Customers outside India pay no GST.</p>
            )}
            {formError && <p role="alert" className="text-xs text-bad">{formError}</p>}
          </div>
        )}

        {step === "review" && !quote && (
          <div role="status" aria-label="Working out the price" className="grid gap-2.5">
            <Skeleton className="h-3 w-24" />
            <div className="flex justify-between gap-4"><Skeleton className="h-4 w-56" /><Skeleton className="h-4 w-20" /></div>
            <div className="flex justify-between gap-4"><Skeleton className="h-4 w-40" /><Skeleton className="h-4 w-16" /></div>
            <div className="flex justify-between gap-4 border-t border-border pt-2.5"><Skeleton className="h-5 w-28" /><Skeleton className="h-5 w-24" /></div>
            <Skeleton className="h-3 w-64" />
          </div>
        )}

        {step === "review" && quote && (
          <div className="grid gap-4 text-sm">
            {!isScheduled(quote) ? (
              <div className="grid gap-1.5">
                <p className="text-xs text-muted-foreground">Charged today</p>
                {quote.lines.map((l) => (
                  <div key={l.label} className="flex justify-between gap-4">
                    <span>{l.label} <span className="text-muted-foreground">({day(l.from)} – {day(l.to)})</span></span>
                    <span className={l.amount < 0 ? "tabular-nums text-ok" : "tabular-nums"}>{l.amount < 0 ? "−" : ""}{rupees(Math.abs(l.amount))}</span>
                  </div>
                ))}
                {quote.taxes.length > 0 && (
                  <div className="mt-1 flex justify-between border-t border-border pt-2"><span>Taxable value</span><span className="tabular-nums">{rupees(quote.taxable)}</span></div>
                )}
                <TaxRows taxes={quote.taxes} />
                <div className="mt-1 flex justify-between border-t border-border pt-2 text-base font-semibold">
                  <span>Total due now</span><span className="tabular-nums">{rupees(quote.total_now)}</span>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-border bg-raised/40 p-3">
                <p><span className="font-semibold">{quote.plan_name}</span> starts on {day(quote.effective_at)}. <span className="font-semibold">Nothing is charged today.</span></p>
                <p className="mt-1 text-xs text-muted-foreground">Razorpay asks you to approve the new plan now; banks may show a small verification charge that's refunded.</p>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Then {rupees(quote.renewal_total)} every {per} from {day(quote.renews_at)}
              {quote.renewal_taxes.length > 0 ? ` (incl. ${quote.gst_rate}% GST)` : ""}. Cancel anytime.
            </p>
            <div className="flex items-start justify-between gap-3 rounded-lg border border-border p-3 text-xs">
              <div className="grid gap-0.5">
                <span className="text-muted-foreground">Billed to</span>
                <span className="text-foreground">{details?.name || "—"}</span>
                <span className="text-muted-foreground">{[stateName, countryName].filter(Boolean).join(", ")}{details?.gstin ? ` · GSTIN ${details.gstin}` : ""}</span>
                {quote.gst_rate === 0 && details?.country !== "IN" && <span className="text-muted-foreground">No GST: billed as an export of services.</span>}
              </div>
              <button type="button" onClick={() => setStep("details")} className="flex items-center gap-1 text-primary hover:underline">
                <Pencil className="size-3" aria-hidden />Edit
              </button>
            </div>
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Lock className="size-3.5 text-ok" aria-hidden />You'll pay in Razorpay's secure window: UPI, card or netbanking.
            </p>
            <p className="text-xs text-muted-foreground">
              Renews automatically until you cancel. By paying you agree to the{" "}
              <Link to="/legal/terms" target="_blank" className="text-primary underline-offset-4 hover:underline">terms</Link> and the{" "}
              <Link to="/legal/refunds" target="_blank" className="text-primary underline-offset-4 hover:underline">refund and cancellation policy</Link>.
            </p>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          {step === "details" ? (
            <Button onClick={saveDetails} disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : "Continue"}</Button>
          ) : (
            <Button onClick={pay} disabled={busy || !quote}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : !quote ? "Pay"
                : isScheduled(quote) ? "Approve and schedule" : `Pay ${rupees(quote.total_now)}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

import { useEffect, useState } from "react";
import {
  Check,
  CreditCard,
  Crown,
  HelpCircle,
  Loader2,
  Lock,
  Sparkles,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Plan = {
  id: string;
  name: string;
  badge: string;
  price_monthly: number;
  price_yearly: number;
  posts_per_day: number;
  features: string[];
  popular: boolean;
};

type PlansResponse = {
  plans: Plan[];
  payments_enabled: boolean;
};

type StatusResponse = {
  tier: string;
  status: string;
  renews_at: string | null;
  has_subscription: boolean;
  payments_enabled: boolean;
};

type CheckoutResponse =
  | { mode: "razorpay"; key_id: string; subscription_id: string; plan: string; email: string; name: string }
  | { mode: "instant"; ok: boolean; tier: string; status: string; message: string };

type VerifyResponse = { ok: boolean; outcome: string; tier: string; status: string };

type RazorpaySuccess = { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string };

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

const CHECKOUT_JS = "https://checkout.razorpay.com/v1/checkout.js";

/** Razorpay's checkout script, loaded once, the first time someone buys. */
function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = CHECKOUT_JS;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load the payment window. Check your connection and try again."));
    document.body.appendChild(s);
  });
}

const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  past_due: "Payment retrying",
  halted: "Payment failed",
  canceling: "Ends at period end",
  canceled: "Cancelled",
  paused: "Paused",
};

export default function SubscriptionPage() {
  const { user, patchUser } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentTier, setCurrentTier] = useState<string>(user?.subscription_tier || "free");
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [paymentsEnabled, setPaymentsEnabled] = useState(false);
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);

  async function refreshStatus() {
    const st = await api<StatusResponse>("/api/subscription/status");
    setStatus(st);
    setCurrentTier(st.tier);
    setPaymentsEnabled(st.payments_enabled);
    patchUser({ subscription_tier: st.tier, subscription_status: st.status });
    return st;
  }

  useEffect(() => {
    Promise.all([
      api<PlansResponse>("/api/subscription/plans"),
      api<StatusResponse>("/api/subscription/status").catch(() => null),
    ])
      .then(([plansRes, statusRes]) => {
        setPlans(plansRes.plans);
        setPaymentsEnabled(plansRes.payments_enabled);
        if (statusRes) {
          setStatus(statusRes);
          setCurrentTier(statusRes.tier);
        }
      })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Failed to load plans");
      })
      .finally(() => setLoading(false));
  }, []);

  /** After Razorpay says the payment went through: the server checks it with Razorpay and updates the plan. */
  async function confirmPayment(resp: RazorpaySuccess, planName: string) {
    try {
      const v = await api<VerifyResponse>("/api/subscription/verify", { method: "POST", body: resp });
      if (v.outcome === "activated" || v.status === "active") {
        await refreshStatus();
        toast.success(`You're on ${planName} now.`);
      } else {
        // paid, but Razorpay is still settling the first charge: the webhook switches the plan shortly
        toast.info("Payment received. Your plan switches as soon as Razorpay confirms it, usually within a minute.");
        setTimeout(() => { refreshStatus().catch(() => undefined); }, 15000);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't confirm the payment. Refresh in a minute to check your plan.");
    } finally {
      setBusyPlan(null);
    }
  }

  async function handleSelectPlan(planId: string) {
    if (planId === currentTier) {
      toast.info(`You are currently on the ${planId} plan.`);
      return;
    }

    setBusyPlan(planId);
    try {
      const res = await api<CheckoutResponse>("/api/subscription/checkout", {
        method: "POST",
        body: { plan_id: planId, interval },
      });

      if (res.mode === "instant") {
        setCurrentTier(res.tier);
        patchUser({ subscription_tier: res.tier, subscription_status: res.status });
        toast.success(res.message);
        setBusyPlan(null);
        return;
      }

      await loadRazorpay();
      const Razorpay = window.Razorpay;
      if (!Razorpay) throw new Error("Couldn't load the payment window.");
      new Razorpay({
        key: res.key_id,
        subscription_id: res.subscription_id,
        name: "Mintly",
        description: `${res.plan} plan (${interval === "year" ? "yearly" : "monthly"})`,
        prefill: { email: res.email, name: res.name },
        theme: { color: "#34E3A4" },
        handler: (resp: RazorpaySuccess) => { void confirmPayment(resp, res.plan); },
        modal: {
          ondismiss: () => {
            setBusyPlan(null);
            toast.info("Payment cancelled. Your plan didn't change.");
          },
        },
      }).open();
    } catch (err) {
      toast.error(err instanceof ApiError || err instanceof Error ? err.message : "Failed to start checkout");
      setBusyPlan(null);
    }
  }

  async function handleCancel() {
    if (!window.confirm("Cancel your subscription? You keep your plan until the end of the period you've paid for.")) return;
    setCanceling(true);
    try {
      await api("/api/subscription/cancel", { method: "POST" });
      await refreshStatus();
      toast.success("Subscription cancelled. You keep your plan until the end of this period.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't cancel. Try again in a minute.");
    } finally {
      setCanceling(false);
    }
  }

  const statusKey = status?.status ?? "active";
  const renews = status?.renews_at ? new Date(status.renews_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : null;

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[72rem] gap-8 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="06"
          eyebrow="Billing & Scaling"
          title="Plans & Subscription"
          lead="Supercharge your automated content engine. Select the volume and publishing capabilities that match your growth strategy."
        />

        {/* Current status banner */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-raised/50 p-5 backdrop-blur">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Crown className="size-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Current Plan:</span>
                <span className="font-heading font-semibold uppercase tracking-wider text-foreground">
                  {currentTier}
                </span>
                <span className={cn("rounded-full px-2 py-0.5 font-mono text-[10px] uppercase",
                  statusKey === "active" ? "bg-ok/20 text-ok" : "bg-wait/20 text-wait")}>
                  {STATUS_LABEL[statusKey] ?? statusKey}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {renews
                  ? statusKey === "canceling"
                    ? `Your plan stays active until ${renews}, then moves to Free.`
                    : `Renews on ${renews}.`
                  : "All generation jobs, render pipelines, and publishing slots reflect your current tier."}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {paymentsEnabled ? (
              <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                <Lock className="size-3.5 text-ok" />
                <span>Payments by Razorpay</span>
              </div>
            ) : (
              <span className="font-mono text-xs text-wait">Payments aren't set up yet</span>
            )}
            {status?.has_subscription && statusKey !== "canceling" && (
              <Button variant="ghost" size="sm" onClick={handleCancel} disabled={canceling}>
                {canceling ? <Loader2 className="size-4 animate-spin" /> : "Cancel subscription"}
              </Button>
            )}
          </div>
        </div>

        {/* Monthly vs Yearly Switch */}
        <div className="flex flex-col items-center justify-center gap-3 pt-2">
          <div className="inline-flex rounded-lg border border-border bg-raised p-1">
            <button
              type="button"
              onClick={() => setInterval("month")}
              className={cn(
                "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
                interval === "month"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Monthly Billing
            </button>
            <button
              type="button"
              onClick={() => setInterval("year")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
                interval === "year"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Annual Billing
              <span className="rounded-full bg-signal/20 px-1.5 py-0.5 font-mono text-[10px] text-signal font-semibold uppercase">
                Save 20%
              </span>
            </button>
          </div>
        </div>

        {/* Plan Cards Grid */}
        {loading ? (
          <div className="grid gap-6 md:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="shimmer h-96 rounded-xl border border-border" />
            ))}
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-3">
            {plans.map((plan) => {
              const isCurrent = currentTier.toLowerCase() === plan.id.toLowerCase();
              const price = interval === "year" ? Math.round(plan.price_yearly / 12) : plan.price_monthly;
              const isBusy = busyPlan === plan.id;

              return (
                <div
                  key={plan.id}
                  className={cn(
                    "relative flex flex-col justify-between rounded-2xl border p-6 transition-all duration-200",
                    plan.popular
                      ? "border-primary/60 bg-gradient-to-b from-primary/10 via-raised to-background shadow-lg shadow-primary/5"
                      : "border-border bg-raised/30 hover:border-border/80"
                  )}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-0.5 font-mono text-[11px] font-semibold text-primary-foreground shadow">
                        <Sparkles className="size-3" />
                        {plan.badge}
                      </span>
                    </div>
                  )}

                  <div>
                    <div className="flex items-baseline justify-between">
                      <h3 className="font-heading text-xl font-bold tracking-tight">{plan.name}</h3>
                      {!plan.popular && (
                        <span className="font-mono text-[11px] text-muted-foreground">{plan.badge}</span>
                      )}
                    </div>

                    <div className="mt-4 flex items-baseline gap-1">
                      <span className="font-heading text-4xl font-extrabold tracking-tight">${price}</span>
                      <span className="text-xs text-muted-foreground">/ month</span>
                    </div>
                    {interval === "year" && (
                      <p className="mt-1 font-mono text-[11px] text-signal">
                        Billed ${plan.price_yearly}/yr annually
                      </p>
                    )}

                    <div className="my-6 border-t border-rule" />

                    <div className="mb-3 flex items-center gap-2 font-mono text-xs font-semibold text-foreground">
                      <Zap className="size-4 text-signal" />
                      <span>{plan.posts_per_day} {plan.posts_per_day === 1 ? "Post" : "Posts"} / Day Automated</span>
                    </div>

                    <ul className="grid gap-2.5 text-sm text-muted-foreground">
                      {plan.features.map((f, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Check className="mt-0.5 size-4 shrink-0 text-ok" />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="mt-8 pt-4">
                    <Button
                      variant={isCurrent ? "outline" : plan.popular ? "default" : "secondary"}
                      className="w-full py-5 text-sm font-semibold"
                      disabled={isCurrent || isBusy}
                      onClick={() => handleSelectPlan(plan.id)}
                    >
                      {isBusy ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : isCurrent ? (
                        "Current Plan"
                      ) : (
                        `Upgrade to ${plan.name}`
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Security & FAQ Section */}
        <div className="grid gap-6 rounded-xl border border-border/80 bg-raised/20 p-6 md:grid-cols-3">
          <div className="flex items-start gap-3">
            <CreditCard className="mt-1 size-5 text-muted-foreground" />
            <div>
              <h4 className="text-sm font-semibold">Secure payments by Razorpay</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Pay with UPI, cards or netbanking. Card details go straight to Razorpay; Mintly never sees them.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Zap className="mt-1 size-5 text-muted-foreground" />
            <div>
              <h4 className="text-sm font-semibold">Instant Volume Upgrades</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Upgrading unlocks additional daily slots and high-priority render queue immediately.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <HelpCircle className="mt-1 size-5 text-muted-foreground" />
            <div>
              <h4 className="text-sm font-semibold">Cancel or Switch Anytime</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Flexible subscription management with no lock-ins. Switch plans whenever your cadence grows.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

import { useEffect, useState } from "react";
import {
  Check,
  CreditCard,
  Crown,
  HelpCircle,
  Loader2,
  Lock,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { LegalLinks } from "@/pages/Legal";
import { PlanReviewDialog, type BillingDetails } from "@/components/plan-review-dialog";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Plan = {
  id: string;
  name: string;
  badge: string;
  price_inr_monthly: number;
  price_inr_yearly: number;
  posts_per_day: number;
  quota: { reels: number; carousels: number };
  features: string[];
  popular: boolean;
};

type PlansResponse = {
  plans: Plan[];
  payments_enabled: boolean;
  gst: { enabled: boolean; rate: number };
};

type StatusResponse = {
  tier: string;
  status: string;
  renews_at: string | null;
  has_subscription: boolean;
  change_scheduled: boolean;
  payments_enabled: boolean;
  billing: BillingDetails;
  usage: Usage;
};

type Count = { reels: number; carousels: number };
type Usage = { plan: string; exempt: boolean; used: Count; quota: Count | null; left: Count | null; resets_at: string };

/** "12 of 30 reels and 14 of 30 carousels used this month" (plans without reels mention carousels only). */
function usageLine(u: Usage | undefined): string | null {
  if (!u || u.exempt || !u.quota || (!u.quota.reels && !u.quota.carousels)) return null;
  const parts = [];
  if (u.quota.reels) parts.push(`${u.used.reels} of ${u.quota.reels} reels`);
  parts.push(`${u.used.carousels} of ${u.quota.carousels} carousels`);
  const resets = new Date(u.resets_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return `${parts.join(" and ")} used this month. Resets ${resets}.`;
}

/** Squared status tag colours by role (docs/design/design-system.md, "Status colours"). */
const TAG: Record<string, { tag: string; dot: string }> = {
  active: { tag: "text-ok border-ok/35 bg-ok/10", dot: "bg-ok" },
  past_due: { tag: "text-wait border-wait/35 bg-wait/10", dot: "bg-wait" },
  canceling: { tag: "text-wait border-wait/35 bg-wait/10", dot: "bg-wait" },
  changing: { tag: "text-go border-go/35 bg-go/10", dot: "bg-go" },
  halted: { tag: "text-bad border-bad/40 bg-bad/10", dot: "bg-bad" },
  canceled: { tag: "text-muted-foreground border-border", dot: "bg-muted-foreground/60" },
  paused: { tag: "text-muted-foreground border-border", dot: "bg-muted-foreground/60" },
};

const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  past_due: "Payment retrying",
  halted: "Payment failed",
  canceling: "Ends at period end",
  changing: "Change scheduled",
  canceled: "Cancelled",
  paused: "Paused",
};

const inr = (n: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n);

export default function SubscriptionPage() {
  const { user, patchUser } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentTier, setCurrentTier] = useState<string>(user?.subscription_tier || "free");
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [paymentsEnabled, setPaymentsEnabled] = useState(false);
  const [gst, setGst] = useState<{ enabled: boolean; rate: number }>({ enabled: false, rate: 18 });
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);
  const [reviewing, setReviewing] = useState<Plan | null>(null);

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
        setGst(plansRes.gst);
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

  async function handleSelectPlan(plan: Plan) {
    if (status?.change_scheduled) {
      toast.info("A plan change is already scheduled for your renewal date.");
      return;
    }
    if (!paymentsEnabled) {
      // local development can still switch instantly (BILLING_DEV_INSTANT); elsewhere this explains why not
      setBusyPlan(plan.id);
      try {
        const res = await api<{ tier: string; status: string; message: string }>("/api/subscription/checkout", {
          method: "POST", body: { plan_id: plan.id, interval },
        });
        setCurrentTier(res.tier);
        patchUser({ subscription_tier: res.tier, subscription_status: res.status });
        toast.success(res.message);
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Failed to start checkout");
      } finally {
        setBusyPlan(null);
      }
      return;
    }
    setReviewing(plan);   // billing details, then the itemised quote with GST, then Razorpay
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
  const renews = status?.renews_at ? new Date(status.renews_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : null;

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[72rem] gap-8 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="06"
          eyebrow="Billing"
          title="Plans and subscription"
          lead="Choose how many reels and carousels Mintly makes and posts for you each month."
        />

        {/* Current status banner */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card/40 p-5">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Crown className="size-5" aria-hidden />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Current plan</span>
                <span className="font-heading font-semibold uppercase tracking-wider text-foreground">
                  {currentTier}
                </span>
                <span className={cn("inline-flex h-5 items-center gap-1.5 rounded-[4px] border px-1.5 text-[11px] leading-none font-medium",
                  TAG[statusKey]?.tag ?? TAG.canceled.tag)}>
                  <span aria-hidden className={cn("size-1.5 rounded-[1px]", TAG[statusKey]?.dot ?? TAG.canceled.dot)} />
                  {STATUS_LABEL[statusKey] ?? statusKey}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {renews
                  ? statusKey === "canceling"
                    ? `Your plan stays active until ${renews}, then moves to Free.`
                    : statusKey === "changing"
                      ? `Your new plan starts on ${renews}, when this paid period ends.`
                      : `Renews on ${renews}.`
                  : "Choose a plan below to start posting automatically."}
              </p>
              {usageLine(status?.usage) && (
                <p className="mt-1 text-xs tabular-nums text-foreground/80">{usageLine(status?.usage)}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            {paymentsEnabled ? (
              <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
                <Lock className="size-3.5 text-ok" aria-hidden />
                <span>Payments by Razorpay</span>
              </div>
            ) : (
              <span className="font-mono text-xs text-wait">Payments aren't set up yet</span>
            )}
            {status?.has_subscription && statusKey !== "canceling" && statusKey !== "changing" && (
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
                "rounded-md px-4 py-1.5 text-sm font-medium transition-colors duration-(--dur-fast) touch:h-10",
                interval === "month"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Monthly
            </button>
            <button
              type="button"
              onClick={() => setInterval("year")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-medium transition-colors duration-(--dur-fast) touch:h-10",
                interval === "year"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Yearly
              <span className="rounded-[4px] border border-ok/35 bg-ok/10 px-1.5 py-0.5 text-[11px] font-medium leading-none text-ok">
                2 months free
              </span>
            </button>
          </div>
        </div>

        {/* Plan Cards Grid */}
        {loading ? (
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="shimmer h-96 rounded-xl border border-border" />
            ))}
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => {
              const isCurrent = currentTier.toLowerCase() === plan.id.toLowerCase();
              const price = interval === "year" ? Math.round(plan.price_inr_yearly / 12) : plan.price_inr_monthly;
              const isBusy = busyPlan === plan.id;

              return (
                <div
                  key={plan.id}
                  className={cn(
                    "relative flex flex-col justify-between rounded-xl border p-6 transition-colors duration-(--dur-fast)",
                    plan.popular ? "border-primary/60 bg-selected" : "border-border bg-card/40 hover:border-rule"
                  )}
                >
                  {plan.popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <span className="inline-flex h-5 items-center rounded-[4px] bg-primary px-2 text-[11px] font-medium leading-none text-primary-foreground">
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
                      <span className="font-heading text-4xl font-extrabold tracking-tight">₹{inr(price)}</span>
                      <span className="text-xs text-muted-foreground">/ month{gst.enabled ? " + GST" : ""}</span>
                    </div>
                    {interval === "year" && (
                      <p className="mt-1 font-mono text-[11px] text-signal">
                        Billed ₹{inr(plan.price_inr_yearly)}/yr annually{gst.enabled ? " + GST" : ""}
                      </p>
                    )}
                    {gst.enabled && (
                      <p className="mt-1 text-[11px] text-muted-foreground">{gst.rate}% GST for customers in India</p>
                    )}

                    <div className="my-6 border-t border-rule" />

                    <div className="mb-3 flex items-center gap-2 font-mono text-xs font-semibold text-foreground">
                      <Zap className="size-4 text-muted-foreground" aria-hidden />
                      <span>{plan.quota.reels ? `${plan.quota.reels} reels + ` : ""}{plan.quota.carousels} carousels / month</span>
                    </div>

                    <ul className="grid gap-2.5 text-sm text-muted-foreground">
                      {plan.features.map((f, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Check className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden />
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
                      onClick={() => handleSelectPlan(plan)}
                    >
                      {isBusy ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : isCurrent ? (
                        "Your current plan"
                      ) : (
                        `Choose ${plan.name}`
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
                Pay with UPI, card or netbanking. Payment details go straight to Razorpay; Mintly never sees them.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Zap className="mt-1 size-5 text-muted-foreground" />
            <div>
              <h4 className="text-sm font-semibold">Fair plan changes</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Upgrades start now and you pay only the difference for the time left. Downgrades start when your paid period ends.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <HelpCircle className="mt-1 size-5 text-muted-foreground" />
            <div>
              <h4 className="text-sm font-semibold">Cancel anytime</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                No lock-in. Cancel and keep your plan until the end of the period you've paid for.
              </p>
            </div>
          </div>
        </div>
      </div>
      <LegalLinks className="mx-auto max-w-[72rem] px-4 pb-8 text-xs text-muted-foreground md:px-8" />
      <PlanReviewDialog
        plan={reviewing}
        interval={interval}
        open={reviewing !== null}
        onOpenChange={(o) => { if (!o) setReviewing(null); }}
        onDone={() => { refreshStatus().catch(() => undefined); }}
      />
    </AppShell>
  );
}

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
  stripe_publishable_key: string;
};

type StatusResponse = {
  tier: string;
  status: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_publishable_key: string;
};

export default function SubscriptionPage() {
  const { user, patchUser } = useAuth();
  const [searchParams] = useSearchParams();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentTier, setCurrentTier] = useState<string>(user?.subscription_tier || "free");
  const [stripeKey, setStripeKey] = useState<string>("");
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get("success")) {
      toast.success("Payment successful! Your subscription is now active.");
    } else if (searchParams.get("cancelled")) {
      toast.info("Payment session was cancelled.");
    }
  }, [searchParams]);

  useEffect(() => {
    Promise.all([
      api<PlansResponse>("/api/subscription/plans"),
      api<StatusResponse>("/api/subscription/status").catch(() => null),
    ])
      .then(([plansRes, statusRes]) => {
        if (plansRes) {
          setPlans(plansRes.plans);
          if (plansRes.stripe_publishable_key) {
            setStripeKey(plansRes.stripe_publishable_key);
          }
        }
        if (statusRes) {
          setCurrentTier(statusRes.tier);
          if (statusRes.stripe_publishable_key && !stripeKey) {
            setStripeKey(statusRes.stripe_publishable_key);
          }
        }
      })
      .catch((err) => {
        toast.error(err instanceof ApiError ? err.message : "Failed to load plans");
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleSelectPlan(planId: string) {
    if (planId === currentTier) {
      toast.info(`You are currently on the ${planId} plan.`);
      return;
    }

    setBusyPlan(planId);
    try {
      const res = await api<{
        ok?: boolean;
        tier?: string;
        checkout_url?: string;
        mode?: string;
        message?: string;
      }>("/api/subscription/checkout", {
        method: "POST",
        body: { plan_id: planId, interval },
      });

      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      } else if (res.ok) {
        setCurrentTier(res.tier || planId);
        patchUser({ subscription_tier: res.tier || planId, subscription_status: "active" });
        toast.success(res.message || "Subscription activated successfully!");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to initiate checkout");
    } finally {
      setBusyPlan(null);
    }
  }

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
                <span className="rounded-full bg-ok/20 px-2 py-0.5 font-mono text-[10px] text-ok uppercase">
                  Active
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                All generation jobs, render pipelines, and publishing slots reflect your current tier.
              </p>
            </div>
          </div>
          {stripeKey && (
            <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
              <Lock className="size-3.5 text-ok" />
              <span>Stripe Gateway Connected</span>
            </div>
          )}
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
              <h4 className="text-sm font-semibold">Stripe Secure Payments</h4>
              <p className="mt-1 text-xs text-muted-foreground">
                All transactions are encrypted with bank-grade 256-bit security via Stripe.
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

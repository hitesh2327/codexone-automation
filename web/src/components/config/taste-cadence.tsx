import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  Clock,
  Loader2,
  Palette,
  Save,
  Sliders,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth, type User } from "@/lib/auth";
import { cn } from "@/lib/utils";

function InstagramIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

function YoutubeIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
  );
}

const NICHES = [
  "AI & Machine Learning",
  "Software Engineering & Dev",
  "Fintech & Crypto",
  "Startup & Entrepreneurship",
  "Productivity & Tech Tools",
  "Cybersecurity & Cloud",
  "Design & UI/UX",
];

const TONES = [
  "Punchy & High Energy",
  "Educational & Insightful",
  "Authoritative & Deep",
  "Conversational & Friendly",
  "Provocative & Thought-Provoking",
  "Storytelling & Narrative",
];

const AESTHETICS = [
  "Dark Minimalist Luxury",
  "Cyberpunk Neon Glow",
  "Clean Modern Pastel",
  "High-Contrast Cinematic",
  "Retro Pixel / Terminal",
  "Editorial Typography",
];

const DEFAULT_SLOTS = ["10:00", "18:00", "14:00", "21:00"];

export function TasteCadenceConfig({
  isOnboarding,
  onComplete,
}: {
  isOnboarding?: boolean;
  onComplete?: () => void;
}) {
  const { user, patchUser } = useAuth();
  const navigate = useNavigate();

  const [niche, setNiche] = useState(user?.taste?.niche || "AI & Machine Learning");
  const [tone, setTone] = useState(user?.taste?.tone || "Educational & Insightful");
  const [aesthetic, setAesthetic] = useState(user?.taste?.aesthetic || "Dark Minimalist Luxury");
  const [targetAudience, setTargetAudience] = useState(
    user?.taste?.target_audience || "Developers & Tech Founders"
  );
  const [promptInstructions, setPromptInstructions] = useState(
    user?.taste?.prompt_instructions || ""
  );

  const [platforms, setPlatforms] = useState<string[]>(
    user?.taste?.default_targets || ["ig", "yt"]
  );

  const [postsPerDay, setPostsPerDay] = useState<number>(
    user?.cadence?.posts_per_day || 2
  );
  const [slots, setSlots] = useState<string[]>(
    user?.cadence?.slots || ["10:00", "18:00"]
  );

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user?.taste) {
      if (user.taste.niche) setNiche(user.taste.niche);
      if (user.taste.tone) setTone(user.taste.tone);
      if (user.taste.aesthetic) setAesthetic(user.taste.aesthetic);
      if (user.taste.target_audience) setTargetAudience(user.taste.target_audience);
      if (user.taste.prompt_instructions !== undefined) setPromptInstructions(user.taste.prompt_instructions);
      if (user.taste.default_targets) setPlatforms(user.taste.default_targets);
    }
    if (user?.cadence) {
      if (user.cadence.posts_per_day) setPostsPerDay(user.cadence.posts_per_day);
      if (user.cadence.slots) setSlots(user.cadence.slots);
    }
  }, [user]);

  function handlePostsPerDayChange(count: number) {
    setPostsPerDay(count);
    const newSlots = [...slots];
    while (newSlots.length < count) {
      newSlots.push(DEFAULT_SLOTS[newSlots.length] || "12:00");
    }
    setSlots(newSlots.slice(0, count));
  }

  function handleSlotTimeChange(index: number, value: string) {
    const next = [...slots];
    next[index] = value;
    setSlots(next);
  }

  function togglePlatform(target: string) {
    setPlatforms((prev) =>
      prev.includes(target) ? prev.filter((p) => p !== target) : [...prev, target]
    );
  }

  async function handleSave(completeOnboarding = false) {
    if (platforms.length === 0) {
      toast.error("Please select at least one publishing platform (Instagram or YouTube).");
      return;
    }

    setSaving(true);
    const payload = {
      taste: {
        niche,
        tone,
        aesthetic,
        target_audience: targetAudience,
        prompt_instructions: promptInstructions,
        default_targets: platforms,
      },
      cadence: {
        posts_per_day: postsPerDay,
        slots,
      },
      config_completed: completeOnboarding ? true : user?.config_completed ?? true,
    };

    try {
      const updated = await api<User>("/api/profile", {
        method: "PATCH",
        body: payload,
      });
      patchUser({
        taste: updated.taste,
        cadence: updated.cadence,
        config_completed: updated.config_completed,
      });
      toast.success(
        completeOnboarding
          ? "🎉 Setup complete! Welcome to your dashboard."
          : "Taste & Cadence preferences saved successfully."
      );
      if (completeOnboarding) {
        if (onComplete) onComplete();
        navigate("/dashboard");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to save preferences");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="grid gap-8 border-t border-rule pt-8" id="taste-cadence">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="select-none font-heading text-4xl font-bold text-transparent [-webkit-text-stroke:1px_color-mix(in_srgb,var(--brand-text)_30%,transparent)]">
              00
            </span>
            <h2 className="font-heading text-2xl font-semibold tracking-tight">
              Content Taste, Platforms & Publishing Cadence
            </h2>
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Configure your AI persona, aesthetic style, target social destinations, and daily posting frequency.
          </p>
        </div>
        {isOnboarding && (
          <span className="rounded-full bg-signal/20 px-3 py-1 font-mono text-xs font-semibold uppercase text-signal">
            Step 1: Required Onboarding
          </span>
        )}
      </header>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Card 1: Taste & Style */}
        <div className="grid gap-6 rounded-xl border border-border bg-raised/40 p-6 backdrop-blur">
          <div className="flex items-center gap-2.5 font-heading text-lg font-semibold">
            <Palette className="size-5 text-primary" />
            <span>Content Taste & Style Persona</span>
          </div>

          {/* Niche */}
          <div className="grid gap-2">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Primary Niche / Subject
            </label>
            <div className="flex flex-wrap gap-1.5">
              {NICHES.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNiche(n)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-xs transition-colors",
                    niche === n
                      ? "border-primary bg-primary/10 font-medium text-foreground"
                      : "border-border bg-background/50 text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
            <Input
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              placeholder="Or enter custom niche..."
              className="mt-1 h-9 text-sm"
            />
          </div>

          {/* Tone */}
          <div className="grid gap-2">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Voice & Tone
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TONES.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTone(t)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-xs transition-colors",
                    tone === t
                      ? "border-primary bg-primary/10 font-medium text-foreground"
                      : "border-border bg-background/50 text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
            <Input
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              placeholder="Custom tone instructions..."
              className="mt-1 h-9 text-sm"
            />
          </div>

          {/* Visual Aesthetic */}
          <div className="grid gap-2">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Visual Aesthetic & Color Theme
            </label>
            <div className="flex flex-wrap gap-1.5">
              {AESTHETICS.map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => setAesthetic(a)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-xs transition-colors",
                    aesthetic === a
                      ? "border-primary bg-primary/10 font-medium text-foreground"
                      : "border-border bg-background/50 text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          {/* Target Audience */}
          <div className="grid gap-2">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Target Audience
            </label>
            <Input
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="e.g. High school & university students learning Python"
              className="h-9 text-sm"
            />
          </div>

          {/* Custom Prompt Directives */}
          <div className="grid gap-2">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Custom AI Prompt Directives
            </label>
            <textarea
              value={promptInstructions}
              onChange={(e) => setPromptInstructions(e.target.value)}
              rows={3}
              placeholder="e.g. Always include 3 actionable tips and end with a curiosity question."
              className="rounded-md border border-input bg-background/60 p-2.5 text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
            />
          </div>
        </div>

        {/* Card 2: Destinations & Cadence */}
        <div className="grid gap-6 rounded-xl border border-border bg-raised/40 p-6 backdrop-blur">
          <div className="flex items-center gap-2.5 font-heading text-lg font-semibold">
            <Sliders className="size-5 text-signal" />
            <span>Target Platforms & Daily Cadence</span>
          </div>

          {/* Platform Selection */}
          <div className="grid gap-3">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Posting Destinations (Select All That Apply)
            </label>
            <div className="grid grid-cols-2 gap-3">
              {/* Instagram */}
              <div
                role="checkbox"
                aria-checked={platforms.includes("ig")}
                tabIndex={0}
                onClick={() => togglePlatform("ig")}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    togglePlatform("ig");
                  }
                }}
                className={cn(
                  "flex cursor-pointer items-center justify-between rounded-lg border p-3.5 transition-colors",
                  platforms.includes("ig")
                    ? "border-primary/80 bg-primary/10 shadow-sm"
                    : "border-border bg-background/50 hover:bg-raised"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex size-8 items-center justify-center rounded-md bg-gradient-to-tr from-yellow-500 via-pink-500 to-purple-600 text-white">
                    <InstagramIcon className="size-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">Instagram</div>
                    <div className="text-[11px] text-muted-foreground">Reels & Carousels</div>
                  </div>
                </div>
                <div
                  className={cn(
                    "flex size-5 items-center justify-center rounded border",
                    platforms.includes("ig")
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  )}
                >
                  {platforms.includes("ig") && <Check className="size-3.5" />}
                </div>
              </div>

              {/* YouTube */}
              <div
                role="checkbox"
                aria-checked={platforms.includes("yt")}
                tabIndex={0}
                onClick={() => togglePlatform("yt")}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    togglePlatform("yt");
                  }
                }}
                className={cn(
                  "flex cursor-pointer items-center justify-between rounded-lg border p-3.5 transition-colors",
                  platforms.includes("yt")
                    ? "border-primary/80 bg-primary/10 shadow-sm"
                    : "border-border bg-background/50 hover:bg-raised"
                )}
              >
                <div className="flex items-center gap-2.5">
                  <div className="flex size-8 items-center justify-center rounded-md bg-red-600 text-white">
                    <YoutubeIcon className="size-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold">YouTube</div>
                    <div className="text-[11px] text-muted-foreground">Shorts Pipeline</div>
                  </div>
                </div>
                <div
                  className={cn(
                    "flex size-5 items-center justify-center rounded border",
                    platforms.includes("yt")
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/40"
                  )}
                >
                  {platforms.includes("yt") && <Check className="size-3.5" />}
                </div>
              </div>
            </div>
          </div>

          {/* Daily Post Cadence */}
          <div className="grid gap-3">
            <div className="flex items-baseline justify-between">
              <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Automated Posts Per Day
              </label>
              <span className="font-mono text-xs text-signal font-semibold">
                {postsPerDay} {postsPerDay === 1 ? "Slot" : "Slots"} Scheduled
              </span>
            </div>

            <div className="grid grid-cols-4 gap-2">
              {[1, 2, 3, 4].map((count) => (
                <button
                  key={count}
                  type="button"
                  onClick={() => handlePostsPerDayChange(count)}
                  className={cn(
                    "flex flex-col items-center justify-center rounded-lg border py-2.5 transition-colors",
                    postsPerDay === count
                      ? "border-signal bg-signal/10 font-bold text-signal shadow-sm"
                      : "border-border bg-background/50 text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}
                >
                  <span className="font-heading text-lg">{count}</span>
                  <span className="text-[10px] uppercase font-mono tracking-wider">
                    {count === 1 ? "Post" : "Posts"}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Slot Timings */}
          <div className="grid gap-3">
            <label className="font-mono text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Slot Times (24h IST)
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              {slots.map((slotTime, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between gap-2 rounded-md border border-border bg-background/60 px-3 py-1.5"
                >
                  <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Clock className="size-3.5 text-primary" />
                    <span>Slot #{i + 1}</span>
                  </div>
                  <Input
                    type="time"
                    value={slotTime}
                    onChange={(e) => handleSlotTimeChange(i, e.target.value)}
                    className="h-8 w-28 font-mono text-xs"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Action Button */}
          <div className="mt-auto pt-4">
            {isOnboarding ? (
              <Button
                onClick={() => handleSave(true)}
                disabled={saving}
                className="w-full py-6 text-sm font-semibold shadow-lg shadow-primary/20"
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Sparkles className="size-4" />
                )}
                Complete Onboarding & Unlock Full Desk
              </Button>
            ) : (
              <Button
                onClick={() => handleSave(false)}
                disabled={saving}
                className="w-full"
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Save className="size-4" />
                )}
                Save Taste & Cadence Settings
              </Button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

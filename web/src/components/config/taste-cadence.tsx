import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Brain,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Loader2,
  Palette,
  Plus,
  RefreshCw,
  Rss,
  Save,
  Sliders,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuth, type CategoryConfig, type TopicSourceConfig, type User } from "@/lib/auth";
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

const NICHE_GROUPS: { label: string; niches: string[] }[] = [
  {
    label: "Tech & Dev",
    niches: [
      "AI & Machine Learning",
      "Software Engineering & Dev",
      "Cybersecurity & Cloud",
      "Fintech & Crypto",
      "Startup & Entrepreneurship",
      "Productivity & Tech Tools",
      "Design & UI/UX",
    ],
  },
  {
    label: "Food & Lifestyle",
    niches: [
      "Food & Cooking",
      "Travel & Adventure",
      "Fashion & Beauty",
      "Health & Wellness",
      "Fitness & Workout",
      "Home Decor & DIY",
      "Parenting & Family",
    ],
  },
  {
    label: "Education & Knowledge",
    niches: [
      "Science & Research",
      "History & Culture",
      "Mathematics & Logic",
      "Language Learning",
      "Kids & Education",
      "Books & Literature",
      "Personal Development",
    ],
  },
  {
    label: "Entertainment",
    niches: [
      "Gaming & Esports",
      "Movies & TV",
      "Music & Audio",
      "Comedy & Memes",
      "Sports & Athletes",
      "Photography & Art",
      "Animation & Cartoons",
    ],
  },
  {
    label: "Business & Finance",
    niches: [
      "Business & Entrepreneurship",
      "Personal Finance & Investing",
      "Marketing & Growth",
      "Real Estate",
      "Career & Job Search",
      "Freelancing & Creators",
    ],
  },
];

const TONES = [
  "Punchy & High Energy",
  "Educational & Insightful",
  "Authoritative & Deep",
  "Conversational & Friendly",
  "Provocative & Thought-Provoking",
  "Storytelling & Narrative",
  "Entertaining & Fun",
  "Inspirational & Motivational",
];

const CONTENT_TYPES = [
  "Educational & How-To",
  "Entertainment & Fun",
  "Inspirational & Motivational",
  "Tutorial & Walkthrough",
  "News & Commentary",
  "Product & Review",
  "Behind the Scenes",
];

const AESTHETICS = [
  "Dark Minimalist Luxury",
  "Cyberpunk Neon Glow",
  "Bright & Vibrant Energy",
  "Clean Modern Pastel",
  "Natural & Organic Warm",
  "High-Contrast Cinematic",
  "Playful & Colorful",
  "Retro Pixel / Terminal",
  "Editorial Typography",
];

const TEMPLATE_STYLES = [
  { value: "Technical Dark", label: "Animated Diagrams", desc: "Code & system diagrams — best for tech" },
  { value: "Minimal Clean", label: "Minimal Clean", desc: "Light cards, any niche" },
  { value: "Vibrant Lifestyle", label: "Vibrant Lifestyle", desc: "Warm & bright — food, travel, wellness" },
  { value: "Playful Colorful", label: "Playful & Colorful", desc: "Bold colors — kids, entertainment, gaming" },
];

const DEFAULT_SLOTS = ["10:00", "18:00", "14:00", "21:00"];

const DAYS_SHORT = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const DAYS_LABEL: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};
type DayKey = typeof DAYS_SHORT[number];
type WeeklySlots = Record<DayKey, string[] | null>;

function defaultWeeklySlots(slots: string[]): WeeklySlots {
  return Object.fromEntries(DAYS_SHORT.map((d) => [d, [...slots]])) as WeeklySlots;
}

function normalizeCategoryList(raw?: (string | CategoryConfig)[]): CategoryConfig[] {
  if (!Array.isArray(raw)) return [];
  const out: CategoryConfig[] = [];
  const seen = new Set<string>();
  for (const item of raw) {
    const cfg: CategoryConfig =
      typeof item === "string"
        ? { name: item.trim(), description: "", keywords: [], weight: 20, prompt_style: "" }
        : {
            name: String(item.name || "").trim(),
            description: item.description || "",
            keywords: Array.isArray(item.keywords) ? item.keywords : [],
            weight: typeof item.weight === "number" && item.weight >= 1 ? Math.min(100, Math.round(item.weight)) : 20,
            prompt_style: item.prompt_style || "",
          };
    if (!cfg.name || seen.has(cfg.name.toLowerCase())) continue;
    seen.add(cfg.name.toLowerCase());
    out.push(cfg);
  }
  return out;
}

type FeedTestPreview = {
  locator: string;
  resolved_url?: string;
  headlines?: { title: string; url: string; published?: string }[];
  error?: string;
};

export function TasteCadenceConfig({
  isOnboarding,
  onComplete,
}: {
  isOnboarding?: boolean;
  onComplete?: () => void;
}) {
  const { user, patchUser } = useAuth();
  const navigate = useNavigate();

  const [niche, setNiche] = useState(user?.taste?.niche || "");
  const [categories, setCategories] = useState<CategoryConfig[]>(
    normalizeCategoryList(user?.taste?.categories)
  );
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [categoryInput, setCategoryInput] = useState("");
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [categoriesReasoning, setCategoriesReasoning] = useState("");
  const [suggestedSubs, setSuggestedSubs] = useState<string[]>([]);

  const [sources, setSources] = useState<TopicSourceConfig[]>(
    Array.isArray(user?.taste?.sources) ? user.taste.sources : []
  );
  const [sourceType, setSourceType] = useState<"rss" | "substack" | "reddit">("rss");
  const [sourceLocator, setSourceLocator] = useState("");
  const [sourceCategory, setSourceCategory] = useState("");
  const [testingSourceKey, setTestingSourceKey] = useState<string | null>(null);
  const [feedPreview, setFeedPreview] = useState<FeedTestPreview | null>(null);
  const [tone, setTone] = useState(user?.taste?.tone || "Educational & Insightful");
  const [contentType, setContentType] = useState(user?.taste?.content_type || "Educational & How-To");
  const [aesthetic, setAesthetic] = useState(user?.taste?.aesthetic || "Dark Minimalist Luxury");
  const [templateStyle, setTemplateStyle] = useState(user?.taste?.template_style || "Technical Dark");
  const [targetAudience, setTargetAudience] = useState(
    user?.taste?.target_audience || ""
  );
  const [promptInstructions, setPromptInstructions] = useState(
    user?.taste?.prompt_instructions || ""
  );

  const [platforms, setPlatforms] = useState<string[]>(
    user?.taste?.default_targets || ["ig", "yt"]
  );
  const [defaultLanguage, setDefaultLanguage] = useState<"en" | "hi">(
    user?.taste?.default_language === "hi" ? "hi" : "en"
  );
  const [defaultPostFormat, setDefaultPostFormat] = useState<"carousel" | "image_reel">(
    user?.taste?.default_post_format === "image_reel" ? "image_reel" : "carousel"
  );

  const [postsPerDay, setPostsPerDay] = useState<number>(
    user?.cadence?.posts_per_day || 2
  );
  const [slots, setSlots] = useState<string[]>(
    user?.cadence?.slots || ["10:00", "18:00"]
  );
  const [scheduleMode, setScheduleMode] = useState<"uniform" | "weekly" | "ai">(
    (user?.cadence?.schedule_mode as "uniform" | "weekly" | "ai") || "uniform"
  );
  const [weeklySlots, setWeeklySlots] = useState<WeeklySlots>(
    (user?.cadence?.weekly_slots as WeeklySlots) || defaultWeeklySlots(user?.cadence?.slots || ["10:00", "18:00"])
  );
  const [aiSchedule, setAiSchedule] = useState<Record<string, string[]>>(
    user?.cadence?.ai_schedule || {}
  );
  const [aiReasoning, setAiReasoning] = useState<string>("");
  const [aiLoading, setAiLoading] = useState(false);

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user?.taste) {
      if (user.taste.niche) setNiche(user.taste.niche);
      if (user.taste.categories) setCategories(normalizeCategoryList(user.taste.categories));
      if (user.taste.sources) setSources(user.taste.sources);
      if (user.taste.tone) setTone(user.taste.tone);
      if (user.taste.content_type) setContentType(user.taste.content_type);
      if (user.taste.aesthetic) setAesthetic(user.taste.aesthetic);
      if (user.taste.template_style) setTemplateStyle(user.taste.template_style);
      if (user.taste.target_audience) setTargetAudience(user.taste.target_audience);
      if (user.taste.prompt_instructions !== undefined) setPromptInstructions(user.taste.prompt_instructions);
      if (user.taste.default_targets) setPlatforms(user.taste.default_targets);
      if (user.taste.default_language === "en" || user.taste.default_language === "hi") setDefaultLanguage(user.taste.default_language);
      if (user.taste.default_post_format === "carousel" || user.taste.default_post_format === "image_reel") setDefaultPostFormat(user.taste.default_post_format);
    }
    if (user?.cadence) {
      if (user.cadence.posts_per_day) setPostsPerDay(user.cadence.posts_per_day);
      if (user.cadence.slots) setSlots(user.cadence.slots);
      if (user.cadence.schedule_mode) setScheduleMode(user.cadence.schedule_mode as "uniform" | "weekly" | "ai");
      if (user.cadence.weekly_slots) setWeeklySlots(user.cadence.weekly_slots as WeeklySlots);
      if (user.cadence.ai_schedule) setAiSchedule(user.cadence.ai_schedule);
    }
  }, [user]);

  function handlePostsPerDayChange(count: number) {
    setPostsPerDay(count);
    const newSlots = [...slots];
    while (newSlots.length < count) newSlots.push(DEFAULT_SLOTS[newSlots.length] || "12:00");
    const resized = newSlots.slice(0, count);
    setSlots(resized);
    // Resize weekly slots too
    setWeeklySlots((prev) => {
      const next = { ...prev };
      for (const d of DAYS_SHORT) {
        const cur = next[d];
        if (cur === null) continue;
        const expanded = [...(cur || [])];
        while (expanded.length < count) expanded.push(DEFAULT_SLOTS[expanded.length] || "12:00");
        next[d] = expanded.slice(0, count);
      }
      return next;
    });
  }

  function handleWeeklySlotChange(day: DayKey, index: number, value: string) {
    setWeeklySlots((prev) => {
      const cur = prev[day] ? [...prev[day]!] : [...slots];
      cur[index] = value;
      return { ...prev, [day]: cur };
    });
  }

  function toggleDayEnabled(day: DayKey) {
    setWeeklySlots((prev) => ({
      ...prev,
      [day]: prev[day] === null ? [...slots] : null,
    }));
  }

  async function handleGetAiSuggestions() {
    setAiLoading(true);
    try {
      const result = await api<Record<string, string[] | string>>("/api/profile/suggest-schedule", { method: "POST" });
      const schedule: Record<string, string[]> = {};
      let reasoning = "";
      for (const [k, v] of Object.entries(result)) {
        if (k === "reasoning") { reasoning = v as string; continue; }
        if (Array.isArray(v)) schedule[k] = v;
      }
      setAiSchedule(schedule);
      setAiReasoning(reasoning);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not get AI suggestions. Make sure GEMINI_API_KEY is configured.");
    } finally {
      setAiLoading(false);
    }
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

  async function handleSuggestCategories() {
    if (!niche.trim()) {
      toast.error("Set your niche first so AI knows what categories to suggest.");
      return;
    }
    setCategoriesLoading(true);
    try {
      const result = await api<{
        categories: string[];
        category_configs?: CategoryConfig[];
        suggested_subreddits?: string[];
        reasoning: string;
      }>("/api/profile/suggest-categories", { method: "POST" });
      if (result.category_configs && result.category_configs.length > 0) {
        setCategories(normalizeCategoryList(result.category_configs));
      } else {
        setCategories(normalizeCategoryList(result.categories));
      }
      setSuggestedSubs(result.suggested_subreddits || []);
      setCategoriesReasoning(result.reasoning);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not get suggestions. Make sure GEMINI_API_KEY is configured.");
    } finally {
      setCategoriesLoading(false);
    }
  }

  function handleAddCategory() {
    const val = categoryInput.trim();
    if (!val) return;
    if (categories.some((c) => c.name.toLowerCase() === val.toLowerCase())) {
      setCategoryInput("");
      return;
    }
    if (categories.length >= 12) {
      toast.error("Maximum 12 content pillars allowed.");
      return;
    }
    setCategories((prev) => [...prev, { name: val, description: "", keywords: [], weight: 20, prompt_style: "" }]);
    setCategoryInput("");
  }

  function handleRemoveCategory(catName: string) {
    setCategories((prev) => prev.filter((c) => c.name !== catName));
    if (expandedCategory === catName) setExpandedCategory(null);
  }

  function handleUpdateCategory(catName: string, patch: Partial<CategoryConfig>) {
    setCategories((prev) => prev.map((c) => (c.name === catName ? { ...c, ...patch } : c)));
  }

  async function runSourceTest(type: "rss" | "substack" | "reddit", locator: string, key: string) {
    const trimmed = locator.trim();
    if (!trimmed) {
      toast.error("Enter a feed URL, Substack slug, or subreddit first.");
      return;
    }
    setTestingSourceKey(key);
    setFeedPreview(null);
    try {
      const res = await api<{
        ok: boolean;
        resolved_url: string;
        headlines: { title: string; url: string; published?: string }[];
      }>("/api/profile/sources/test", {
        method: "POST",
        body: { source_type: type, locator: trimmed },
      });
      setFeedPreview({
        locator: trimmed,
        resolved_url: res.resolved_url,
        headlines: res.headlines,
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not fetch feed";
      setFeedPreview({ locator: trimmed, error: msg });
    } finally {
      setTestingSourceKey(null);
    }
  }

  function handleAddSource(overrideType?: "rss" | "substack" | "reddit", overrideLocator?: string) {
    const st = overrideType ?? sourceType;
    const raw = (overrideLocator ?? sourceLocator).trim();
    if (!raw) return;
    const normalizedLoc = st === "reddit" ? raw.replace(/^\/?r\//, "") : raw;
    if (sources.some((s) => s.source_type === st && s.locator.toLowerCase() === normalizedLoc.toLowerCase())) {
      if (!overrideLocator) setSourceLocator("");
      return;
    }
    setSources((prev) => [
      ...prev,
      {
        source_type: st,
        locator: normalizedLoc,
        category: overrideLocator ? "" : sourceCategory,
        enabled: true,
      },
    ]);
    if (!overrideLocator) {
      setSourceLocator("");
      setSourceCategory("");
    }
  }

  function handleRemoveSource(st: string, locator: string) {
    setSources((prev) => prev.filter((s) => !(s.source_type === st && s.locator === locator)));
  }

  function handleToggleSource(st: string, locator: string) {
    setSources((prev) =>
      prev.map((s) => (s.source_type === st && s.locator === locator ? { ...s, enabled: s.enabled === false } : s))
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
        categories: categories.length > 0 ? categories : undefined,
        sources,
        tone,
        content_type: contentType,
        aesthetic,
        template_style: templateStyle,
        target_audience: targetAudience,
        prompt_instructions: promptInstructions,
        default_targets: platforms,
        default_language: defaultLanguage,
        default_post_format: defaultPostFormat,
      },
      cadence: {
        posts_per_day: postsPerDay,
        slots,
        schedule_mode: scheduleMode,
        weekly_slots: scheduleMode === "weekly" ? weeklySlots : undefined,
        ai_schedule: scheduleMode === "ai" ? aiSchedule : undefined,
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
            <span className="num-badge">
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
          <span className="rounded-full bg-signal/20 px-3 py-1 text-xs font-semibold text-signal">
            Step 1: Required Onboarding
          </span>
        )}
      </header>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Card 1: Taste & Style */}
        <div className="grid content-start gap-6 rounded-xl border border-border bg-raised/40 p-6 backdrop-blur">
          <div className="flex items-center gap-2.5 font-heading text-lg font-semibold">
            <Palette className="size-5 text-primary" />
            <span>Content Taste & Style Persona</span>
          </div>

          {/* Niche */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
              Primary Niche / Subject
            </label>
            <div className="grid gap-2">
              {NICHE_GROUPS.map((group) => (
                <div key={group.label} className="grid gap-1">
                  <span className="text-xs text-muted-foreground/60">
                    {group.label}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {group.niches.map((n) => (
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
                </div>
              ))}
            </div>
            <Input
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              placeholder="Or type a custom niche (e.g. Vegan Recipes, Anime, Real Estate India)"
              className="mt-1 h-9 text-sm"
            />
          </div>

          {/* Content Type */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
              Content Type
            </label>
            <div className="flex flex-wrap gap-1.5">
              {CONTENT_TYPES.map((ct) => (
                <button
                  key={ct}
                  type="button"
                  onClick={() => setContentType(ct)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-xs transition-colors",
                    contentType === ct
                      ? "border-primary bg-primary/10 font-medium text-foreground"
                      : "border-border bg-background/50 text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}
                >
                  {ct}
                </button>
              ))}
            </div>
          </div>

          {/* Content Categories & Weights */}
          <div className="grid gap-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-muted-foreground">
                Content Pillars &amp; Weights
              </label>
              <button
                type="button"
                onClick={handleSuggestCategories}
                disabled={categoriesLoading}
                className="flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
              >
                {categoriesLoading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                {categories.length ? "Re-suggest" : "AI Suggest"}
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground/70">
              Adjust pillar weights (%) to control rotation frequency, and expand any pillar to set description, keywords, or prompt style.
            </p>
            {categories.length > 0 ? (
              <div className="grid gap-2">
                {(() => {
                  const totalWeight = categories.reduce((sum, c) => sum + Math.max(1, c.weight), 0) || 1;
                  return categories.map((cat) => {
                    const pct = Math.round((Math.max(1, cat.weight) / totalWeight) * 100);
                    const isOpen = expandedCategory === cat.name;
                    return (
                      <div
                        key={cat.name}
                        className="grid gap-2 rounded-lg border border-border bg-background/50 p-2.5"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-foreground">{cat.name}</span>
                            <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-primary">
                              {pct}%
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <input
                              type="range"
                              min={1}
                              max={100}
                              aria-label={`${cat.name} weight`}
                              value={cat.weight}
                              onChange={(e) => handleUpdateCategory(cat.name, { weight: Number(e.target.value) || 1 })}
                              className="h-1.5 w-24 accent-primary cursor-pointer"
                            />
                            <Input
                              type="number"
                              min={1}
                              max={100}
                              aria-label={`${cat.name} weight value`}
                              value={cat.weight}
                              onChange={(e) => handleUpdateCategory(cat.name, {
                                weight: Math.max(1, Math.min(100, Number(e.target.value) || 1)),
                              })}
                              className="h-7 w-14 px-1.5 text-center font-mono text-xs"
                            />
                            <button
                              type="button"
                              onClick={() => setExpandedCategory(isOpen ? null : cat.name)}
                              className="flex items-center gap-0.5 rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-raised hover:text-foreground"
                            >
                              Style {isOpen ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRemoveCategory(cat.name)}
                              aria-label={`Remove ${cat.name}`}
                              className="text-muted-foreground hover:text-foreground"
                            >
                              <X className="size-3.5" />
                            </button>
                          </div>
                        </div>
                        {isOpen && (
                          <div className="grid gap-2 border-t border-border/60 pt-2">
                            <Input
                              value={cat.description || ""}
                              onChange={(e) => handleUpdateCategory(cat.name, { description: e.target.value })}
                              placeholder="Description (helps AI match trending topics to this pillar)"
                              className="h-8 text-xs"
                            />
                            <Input
                              value={(cat.keywords || []).join(", ")}
                              onChange={(e) =>
                                handleUpdateCategory(cat.name, {
                                  keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean),
                                })
                              }
                              placeholder="Optional hint keywords (comma-separated)"
                              className="h-8 text-xs"
                            />
                            <Input
                              value={cat.prompt_style || ""}
                              onChange={(e) => handleUpdateCategory(cat.name, { prompt_style: e.target.value })}
                              placeholder="Style & Angle directive (e.g. Punchy 3s hook, zero hype)"
                              className="h-8 text-xs"
                            />
                          </div>
                        )}
                      </div>
                    );
                  });
                })()}
              </div>
            ) : (
              <p className="rounded-md border border-dashed border-border/60 px-4 py-3 text-center text-xs text-muted-foreground">
                No categories set — click "AI Suggest" or add manually below.
              </p>
            )}
            {categoriesReasoning && (
              <p className="rounded-md border border-border/50 bg-background/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span className="font-medium text-foreground/70">Why: </span>{categoriesReasoning}
              </p>
            )}
            {suggestedSubs.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                <span>Suggested subreddits:</span>
                {suggestedSubs.map((sub) => (
                  <button
                    key={sub}
                    type="button"
                    onClick={() => handleAddSource("reddit", sub)}
                    className="rounded border border-border bg-background/60 px-2 py-0.5 font-mono text-[11px] hover:border-primary/50 hover:text-foreground"
                  >
                    + r/{sub}
                  </button>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Input
                value={categoryInput}
                onChange={(e) => setCategoryInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddCategory(); } }}
                placeholder="Add a custom category..."
                className="h-8 text-xs"
              />
              <button
                type="button"
                onClick={handleAddCategory}
                disabled={!categoryInput.trim()}
                className="flex items-center gap-1 rounded-md border border-border bg-background/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-40"
              >
                <Plus className="size-3.5" />Add
              </button>
            </div>
          </div>

          {/* Custom Content Sources */}
          <div className="grid gap-2.5 rounded-lg border border-border/70 bg-background/30 p-3.5">
            <div className="flex items-center gap-2">
              <Rss className="size-3.5 text-primary" />
              <label className="text-xs font-medium text-muted-foreground">
                Custom Topic Sources (RSS, Substack &amp; Subreddits)
              </label>
            </div>
            <p className="text-[11px] text-muted-foreground/70">
              Add HTTPS RSS/Atom feeds, Substack newsletters, or niche subreddits. Non-tech niches skip developer feeds automatically.
            </p>
            {sources.length > 0 && (
              <div className="grid gap-1.5">
                {sources.map((src) => {
                  const sKey = `${src.source_type}:${src.locator}`;
                  return (
                    <div
                      key={sKey}
                      className={cn(
                        "flex flex-wrap items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-xs",
                        src.enabled === false ? "border-border/40 opacity-55" : "border-border bg-background/60"
                      )}
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] uppercase text-primary">
                          {src.source_type}
                        </span>
                        <span className="truncate font-mono text-[11px] text-foreground">{src.locator}</span>
                        {src.category && (
                          <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {src.category}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => runSourceTest(src.source_type, src.locator, sKey)}
                          disabled={testingSourceKey === sKey}
                          className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-50"
                        >
                          {testingSourceKey === sKey ? "Testing..." : "Test Feed"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleSource(src.source_type, src.locator)}
                          className="rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-raised hover:text-foreground"
                        >
                          {src.enabled === false ? "Enable" : "Disable"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveSource(src.source_type, src.locator)}
                          aria-label={`Remove ${src.locator}`}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="grid gap-2 sm:grid-cols-[110px_1fr]">
              <select
                aria-label="Source type"
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as "rss" | "substack" | "reddit")}
                className="h-8 rounded-md border border-input bg-background/60 px-2 text-xs text-foreground"
              >
                <option value="rss">HTTPS RSS</option>
                <option value="substack">Substack</option>
                <option value="reddit">Subreddit</option>
              </select>
              <Input
                value={sourceLocator}
                onChange={(e) => setSourceLocator(e.target.value)}
                placeholder={
                  sourceType === "reddit"
                    ? "e.g. personalfinance"
                    : sourceType === "substack"
                      ? "e.g. stratechery or https://stratechery.substack.com"
                      : "https://example.com/feed.xml"
                }
                className="h-8 text-xs"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {categories.length > 0 && (
                <select
                  aria-label="Pin source to category"
                  value={sourceCategory}
                  onChange={(e) => setSourceCategory(e.target.value)}
                  className="h-8 rounded-md border border-input bg-background/60 px-2 text-xs text-foreground"
                >
                  <option value="">Auto-match category</option>
                  {categories.map((c) => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
              )}
              <button
                type="button"
                onClick={() => runSourceTest(sourceType, sourceLocator, "draft")}
                disabled={!sourceLocator.trim() || testingSourceKey === "draft"}
                className="flex items-center gap-1 rounded-md border border-primary/40 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-40"
              >
                {testingSourceKey === "draft" && <Loader2 className="size-3 animate-spin" />}
                Test Feed
              </button>
              <button
                type="button"
                onClick={() => handleAddSource()}
                disabled={!sourceLocator.trim()}
                className="flex items-center gap-1 rounded-md border border-border bg-background/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-raised hover:text-foreground disabled:opacity-40"
              >
                <Plus className="size-3.5" />Add Source
              </button>
            </div>
            {feedPreview && (
              <div
                className={cn(
                  "grid gap-1.5 rounded-md border p-2.5 text-xs",
                  feedPreview.error
                    ? "border-destructive/50 bg-destructive/10 text-destructive"
                    : "border-primary/30 bg-primary/5 text-foreground"
                )}
              >
                {feedPreview.error ? (
                  <div className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                    <span>{feedPreview.error}</span>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span className="truncate font-mono">{feedPreview.resolved_url}</span>
                      <span>{(feedPreview.headlines || []).length} preview items</span>
                    </div>
                    {(feedPreview.headlines || []).length > 0 ? (
                      <ul className="grid gap-1">
                        {feedPreview.headlines!.map((h, i) => (
                          <li key={i} className="flex items-center justify-between gap-2 text-[11px]">
                            <span className="truncate font-medium">{h.title}</span>
                            {h.url && (
                              <a
                                href={h.url}
                                target="_blank"
                                rel="noreferrer"
                                className="shrink-0 text-primary hover:underline"
                              >
                                <ExternalLink className="size-3" />
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">Feed reachable, but returned 0 entries.</span>
                    )}
                  </>
                )}
              </div>
            )}
          </div>

          {/* Tone */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
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
            <label className="text-xs font-medium text-muted-foreground">
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

          {/* Template Style */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
              Slide & Reel Template Style
            </label>
            <div className="grid grid-cols-2 gap-2">
              {TEMPLATE_STYLES.map((ts) => (
                <button
                  key={ts.value}
                  type="button"
                  onClick={() => setTemplateStyle(ts.value)}
                  className={cn(
                    "flex flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition-colors",
                    templateStyle === ts.value
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background/50 hover:bg-raised"
                  )}
                >
                  <span className={cn("text-xs font-semibold", templateStyle === ts.value ? "text-foreground" : "text-muted-foreground")}>
                    {ts.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground/70">{ts.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Target Audience */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
              Target Audience
            </label>
            <Input
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="e.g. Home cooks aged 25-40 who want quick weeknight meals"
              className="h-9 text-sm"
            />
          </div>

          {/* Custom Prompt Directives */}
          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">
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
        <div className="grid content-start gap-6 rounded-xl border border-border bg-raised/40 p-6 backdrop-blur">
          <div className="flex items-center gap-2.5 font-heading text-lg font-semibold">
            <Sliders className="size-5 text-signal" />
            <span>Target Platforms & Daily Cadence</span>
          </div>

          {/* Platform Selection */}
          <div className="grid gap-3">
            <label className="text-xs font-medium text-muted-foreground">
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

          {/* Default Narration & Post Format */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground">
                Default Narration Language
              </label>
              <div className="grid grid-cols-2 gap-1.5 rounded-lg border border-border bg-background/50 p-1">
                {([
                  { value: "en" as const, label: "English" },
                  { value: "hi" as const, label: "Hinglish" },
                ]).map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDefaultLanguage(opt.value)}
                    className={cn(
                      "rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                      defaultLanguage === opt.value
                        ? "bg-primary/10 text-primary shadow-sm"
                        : "text-muted-foreground hover:bg-raised hover:text-foreground"
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground/70">
                Used by Generate &amp; scheduled runs unless overridden.
              </p>
            </div>

            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground">
                Default Post Format
              </label>
              <div className="grid grid-cols-2 gap-1.5 rounded-lg border border-border bg-background/50 p-1">
                {([
                  { value: "carousel" as const, label: "Carousel" },
                  { value: "image_reel" as const, label: "Image reel" },
                ]).map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDefaultPostFormat(opt.value)}
                    className={cn(
                      "rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                      defaultPostFormat === opt.value
                        ? "bg-primary/10 text-primary shadow-sm"
                        : "text-muted-foreground hover:bg-raised hover:text-foreground"
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground/70">
                Second item paired with the main reel.
              </p>
            </div>
          </div>

          {/* Daily Post Cadence */}
          <div className="grid gap-3">
            <div className="flex items-baseline justify-between">
              <label className="text-xs font-medium text-muted-foreground">
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
                  <span className="text-xs">
                    {count === 1 ? "Post" : "Posts"}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Schedule Mode */}
          <div className="grid gap-3">
            <label className="text-xs font-medium text-muted-foreground">
              Posting Schedule
            </label>
            <div className="grid grid-cols-3 gap-1.5 rounded-lg border border-border bg-background/50 p-1">
              {([
                { mode: "uniform" as const, icon: Clock, label: "Same Every Day" },
                { mode: "weekly" as const, icon: CalendarDays, label: "Per Day of Week" },
                { mode: "ai" as const, icon: Brain, label: "AI Picks Best Time" },
              ] as const).map(({ mode, icon: Icon, label }) => (
                <button key={mode} type="button" onClick={() => setScheduleMode(mode)}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-md px-2 py-2 text-xs font-medium tracking-wide transition-colors",
                    scheduleMode === mode
                      ? "bg-primary/10 text-primary shadow-sm"
                      : "text-muted-foreground hover:bg-raised hover:text-foreground"
                  )}>
                  <Icon className="size-3.5" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Uniform: same time every day */}
          {scheduleMode === "uniform" && (
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground">
                Slot Times (24h IST)
              </label>
              <div className="grid gap-2 sm:grid-cols-2">
                {slots.map((slotTime, i) => (
                  <div key={i} className="flex items-center justify-between gap-2 rounded-md border border-border bg-background/60 px-3 py-1.5">
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                      <Clock className="size-3.5 text-primary" />
                      <span>Slot #{i + 1}</span>
                    </div>
                    <Input type="time" value={slotTime} onChange={(e) => handleSlotTimeChange(i, e.target.value)}
                      className="h-8 w-28 font-mono text-xs" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Weekly: different time per day */}
          {scheduleMode === "weekly" && (
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground">
                Times Per Day (24h IST) — toggle a day off to skip it
              </label>
              <div className="grid gap-1.5">
                {DAYS_SHORT.map((day) => {
                  const enabled = weeklySlots[day] !== null;
                  const daytimes = weeklySlots[day] || slots;
                  return (
                    <div key={day} className={cn(
                      "flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 transition-colors",
                      enabled ? "border-border bg-background/60" : "border-border/40 bg-background/20 opacity-50"
                    )}>
                      <button type="button" onClick={() => toggleDayEnabled(day)}
                        className={cn(
                          "flex size-6 shrink-0 items-center justify-center rounded border transition-colors",
                          enabled ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
                        )}>
                        {enabled && <Check className="size-3.5" />}
                      </button>
                      <span className="w-8 font-mono text-xs font-medium">{DAYS_LABEL[day]}</span>
                      {enabled && daytimes.slice(0, postsPerDay).map((t, i) => (
                        <Input key={i} type="time" value={t}
                          onChange={(e) => handleWeeklySlotChange(day, i, e.target.value)}
                          className="h-7 w-24 font-mono text-xs" />
                      ))}
                      {!enabled && <span className="text-xs text-muted-foreground italic">No posts</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI: let Gemini suggest the best times */}
          {scheduleMode === "ai" && (
            <div className="grid gap-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-muted-foreground">
                  AI-Suggested Times (IST)
                </label>
                <button type="button" onClick={handleGetAiSuggestions} disabled={aiLoading}
                  className="flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50">
                  {aiLoading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                  {Object.keys(aiSchedule).length ? "Re-suggest" : "Get Suggestions"}
                </button>
              </div>
              {Object.keys(aiSchedule).length > 0 ? (
                <div className="grid gap-2">
                  {Object.entries(aiSchedule).map(([plat, times]) => (
                    <div key={plat} className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-background/60 px-3 py-2">
                      <span className="w-16 text-xs font-semibold text-muted-foreground">
                        {plat === "ig" ? "Instagram" : plat === "yt" ? "YouTube" : plat}
                      </span>
                      {(times || []).map((t, i) => (
                        <span key={i} className="flex items-center gap-1 rounded border border-primary/30 bg-primary/5 px-2 py-0.5 font-mono text-xs text-primary">
                          <Clock className="size-3" />{t}
                        </span>
                      ))}
                    </div>
                  ))}
                  {aiReasoning && (
                    <p className="rounded-md border border-border/50 bg-background/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                      <span className="font-medium text-foreground/70">Why: </span>{aiReasoning}
                    </p>
                  )}
                  <button type="button" onClick={handleGetAiSuggestions} disabled={aiLoading}
                    className="flex items-center gap-1.5 self-start text-xs text-muted-foreground hover:text-foreground">
                    <RefreshCw className="size-3" />Refresh suggestions
                  </button>
                </div>
              ) : (
                <p className="rounded-md border border-dashed border-border/60 px-4 py-5 text-center text-xs text-muted-foreground">
                  Click "Get Suggestions" and Gemini will recommend the best posting times for your niche and platforms.
                </p>
              )}
            </div>
          )}

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

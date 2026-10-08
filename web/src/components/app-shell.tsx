import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { CreditCard, FileText, KeyRound, LayoutDashboard, LogOut, ScrollText, Settings2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { UserAvatar } from "@/components/user-avatar";
import { useAuth } from "@/lib/auth";
import { getSlots } from "@/lib/generate";
import type { Slot, SlotState } from "@/lib/generate-format";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, ready: true },
  { to: "/posts", label: "Posts", icon: FileText, ready: true },
  { to: "/generate", label: "Generate", icon: Sparkles, ready: true },
  { to: "/accounts", label: "Accounts", icon: KeyRound, ready: false },
  { to: "/config", label: "Config", icon: Settings2, ready: true },
  { to: "/subscription", label: "Subscription", icon: CreditCard, ready: true },
  { to: "/logs", label: "Logs", icon: ScrollText, ready: true },
];

/** Sidebar sections. Items are looked up in NAV by path, so flipping `ready` above is all a page needs. */
const GROUPS: { label: string; paths: string[] }[] = [
  { label: "Desk", paths: ["/dashboard", "/posts", "/generate"] },
  { label: "Setup", paths: ["/accounts", "/config", "/subscription"] },
  { label: "Record", paths: ["/logs"] },
];

type NavEntry = (typeof NAV)[number] & { n: string };
const ENTRIES: NavEntry[] = NAV.map((e, i) => ({ ...e, n: String(i + 1).padStart(2, "0") }));
const grouped = GROUPS.map((g, gi) => ({
  label: g.label,
  // anything not listed in a group lands in the last one, so a new NAV entry is never lost
  items: ENTRIES.filter((e) => g.paths.includes(e.to) || (gi === GROUPS.length - 1 && !GROUPS.some((x) => x.paths.includes(e.to)))),
})).filter((g) => g.items.length);

const MONO = "font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground";

// ---------------------------------------------------------------------------------------------
// Desktop navigation: an index, not a list of pills
// ---------------------------------------------------------------------------------------------
function SideNav() {
  return (
    <nav aria-label="Main" className="grid gap-6">
      {grouped.map((g) => (
        <div key={g.label} className="grid gap-0.5">
          <p className={cn(MONO, "mb-1.5 flex items-center gap-2 px-3")} aria-hidden>
            {g.label}<span className="h-px flex-1 bg-border" />
          </p>
          {g.items.map(({ to, label, icon: Icon, ready, n }) =>
            ready ? (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "group/nav relative flex h-9 items-center gap-3 rounded-md pr-2.5 pl-3 text-sm transition-colors duration-(--dur-fast)",
                    isActive ? "font-medium text-foreground" : "text-muted-foreground hover:bg-raised hover:text-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* the bookmark: a signal tab on the sidebar's edge */}
                    <span aria-hidden className={cn("absolute top-1.5 bottom-1.5 -left-4 w-[3px] rounded-r-[2px] bg-signal transition-opacity duration-(--dur-base)", isActive ? "opacity-100" : "opacity-0")} />
                    <span aria-hidden className={cn("w-5 font-mono text-[11px] tabular-nums", isActive ? "text-signal" : "text-muted-foreground")}>{n}</span>
                    <span className="flex-1">{label}</span>
                    <Icon aria-hidden className={cn("size-4 shrink-0", isActive ? "text-primary" : "opacity-55 group-hover/nav:opacity-90")} />
                  </>
                )}
              </NavLink>
            ) : (
              <span
                key={to}
                title="Coming in a later phase"
                aria-disabled
                className="flex h-9 cursor-not-allowed items-center gap-3 pr-2.5 pl-3 text-sm text-muted-foreground/75"
              >
                <span aria-hidden className="w-5 font-mono text-[11px] tabular-nums">{n}</span>
                <span className="flex-1">{label}</span>
                <span className="rounded-[3px] border border-dashed border-border px-1 font-mono text-[9px] tracking-[0.14em] uppercase">soon</span>
              </span>
            ),
          )}
        </div>
      ))}
    </nav>
  );
}

// ---------------------------------------------------------------------------------------------
// "Today" strip: the IST clock and today's posting slots, at a glance from any page
// ---------------------------------------------------------------------------------------------
const IST_TIME = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });
const IST_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" });
const IST_DAY = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" });

const SLOT: Record<SlotState, { word: string; dot: string }> = {
  generated: { word: "made", dot: "bg-ok" },
  generating: { word: "making", dot: "bg-go" },
  failed: { word: "failed", dot: "bg-bad" },
  late: { word: "late", dot: "bg-wait" },
  upcoming: { word: "open", dot: "border border-muted-foreground/70" },
  skipped: { word: "skipped", dot: "bg-muted-foreground/50" },
  stale: { word: "missed", dot: "bg-muted-foreground/50" },
};

function useToday() {
  const [now, setNow] = useState(() => Date.now());
  const [slots, setSlots] = useState<Slot[] | null>(null);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const ctrl = new AbortController();
    const load = () => {
      if (document.hidden) return;
      getSlots(ctrl.signal).then((r) => setSlots(Array.isArray(r?.slots) ? r.slots : null)).catch(() => {});
    };
    load();
    const t = setInterval(load, 5 * 60000);
    return () => { clearInterval(t); ctrl.abort(); };
  }, []);
  const today = IST_DATE.format(now);
  return { now, today: slots?.filter((s) => s.date === today) ?? null };
}

function TodayStrip() {
  const { now, today } = useToday();
  return (
    <section aria-label="Today" className="mx-3 grid gap-2 border-t border-dashed border-border pt-4">
      <div className="flex items-baseline justify-between">
        <span className={MONO}>{IST_DAY.format(now).replace(",", "")}</span>
        <span className="font-mono text-xs tabular-nums text-foreground">{IST_TIME.format(now)}<span className="ml-1 text-[10px] text-muted-foreground">IST</span></span>
      </div>
      {today && today.length > 0 && (
        <Link to="/generate" className="-mx-1.5 grid gap-1 rounded-md px-1.5 py-1 transition-colors hover:bg-raised" aria-label={`Today's slots: ${today.map((s) => `${s.time} ${SLOT[s.state]?.word ?? s.state}`).join(", ")}. Open Generate.`}>
          {today.map((s) => (
            <span key={s.slot_at} className="flex items-center gap-2 font-mono text-[11px]" aria-hidden>
              <span className="tabular-nums text-foreground/90">{s.time}</span>
              <span className="h-px flex-1 border-b border-dotted border-rule" />
              <span className={cn("size-1.5 rounded-full", SLOT[s.state]?.dot ?? "bg-muted-foreground/50")} />
              <span className="w-12 text-muted-foreground">{SLOT[s.state]?.word ?? s.state}</span>
            </span>
          ))}
        </Link>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);
  const { pathname } = useLocation();
  const here = ENTRIES.find((e) => pathname.startsWith(e.to)) ?? (pathname.startsWith("/profile") ? { label: "Profile", n: "··" } : null);
  const display = user?.name || user?.username || user?.email;

  async function onLogout() {
    setBusy(true);
    try {
      await logout();
    } catch {
      toast.error("Couldn't sign out. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[15.5rem_minmax(0,1fr)]">
      {/* desktop sidebar: the column carries the surface so it runs the full page height */}
      <div className="hidden border-r border-sidebar-border bg-sidebar md:block">
        <aside className="sticky top-0 flex h-dvh flex-col gap-7 overflow-y-auto px-4 pt-5 pb-4">
          <Link to="/dashboard" className="flex items-center gap-3 rounded-md px-2 py-1" aria-label="codexone, go to Dashboard">
            <Logo className="size-8 rounded-[9px] text-[11px]" />
            <span className="grid leading-tight">
              <span className="font-heading text-[15px] font-semibold tracking-tight">codexone</span>
              <span className="font-mono text-[10px] tracking-[0.16em] text-muted-foreground uppercase">content desk</span>
            </span>
          </Link>

          <SideNav />

          <div className="mt-auto grid gap-4">
            <TodayStrip />
            <div className="flex items-center gap-1 border-t border-border pt-3">
              <NavLink
                to="/profile"
                className={({ isActive }) => cn("flex min-w-0 flex-1 items-center gap-3 rounded-md p-1.5 transition-colors duration-(--dur-fast)", isActive ? "bg-raised" : "hover:bg-raised")}
              >
                <UserAvatar name={user?.name} email={user?.email} version={user?.avatar_v} className="size-9" text="text-xs" />
                <span className="min-w-0 leading-tight">
                  <span className="block truncate text-sm font-medium">{display}</span>
                  <span className="block truncate text-xs text-muted-foreground">View profile</span>
                </span>
              </NavLink>
              <Button variant="ghost" size="icon" onClick={onLogout} disabled={busy} aria-label="Sign out" title="Sign out">
                <LogOut />
              </Button>
            </div>
          </div>
        </aside>
      </div>

      {/* mobile top bar: where you are, and who you are */}
      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/90 px-4 backdrop-blur md:hidden">
        <Link to="/dashboard" aria-label="codexone, go to Dashboard" className="rounded-[9px]">
          <Logo className="size-8 rounded-[9px] text-[11px]" />
        </Link>
        {here ? (
          <span className="flex min-w-0 items-baseline gap-2">
            <span aria-hidden className="font-mono text-[11px] text-signal">{here.n}</span>
            <span className="truncate font-heading font-semibold tracking-tight">{here.label}</span>
          </span>
        ) : (
          <span className="font-heading font-semibold tracking-tight">codexone</span>
        )}
        <NavLink to="/profile" aria-label="Your profile" className="ml-auto grid size-10 place-items-center rounded-[30%]">
          <UserAvatar name={user?.name} email={user?.email} version={user?.avatar_v} className="size-8" text="text-xs" />
        </NavLink>
        <Button variant="ghost" size="icon" onClick={onLogout} disabled={busy} aria-label="Sign out">
          <LogOut />
        </Button>
      </header>

      <main className="min-w-0 pb-24 md:pb-0">{children}</main>

      {/* mobile bottom bar: only the places you can go; the active one carries the signal tab on its top edge */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-border bg-background/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        {ENTRIES.filter((e) => e.ready).map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "relative flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px] transition-colors duration-(--dur-fast)",
                isActive ? "font-medium text-foreground" : "text-muted-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span aria-hidden className={cn("absolute top-0 inset-x-4 h-0.5 rounded-b-[2px] bg-signal transition-opacity", isActive ? "opacity-100" : "opacity-0")} />
                <Icon aria-hidden className={cn("size-[18px]", isActive && "text-primary")} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

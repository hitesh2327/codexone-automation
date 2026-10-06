import { useEffect, useMemo } from "react";
import { Link, NavLink, useLocation, useParams } from "react-router-dom";
import { ArrowLeft, ArrowUpRight } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { GuideBody, Unverified } from "@/components/config/parts";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { errorAnchor } from "@/lib/config-format";
import { GLOSSARY, GUIDES, TROUBLESHOOTING, VERIFIED_ON } from "@/lib/config-guides";
import { cn } from "@/lib/utils";

const TOPICS = [
  ...GUIDES.map((g) => ({ id: g.id, label: g.title.replace(/ \(.*\)$/, "") })),
  { id: "errors", label: "Troubleshooting" },
  { id: "glossary", label: "Glossary" },
];
const GROUPS: [string, string][] = [["verify", "General"], ["gemini", "Gemini"], ["telegram", "Telegram"], ["cloudinary", "Cloudinary"],
  ["github", "GitHub"], ["database", "Database & master key"]];

function Index() {
  return (
    <ol className="grid border-t border-rule">
      {GUIDES.map((g, i) => (
        <li key={g.id}>
          <Link to={`/config/guide/${g.id}`} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-rule py-4 hover:bg-raised sm:grid-cols-[2.5rem_14rem_minmax(0,1fr)_auto] sm:items-baseline">
            <span className="numeral text-xs text-signal">{String(i + 1).padStart(2, "0")}</span>
            <span className="font-medium">{g.title}</span>
            <span className="col-start-2 text-sm text-muted-foreground sm:col-start-3">{g.purpose}</span>
            <span className="col-start-2 font-mono text-[11px] text-muted-foreground sm:col-start-4">{g.minutes ? `~${g.minutes} min` : "at install"}</span>
          </Link>
        </li>
      ))}
      <li>
        <Link to="/config/guide/errors" className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 border-b border-rule py-4 hover:bg-raised">
          <span className="numeral text-xs text-signal">?</span>
          <span><span className="font-medium">Troubleshooting</span><span className="block text-sm text-muted-foreground">Every message a check can show, what causes it and the exact fix.</span></span>
        </Link>
      </li>
    </ol>
  );
}

function Errors() {
  return (
    <div className="grid gap-12">
      {GROUPS.map(([prefix, label]) => (
        <section key={prefix} aria-labelledby={`grp-${prefix}`}>
          <h2 id={`grp-${prefix}`} className="label-mono mb-3">{label}</h2>
          <div className="grid border-t border-rule">
            {Object.entries(TROUBLESHOOTING).filter(([code]) => code.startsWith(`${prefix}.`)).map(([code, t]) => (
              <article key={code} id={errorAnchor(code)} tabIndex={-1} className="scroll-mt-24 border-b border-rule py-5 target:bg-selected target:px-4">
                <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <h3 className="font-heading text-lg font-semibold">{t.title}</h3>
                  <code className="font-mono text-[11px] text-muted-foreground">{code}</code>
                </header>
                <p className="mt-1 max-w-prose text-sm text-muted-foreground">{t.cause}</p>
                <ol className="mt-3 grid gap-1.5 text-sm">
                  {t.fix.map((f, i) => <li key={i} className="flex gap-2.5"><span className="numeral w-4 shrink-0 text-xs text-signal">{i + 1}</span>{f}</li>)}
                </ol>
                {t.link && (
                  <p className="mt-2 text-sm">
                    <a href={t.link.href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-primary underline-offset-4 hover:underline">
                      {t.link.label}<ArrowUpRight aria-hidden className="size-3" /><span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  </p>
                )}
                {t.unverified && <Unverified why={t.unverified} />}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Glossary() {
  return (
    <dl className="grid border-t border-rule">
      {GLOSSARY.map((g) => (
        <div key={g.term} id={`term-${g.term.toLowerCase().replace(/[^a-z]+/g, "-")}`} className="grid gap-x-6 gap-y-1 border-b border-rule py-4 sm:grid-cols-[13rem_minmax(0,1fr)]">
          <dt className="font-medium">{g.term}</dt>
          <dd className="text-sm text-muted-foreground">{g.text}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function ConfigGuidePage() {
  const { topic } = useParams();
  const location = useLocation();
  const guide = useMemo(() => GUIDES.find((g) => g.id === topic), [topic]);
  const title = guide?.title ?? (topic === "errors" ? "Troubleshooting" : topic === "glossary" ? "Glossary" : "Setup guide");
  const lead = guide ? `${guide.minutes ? `About ${guide.minutes} minutes.` : "Done when the app is installed."} Follow along in another tab.`
    : topic === "errors" ? "Every message a check can show: the cause, the exact fix, and the official page behind it."
    : topic === "glossary" ? "The words used on the Config page, in plain language."
    : "How to get each value, step by step, with links to the exact console pages. About 10 minutes for everything needed to generate.";

  useEffect(() => {  // land on the exact troubleshooting entry a failed check linked to
    if (!location.hash) { window.scrollTo({ top: 0 }); return; }
    const el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (el) { el.scrollIntoView({ block: "start" }); (el as HTMLElement).focus?.(); }
  }, [topic, location.hash]);

  return (
    <AppShell>
      <div className="mx-auto grid max-w-[72rem] gap-8 px-4 py-6 md:px-8 md:py-9">
        <PageHeader
          index="05" eyebrow={<Link to="/config" className="hover:text-foreground">Config</Link>} title={title} lead={lead}
          actions={<Button variant="outline" size="sm" asChild><Link to="/config"><ArrowLeft />Back to Config</Link></Button>}
        />
        <div className="grid gap-10 lg:grid-cols-[12rem_minmax(0,1fr)]">
          <nav aria-label="Guide topics" className="h-fit lg:sticky lg:top-8">
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4 lg:grid-cols-1 lg:border-l lg:border-rule">
              <li><NavLink end to="/config/guide" className={({ isActive }) => cn("block py-1.5 text-sm lg:-ml-px lg:border-l-2 lg:pl-4", isActive ? "text-foreground lg:border-signal" : "text-muted-foreground hover:text-foreground lg:border-transparent")}>Overview</NavLink></li>
              {TOPICS.map((t) => (
                <li key={t.id}>
                  <NavLink to={`/config/guide/${t.id}`} className={({ isActive }) => cn("block py-1.5 text-sm lg:-ml-px lg:border-l-2 lg:pl-4", isActive ? "text-foreground lg:border-signal" : "text-muted-foreground hover:text-foreground lg:border-transparent")}>{t.label}</NavLink>
                </li>
              ))}
            </ul>
            <p className="mt-6 hidden text-xs leading-relaxed text-muted-foreground lg:block">
              Checked against the providers' official documentation on {VERIFIED_ON}. Consoles change; anything we couldn't confirm is tagged Unverified.
            </p>
          </nav>
          <div className="min-w-0">
            {guide ? <GuideBody guide={guide} /> : topic === "errors" ? <Errors /> : topic === "glossary" ? <Glossary /> : <Index />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

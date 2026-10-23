import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";

import { Logo, Wordmark } from "@/components/logo";
import { LEGAL_BY_SLUG, LEGAL_DOCS, type Block } from "@/content/legal";
import { COMPANY, MISSING, POLICY_UPDATED } from "@/lib/company";
import { cn } from "@/lib/utils";

/** Running text with **bold** and [links](href): internal paths stay in the app, others open in a new tab. */
function Text({ children }: { children: string }) {
  const parts = children.split(/(\*\*[^*]+\*\*|\[[^\]]+ to be added\]|\[[^\]]+\]\([^)]*\))/g);
  return (
    <>
      {parts.map((part, i) => {
        const bold = part.match(/^\*\*(.+)\*\*$/);
        if (bold) return <strong key={i} className="font-semibold text-foreground">{bold[1]}</strong>;
        if (/^\[[^\]]+ to be added\]$/.test(part)) return <mark key={i} className="rounded-[3px] bg-wait/10 px-1 text-wait">{part}</mark>;
        const link = part.match(/^\[([^\]]+)\]\(([^)]*)\)$/);
        if (!link) return <Fragment key={i}>{part}</Fragment>;
        const [, label, href] = link;
        const cls = "text-[var(--mint)] underline-offset-4 hover:underline focus-ring rounded-sm";
        if (href.startsWith("/")) return <Link key={i} to={href} className={cls}>{label}</Link>;
        return (
          <a key={i} href={href} className={cls} {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
            {label}{href.startsWith("http") && <ArrowUpRight aria-hidden className="ml-0.5 inline size-3 align-[-1px]" />}
          </a>
        );
      })}
    </>
  );
}

function Body({ block }: { block: Block }) {
  if (typeof block === "string") return <p className="max-w-[68ch]"><Text>{block}</Text></p>;
  return (
    <ul className="grid max-w-[68ch] gap-2">
      {block.list.map((item) => (
        <li key={item} className="flex gap-3">
          <span aria-hidden className="mt-[0.6em] size-1.5 shrink-0 rounded-[1px] bg-[var(--mint)]" />
          <span><Text>{item}</Text></span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The public legal pages (/legal/:slug), in Mintly's own palette like the other signed-out screens. A long page
 * read top to bottom, so: numbered sections and a side index (as on Profile), a narrow column for reading.
 */
export default function LegalPage() {
  const { slug = "terms" } = useParams();
  const doc = LEGAL_BY_SLUG[slug];
  const [active, setActive] = useState(doc?.sections[0]?.id);

  useEffect(() => {
    if (!doc) return;
    document.title = `${doc.title} · ${COMPANY.product}`;
    window.scrollTo(0, 0);
    const io = new IntersectionObserver(
      (entries) => { const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]; if (vis) setActive(vis.target.id); },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    doc.sections.forEach((s) => { const el = document.getElementById(s.id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [doc]);

  if (!doc) return <Navigate to="/legal/terms" replace />;
  const num = (i: number) => String(i + 1).padStart(2, "0");

  return (
    <div className="mintly min-h-dvh bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4 md:px-8">
          <Link to="/login" className="flex items-center gap-2.5 rounded-md focus-ring" aria-label="Mintly, sign in">
            <Logo className="size-8" /><Wordmark className="text-lg" />
          </Link>
          <Link to="/login" className="inline-flex h-10 items-center rounded-md px-3 text-sm text-muted-foreground hover:text-foreground focus-ring">Sign in</Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8 md:px-8 md:py-12">
        <p className="label-mono">Legal · {COMPANY.legalName}</p>
        <h1 className="mt-3 font-heading text-[30px] leading-tight font-semibold tracking-tight md:text-[38px]">{doc.title}</h1>
        <p className="mt-2 max-w-prose text-sm text-muted-foreground">{doc.summary}</p>
        <p className="mt-3 font-mono text-[11px] tabular-nums text-muted-foreground">Last updated {POLICY_UPDATED}</p>
        <span aria-hidden className="mt-6 block h-[3px] w-10 bg-[var(--mint)]" />

        {MISSING.length > 0 && (
          <p role="note" className="mt-6 max-w-[68ch] border-l-[3px] border-wait bg-wait/10 px-3 py-2 text-sm">
            <span className="font-semibold text-wait">Draft.</span> A few company details are still being added (marked in
            brackets). This page becomes final once they are in place.
          </p>
        )}

        <div className="mt-10 grid gap-10 lg:grid-cols-[13rem_minmax(0,1fr)]">
          <nav aria-label="On this page" className="sticky top-8 hidden h-fit lg:block">
            <ul className="grid gap-1 border-l">
              {doc.sections.map((s, i) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} aria-current={active === s.id ? "true" : undefined}
                     className={cn("-ml-px flex items-baseline gap-3 border-l-2 py-1.5 pl-4 text-sm transition-colors duration-(--dur-fast) focus-ring",
                       active === s.id ? "border-[var(--mint)] text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                    <span className="font-mono text-[11px] tabular-nums">{num(i)}</span>{s.title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <article className="grid gap-10 text-sm leading-relaxed text-foreground/85">
            {doc.sections.map((s, i) => (
              <section key={s.id} id={s.id} aria-labelledby={`${s.id}-h`} className="scroll-mt-8 border-t pt-8 first:border-t-0 first:pt-0">
                <header className="mb-4 flex items-start gap-4">
                  <span aria-hidden className="num-badge">{num(i)}</span>
                  <h2 id={`${s.id}-h`} className="pt-1 font-heading text-xl font-semibold tracking-tight text-foreground md:text-2xl">{s.title}</h2>
                </header>
                <div className="grid gap-3">{s.body.map((b, j) => <Body key={j} block={b} />)}</div>
              </section>
            ))}
          </article>
        </div>
      </main>

      <LegalFooter />
    </div>
  );
}

/** Links to every legal page; also used under the sign-in screens and on the Subscription page. */
export function LegalFooter({ className }: { className?: string }) {
  return (
    <footer className={cn("border-t", className)}>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-6 text-xs text-muted-foreground md:px-8">
        <p>{COMPANY.product} is a product of {COMPANY.legalName}.</p>
        <LegalLinks />
      </div>
    </footer>
  );
}

export function LegalLinks({ className }: { className?: string }): ReactNode {
  return (
    <nav aria-label="Legal" className={className}>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {LEGAL_DOCS.map((d) => (
          <li key={d.slug}>
            <Link to={`/legal/${d.slug}`} className="inline-flex min-h-6 items-center rounded-sm hover:text-foreground focus-ring">{d.title}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

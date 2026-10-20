import { cn } from "@/lib/utils";

/** The Mintly mark: a mint tile with a lowercase m and a leaf sprouting from it (brand/logo/mintly-icon.svg). */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" aria-hidden className={cn("size-10 shrink-0", className)}>
      <rect width="120" height="120" rx="28" fill="#34E3A4" />
      <g transform="translate(-6 4)">
        <path d="M34 86 V58 a13 13 0 0 1 26 0 V86 M60 58 a13 13 0 0 1 26 0 V86" stroke="#0D1117" strokeWidth="11"
              strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <path d="M84 40 C84 28 94 20 104 20 C104 32 96 40 84 40 Z" fill="#0D1117" />
        <path d="M88 36 L99 25" stroke="#34E3A4" strokeWidth="2" strokeLinecap="round" fill="none" />
      </g>
    </svg>
  );
}

/** The product name as set in the logo lockup. */
export function Wordmark({ className }: { className?: string }) {
  return <span className={cn("font-heading font-semibold tracking-tight", className)}>mintly</span>;
}

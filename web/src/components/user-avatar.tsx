import { useEffect, useState } from "react";

import { avatarUrl, initials } from "@/lib/profile";
import { cn } from "@/lib/utils";

/** Soft, deterministic tint per person, drawn from the brand palette (no random rainbow). */
function tint(seed: string): string {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const mix = 14 + (h % 5) * 6; // 14..38 % of the accent into the primary
  return `color-mix(in srgb, var(--brand-accent) ${mix}%, var(--brand-primary))`;
}

/**
 * A squircle, not a circle: the picture if there is one, otherwise the person's initials.
 * `version` is the server's avatar_v, so a new picture is a new URL and the old one never lingers.
 */
export function UserAvatar({
  name, email, version, className, text = "text-sm",
}: { name?: string | null; email?: string | null; version?: number | null; className?: string; text?: string }) {
  const [broken, setBroken] = useState(false);
  const src = avatarUrl(version);
  useEffect(() => setBroken(false), [src]);

  return (
    <span
      className={cn("relative inline-grid size-10 shrink-0 place-items-center overflow-hidden rounded-[30%] font-heading font-semibold text-[var(--brand-bg)]", text, className)}
      style={{ background: tint(name || email || "?") }}
    >
      {src && !broken ? (
        <img src={src} alt="" className="absolute inset-0 size-full object-cover" onError={() => setBroken(true)} draggable={false} />
      ) : (
        <span aria-hidden>{initials(name, email ?? "?")}</span>
      )}
    </span>
  );
}

import * as React from "react"
import { cn } from "cn"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-md px-3 py-2.5 text-base leading-relaxed md:text-sm border border-input bg-[color-mix(in_srgb,var(--brand-text)_3%,transparent)] shadow-none transition-[color,border-color,box-shadow,background-color] duration-(--dur-fast) outline-none placeholder:text-muted-foreground hover:border-[color-mix(in_srgb,var(--brand-text)_50%,var(--brand-bg))] focus-visible:border-primary focus-visible:bg-transparent focus-visible:ring-3 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }

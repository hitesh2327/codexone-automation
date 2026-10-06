import * as React from "react"
import { cn } from "cn"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md px-3 py-1 text-base touch:h-10 file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground disabled:pointer-events-none md:text-sm border border-input bg-[color-mix(in_srgb,var(--brand-text)_3%,transparent)] shadow-none transition-[color,border-color,box-shadow,background-color] duration-(--dur-fast) outline-none placeholder:text-muted-foreground hover:border-[color-mix(in_srgb,var(--brand-text)_50%,var(--brand-bg))] focus-visible:border-primary focus-visible:bg-transparent focus-visible:ring-3 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
        className
      )}
      {...props}
    />
  )
}

export { Input }

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

/*
 * One button family (docs/design/design-system.md "Buttons"):
 *   default     = the one primary action in a region (solid brand cyan)
 *   secondary   = a weighty alternative (raised neutral fill)
 *   outline     = ordinary actions (hairline)
 *   ghost       = quiet actions, toolbars, "Cancel"
 *   destructive = reject / delete / sign out others (tinted red, never solid until confirmed)
 * Focus uses the global 2px :focus-visible outline. Press nudges 1px down. Heights grow to 40px on touch.
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform] duration-(--dur-fast) ease-(--ease-out) select-none active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.28),0_1px_2px_rgb(0_0_0/0.4)] hover:bg-[color-mix(in_srgb,var(--primary),white_18%)] active:bg-[color-mix(in_srgb,var(--primary),black_10%)] active:shadow-none",
        outline:
          "border-rule bg-transparent text-foreground hover:border-[color-mix(in_srgb,var(--brand-text)_38%,var(--brand-bg))] hover:bg-raised aria-expanded:bg-raised",
        secondary:
          "border-border bg-secondary text-secondary-foreground hover:bg-[color-mix(in_srgb,var(--secondary),var(--foreground)_7%)] aria-expanded:bg-secondary",
        ghost:
          "text-muted-foreground hover:bg-raised hover:text-foreground aria-expanded:bg-raised aria-expanded:text-foreground",
        destructive:
          "border-destructive/35 bg-destructive/10 text-destructive hover:border-destructive/60 hover:bg-destructive/20",
        link: "h-auto! px-0! text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-9 gap-1.5 px-3 touch:h-10 in-data-[slot=button-group]:rounded-md has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),6px)] px-2 text-xs in-data-[slot=button-group]:rounded-md has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-2.5 text-[13px] touch:h-10 in-data-[slot=button-group]:rounded-md has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-11 gap-2 px-4 text-[15px] has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-9 touch:size-10",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),6px)] in-data-[slot=button-group]:rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-8 touch:size-10 in-data-[slot=button-group]:rounded-md",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }

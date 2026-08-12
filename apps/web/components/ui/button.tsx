import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // `btn-glow` (app/globals.css) adds the brand halo and sheen on hover
  // and focus. Applied to every variant so the interaction reads the same
  // whatever the button looks like at rest. `disabled:before:opacity-0`
  // keeps a disabled control from glowing — pointer-events are already
  // off, but a keyboard user can still focus one in some browsers.
  // `btn-glow` (app/globals.css) lights the button's edge on hover and
  // focus. The transition covers box-shadow as well as colors, because the
  // glow's outer bloom lives on the button's own shadow and would
  // otherwise snap on. `disabled:before:opacity-0` keeps a disabled
  // control dark — pointer-events are already off, but a keyboard user can
  // still focus one in some browsers.
  "btn-glow inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-[color,background-color,border-color,box-shadow] duration-[var(--transition-fast)] disabled:pointer-events-none disabled:opacity-50 disabled:before:opacity-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--bg-surface)]",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--brand-primary)] text-[var(--fg-on-primary)] hover:bg-[var(--brand-primary-hover)]",
        outline:
          "border border-[var(--border-strong)] bg-[var(--bg-surface)] text-[var(--fg-default)] hover:bg-[var(--bg-surface-hover)]",
        ghost: "text-[var(--fg-default)] hover:bg-[var(--bg-surface-hover)]",
        destructive: "bg-[var(--critical-600)] text-white hover:bg-[var(--critical-700)]",
        ai: "bg-[var(--ai-600)] text-white hover:bg-[var(--ai-700)]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

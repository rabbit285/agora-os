import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type AuthFieldProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  /** e.g. a "Forgot password?" link rendered next to the label. */
  action?: React.ReactNode;
};

/** A labeled input with an inline error message, forwarding its ref so it
 * composes directly with react-hook-form's register() the same way every
 * existing auth page already wires its own Input/Label pairs by hand. */
export const AuthField = React.forwardRef<HTMLInputElement, AuthFieldProps>(
  ({ label, error, action, id, className, ...props }, ref) => {
    const fieldId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor={fieldId}>{label}</Label>
          {action}
        </div>
        <Input
          id={fieldId}
          ref={ref}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={error ? `${fieldId}-error` : undefined}
          className={cn(error && "border-[var(--critical-500)]", className)}
          {...props}
        />
        {error && (
          <p id={`${fieldId}-error`} role="alert" className="text-xs text-[var(--critical-600)]">
            {error}
          </p>
        )}
      </div>
    );
  },
);
AuthField.displayName = "AuthField";

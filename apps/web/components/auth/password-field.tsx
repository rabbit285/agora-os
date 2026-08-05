"use client";

import * as React from "react";
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type PasswordFieldProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  error?: string;
  action?: React.ReactNode;
};

/** Same shape as AuthField, plus a show/hide toggle — password-manager
 * compatibility relies on the input staying type="password" by default
 * and only switching to "text" while the user is actively revealing it,
 * never the other way around. */
export const PasswordField = React.forwardRef<HTMLInputElement, PasswordFieldProps>(
  ({ label, error, action, id, className, ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const fieldId = id ?? props.name;

    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor={fieldId}>{label}</Label>
          {action}
        </div>
        <div className="relative">
          <Input
            id={fieldId}
            ref={ref}
            type={visible ? "text" : "password"}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={error ? `${fieldId}-error` : undefined}
            className={cn("pr-10", error && "border-[var(--critical-500)]", className)}
            {...props}
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? "Hide password" : "Show password"}
            aria-pressed={visible}
            className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
          >
            {visible ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
          </button>
        </div>
        {error && (
          <p id={`${fieldId}-error`} role="alert" className="text-xs text-[var(--critical-600)]">
            {error}
          </p>
        )}
      </div>
    );
  },
);
PasswordField.displayName = "PasswordField";

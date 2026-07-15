import { type ButtonHTMLAttributes, useId } from "react";

import "../theme/interaction.css";

export type ButtonTone = "default" | "primary" | "danger" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ButtonTone;
  disabledReason?: string;
}

export function Button({
  children,
  className,
  disabled = false,
  disabledReason,
  tone = "default",
  type = "button",
  ...buttonProps
}: ButtonProps) {
  const reasonId = useId();
  const visibleReason = disabled && disabledReason?.trim() ? disabledReason.trim() : null;
  const classes = ["button", className].filter(Boolean).join(" ");

  return (
    <span className="button-field">
      <button
        {...buttonProps}
        aria-describedby={visibleReason ? reasonId : undefined}
        className={classes}
        data-tone={tone}
        disabled={disabled}
        type={type}
      >
        {children}
      </button>
      {visibleReason ? (
        <span className="button-disabled-reason" id={reasonId}>
          {visibleReason}
        </span>
      ) : null}
    </span>
  );
}

import { useRef, type ClipboardEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

export const OTP_LENGTH = 6;

interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * Segmented 6-box numeric code entry — identical to ForgeVault's 2FA login standard.
 * Supports:
 * - Direct single-digit entry with auto-advance to next box
 * - Backspace navigation to previous box when empty
 * - Arrow Left / Right navigation between boxes
 * - Clipboard paste across all 6 boxes
 */
export function OtpInput({
  value,
  onChange,
  autoFocus = true,
  disabled = false,
  className,
}: OtpInputProps) {
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: OTP_LENGTH }, (_, i) => value[i] ?? "");

  const setDigit = (index: number, raw: string) => {
    const digit = raw.replace(/\D/g, "").slice(-1);
    const next = digits.slice();
    next[index] = digit;
    const combined = next.join("").replace(/\s+$/, "");
    onChange(combined);

    if (digit && index < OTP_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowLeft" && index > 0) {
      e.preventDefault();
      inputRefs.current[index - 1]?.focus();
    } else if (e.key === "ArrowRight" && index < OTP_LENGTH - 1) {
      e.preventDefault();
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, OTP_LENGTH);
    if (!pasted) return;
    e.preventDefault();
    onChange(pasted);
    const targetIndex = Math.min(pasted.length, OTP_LENGTH - 1);
    inputRefs.current[targetIndex]?.focus();
  };

  return (
    <div className={cn("flex justify-center gap-2 sm:gap-2.5", className)} data-testid="otp-input-container">
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => {
            inputRefs.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          autoFocus={autoFocus && i === 0}
          disabled={disabled}
          maxLength={1}
          value={digit}
          aria-label={`Dígito ${i + 1} de ${OTP_LENGTH}`}
          data-testid={`otp-digit-${i}`}
          onChange={(e) => setDigit(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          className="h-12 w-10 sm:h-14 sm:w-12 rounded-lg border border-border bg-muted/40 text-center font-mono text-xl font-bold text-foreground transition-all focus:border-primary focus:bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-50"
        />
      ))}
    </div>
  );
}

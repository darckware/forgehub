import { cn } from "@/lib/utils";

/** Mascot icon for "the assistant" across the app -- a small robot that
 * blinks and drifts its eyes, replacing the static lucide `Bot` icon
 * wherever an agent/assistant affordance needs a face (2026-08-16, Marcelo:
 * "crie um icone animado para ser utilizado no agente... um robo que mexe
 * os olhos e pisca... esse icone será utilizado nos assistentes").
 * Same 24x24 viewBox and stroke-based style as lucide-react icons, so it
 * drops into existing `h-4 w-4`-style className usage without layout
 * changes. Animated with native SVG <animate> (SMIL) rather than a CSS
 * class + transform-origin -- a first CSS-transform version rendered
 * static in practice (Marcelo: "não está animado"), most likely because
 * CSS transform-origin on an SVG <g> needs an explicit transform-box to
 * line up with viewBox coordinates, and Tailwind's motion-reduce: variant
 * silently no-ops the whole thing under a reduced-motion setting. SMIL
 * animates the eye ellipses' own geometry (cx/ry) directly, so neither
 * failure mode applies. Two static ear dots sit just outside the head rect
 * (2026-08-16, Marcelo: "observei que no nosso robo não colocamos os dois
 * pontos da orelha") -- lucide's own `Bot` icon has the equivalent pair of
 * ear ticks, and dropping them made this replacement read as less robot-like. */
export function AssistantRobotIcon({ className, animated = true }: { className?: string; animated?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      className={cn("h-4 w-4", className)}
      aria-hidden="true"
    >
      <line x1="12" y1="2" x2="12" y2="5">
        {animated && (
          <animate
            attributeName="y1" values="2;1.5;2;2.5;2" keyTimes="0;0.25;0.5;0.75;1"
            dur="2.4s" repeatCount="indefinite"
          />
        )}
      </line>
      <circle cx="12" cy="1.4" r="0.6" fill="currentColor" stroke="none">
        {animated && (
          <animate
            attributeName="cy" values="1.4;0.9;1.4;1.9;1.4" keyTimes="0;0.25;0.5;0.75;1"
            dur="2.4s" repeatCount="indefinite"
          />
        )}
      </circle>
      <rect x="4" y="5" width="16" height="14" rx="4" />
      <circle cx="2.6" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="21.4" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <ellipse cx="9" cy="12" rx="1.3" ry="1.3" fill="currentColor" stroke="none">
        {animated && (
          <>
            <animate
              attributeName="cx" values="9;9;8.3;8.3;9;9.7;9.7;9" keyTimes="0;0.15;0.3;0.4;0.5;0.65;0.8;1"
              dur="5.2s" repeatCount="indefinite"
            />
            <animate
              attributeName="ry" values="1.3;1.3;0.15;1.3;1.3" keyTimes="0;0.88;0.92;0.96;1"
              dur="4s" repeatCount="indefinite"
            />
          </>
        )}
      </ellipse>
      <ellipse cx="15" cy="12" rx="1.3" ry="1.3" fill="currentColor" stroke="none">
        {animated && (
          <>
            <animate
              attributeName="cx" values="15;15;14.3;14.3;15;15.7;15.7;15" keyTimes="0;0.15;0.3;0.4;0.5;0.65;0.8;1"
              dur="5.2s" repeatCount="indefinite"
            />
            <animate
              attributeName="ry" values="1.3;1.3;0.15;1.3;1.3" keyTimes="0;0.88;0.92;0.96;1"
              dur="4s" begin="0.06s" repeatCount="indefinite"
            />
          </>
        )}
      </ellipse>
      <path d="M9 16.2h6" />
    </svg>
  );
}

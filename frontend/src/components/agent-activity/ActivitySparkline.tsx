import { cn } from "@/lib/utils";

/**
 * Tiny bar sparkline, oldest bucket first. Hand-rolled SVG like DemandsStatsPanel's --
 * no charting library for a strip of rectangles.
 */
export function ActivitySparkline({
  values,
  className,
  barClassName = "fill-primary/70",
  label,
}: {
  values: number[];
  className?: string;
  barClassName?: string;
  label?: string;
}) {
  const max = Math.max(1, ...values);
  const width = 100;
  const height = 24;
  const gap = values.length > 30 ? 0.4 : 1.5;
  const barWidth = values.length ? (width - gap * (values.length - 1)) / values.length : 0;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("h-6 w-full", className)}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {values.map((value, index) => {
        const barHeight = value === 0 ? 1 : Math.max(2, (value / max) * height);
        return (
          <rect
            key={index}
            x={index * (barWidth + gap)}
            y={height - barHeight}
            width={barWidth}
            height={barHeight}
            rx={0.6}
            className={value === 0 ? "fill-muted-foreground/15" : barClassName}
          />
        );
      })}
    </svg>
  );
}

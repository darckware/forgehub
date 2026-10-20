# ForgeHub Theme

## Compact token summary

- Theme strategy: Tailwind CSS with class-based dark mode and HSL CSS custom properties.
- Typography: browser/system sans-serif inherited through Tailwind defaults; operational identifiers and paths use utility-level monospace styles where needed.
- Light palette: background `0 0% 100%`, foreground/primary `222 47% 11%`, card `0 0% 100%`, secondary/muted/accent `210 40% 96%`, muted foreground `215 16% 47%`, destructive `0 84% 60%`, border/input `214 32% 91%`.
- Dark palette: background `222 47% 8%`, foreground/primary `210 40% 98%`, card `222 47% 11%`, secondary/muted/accent `217 33% 17%`, muted foreground `215 20% 65%`, destructive `0 63% 31%`, border/input `217 33% 20%`.
- Radius: base `0.5rem`; large = base, medium = base minus 2px, small = base minus 4px.
- Shadows: Tailwind defaults; ForgeHub favors borders and subtle surface contrast over decorative shadows.
- Spacing and breakpoints: Tailwind defaults.
- Motion: restrained; existing custom `agent-cursor` animation lasts 1.6s and fades/scales a transient cursor indicator.
- Scrollbars: 8px, rounded, muted track and progressively stronger muted-foreground thumb states.

## Raw source: `frontend/tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "agent-cursor-fade": {
          "0%": { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
          "70%": { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
          "100%": { opacity: "0", transform: "translate(-50%, -50%) scale(0.85)" },
        },
      },
      animation: {
        "agent-cursor": "agent-cursor-fade 1.6s ease-out forwards",
      },
    },
  },
  plugins: [],
};
```

## Raw source: `frontend/src/index.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  select { color-scheme: light; }
  .dark select { color-scheme: dark; }
  select option {
    color: hsl(var(--foreground));
    background-color: hsl(var(--background));
  }

  .select-chevron {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    background-position: right 0.5rem center;
    background-size: 1em;
  }

  :root {
    --background: 0 0% 100%;
    --foreground: 222 47% 11%;
    --card: 0 0% 100%;
    --card-foreground: 222 47% 11%;
    --primary: 222 47% 11%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96%;
    --secondary-foreground: 222 47% 11%;
    --muted: 210 40% 96%;
    --muted-foreground: 215 16% 47%;
    --accent: 210 40% 96%;
    --accent-foreground: 222 47% 11%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 210 40% 98%;
    --border: 214 32% 91%;
    --input: 214 32% 91%;
    --ring: 222 47% 11%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222 47% 8%;
    --foreground: 210 40% 98%;
    --card: 222 47% 11%;
    --card-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222 47% 11%;
    --secondary: 217 33% 17%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217 33% 17%;
    --muted-foreground: 215 20% 65%;
    --accent: 217 33% 17%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 63% 31%;
    --destructive-foreground: 210 40% 98%;
    --border: 217 33% 20%;
    --input: 217 33% 20%;
    --ring: 213 27% 84%;
  }

  * { @apply border-border; }
  body { @apply bg-background text-foreground antialiased; }
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track {
  background: hsl(var(--muted));
  border-radius: 9999px;
  margin: 4px;
}
::-webkit-scrollbar-thumb {
  background: hsl(var(--muted-foreground) / 0.4);
  border-radius: 9999px;
  border: 2px solid hsl(var(--muted));
}
::-webkit-scrollbar-thumb:hover { background: hsl(var(--muted-foreground) / 0.7); }
::-webkit-scrollbar-thumb:active { background: hsl(var(--muted-foreground) / 0.9); }
::-webkit-scrollbar-corner { background: transparent; }
```

## Raw source: `frontend/src/lib/theme.tsx`

```tsx
import * as React from "react";

type Theme = "light" | "dark" | "system";
const STORAGE_KEY = "forgehub-theme";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | undefined>(undefined);

function getSystemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(resolved: "light" | "dark") {
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return stored ?? "system";
  });
  const resolvedTheme = theme === "system" ? getSystemTheme() : theme;
  React.useEffect(() => applyTheme(resolvedTheme), [resolvedTheme]);
  React.useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => applyTheme(getSystemTheme());
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [theme]);
  const setTheme = React.useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);
  return <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
```

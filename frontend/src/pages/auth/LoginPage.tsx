import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Loader2,
  LogIn,
  Eye,
  EyeOff,
  ShieldCheck,
  GitBranch,
  Bot,
  User,
  KeyRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo, LogoMark } from "@/components/Logo";
import { useLogin } from "@/hooks/useAuth";
import { getRememberMe, setRememberMe } from "@/store/authStore";

/**
 * Deterministic spark field (module-level so positions don't reshuffle on
 * re-render). Sparks echo the amber spark in the LogoMark: they rise from
 * the bottom of the screen like embers off an anvil.
 */
const SPARKS = Array.from({ length: 18 }, (_, i) => ({
  left: `${(i * 137.5) % 100}%`, // golden-angle spread, no clumping
  size: 1.5 + ((i * 7) % 4),
  duration: 7 + ((i * 13) % 8),
  delay: (i * 1.7) % 9,
}));

/**
 * Pipeline DAG rendered behind everything: nodes are pipeline stages,
 * amber rings are approval gates, and pulses travelling along edges are
 * work flowing product → pipeline → tasks → agents. Fixed coordinates in
 * a 1440×900 viewBox, scaled with `slice` so it always fills the screen.
 */
const DAG_NODES: Array<{ x: number; y: number; gate?: boolean }> = [
  { x: 120, y: 620 },
  { x: 320, y: 480 },
  { x: 320, y: 740 },
  { x: 560, y: 560, gate: true },
  { x: 800, y: 420 },
  { x: 800, y: 700 },
  { x: 1040, y: 540, gate: true },
  { x: 1260, y: 380 },
  { x: 1260, y: 680 },
  { x: 560, y: 300 },
  { x: 1040, y: 820 },
];

const DAG_EDGES: Array<[number, number]> = [
  [0, 1], [0, 2], [1, 3], [2, 3], [1, 9], [9, 4], [3, 4],
  [3, 5], [4, 6], [5, 6], [6, 7], [6, 8], [5, 10], [10, 8],
];

/** Edges that carry an animated pulse, with stagger so flow looks organic. */
const DAG_PULSES = DAG_EDGES.map((edge, i) => ({
  edge,
  duration: 3 + ((i * 5) % 4),
  delay: (i * 1.9) % 8,
})).filter((_, i) => i % 2 === 0 || i > 8);

function PipelineGraph() {
  return (
    <svg
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 h-full w-full"
      aria-hidden="true"
    >
      {DAG_EDGES.map(([a, b], i) => (
        <line
          key={i}
          x1={DAG_NODES[a].x}
          y1={DAG_NODES[a].y}
          x2={DAG_NODES[b].x}
          y2={DAG_NODES[b].y}
          stroke="rgba(129,140,248,0.14)"
          strokeWidth={1}
        />
      ))}
      {DAG_NODES.map((n, i) =>
        n.gate ? (
          <motion.circle
            key={i}
            cx={n.x}
            cy={n.y}
            r={7}
            fill="none"
            stroke="rgba(245,158,11,0.45)"
            strokeWidth={1.5}
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 3, repeat: Infinity, delay: i * 0.7 }}
          />
        ) : (
          <circle key={i} cx={n.x} cy={n.y} r={3.5} fill="rgba(129,140,248,0.4)" />
        ),
      )}
      {DAG_PULSES.map(({ edge: [a, b], duration, delay }, i) => (
        <motion.circle
          key={i}
          r={3}
          fill="#818cf8"
          style={{ filter: "drop-shadow(0 0 4px rgba(129,140,248,0.9))" }}
          initial={{ cx: DAG_NODES[a].x, cy: DAG_NODES[a].y }}
          animate={{
            cx: [DAG_NODES[a].x, DAG_NODES[b].x],
            cy: [DAG_NODES[a].y, DAG_NODES[b].y],
            opacity: [0, 1, 1, 0],
          }}
          transition={{ duration, delay, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </svg>
  );
}

/** Full-viewport animated backdrop: anvil watermark + pipeline DAG + orbs + sparks. */
function ForgeBackdrop() {
  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
      {/* Base: deep near-black blue, fixed (login is dark regardless of theme) */}
      <div className="absolute inset-0 bg-[#05070f]" />

      {/* Slow-panning perspective grid */}
      <motion.div
        className="absolute -inset-[100%] opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(99,102,241,0.14) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.14) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage:
            "radial-gradient(ellipse 70% 60% at 40% 45%, black 30%, transparent 75%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 70% 60% at 40% 45%, black 30%, transparent 75%)",
        }}
        animate={{ x: [0, 56], y: [0, 56] }}
        transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
      />

      {/* Giant brand anvil watermark, slowly breathing behind the graph */}
      <motion.div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-[0.05]"
        animate={{ scale: [1, 1.04, 1] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      >
        <LogoMark className="h-[42rem] w-[42rem]" />
      </motion.div>

      {/* Pipeline DAG: stages, approval gates, work pulses */}
      <PipelineGraph />

      {/* Drifting glow orbs in the brand colors (indigo anvil / amber spark) */}
      <motion.div
        className="absolute h-[34rem] w-[34rem] rounded-full bg-indigo-600/25 blur-[110px]"
        style={{ top: "-10%", left: "-8%" }}
        animate={{ x: [0, 90, 20, 0], y: [0, 50, 110, 0] }}
        transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute h-[28rem] w-[28rem] rounded-full bg-violet-700/20 blur-[100px]"
        style={{ bottom: "-14%", right: "-6%" }}
        animate={{ x: [0, -80, -20, 0], y: [0, -60, -120, 0] }}
        transition={{ duration: 30, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute h-72 w-72 rounded-full bg-amber-500/15 blur-[90px]"
        style={{ top: "55%", left: "48%" }}
        animate={{ x: [0, -60, 40, 0], y: [0, 40, -50, 0], scale: [1, 1.15, 0.95, 1] }}
        transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Rising forge sparks */}
      {SPARKS.map((s, i) => (
        <motion.span
          key={i}
          className="absolute rounded-full bg-amber-400"
          style={{
            left: s.left,
            bottom: -8,
            width: s.size,
            height: s.size,
            boxShadow: "0 0 6px 1px rgba(245,158,11,0.55)",
          }}
          animate={{ y: ["0vh", "-92vh"], opacity: [0, 0.9, 0] }}
          transition={{
            duration: s.duration,
            delay: s.delay,
            repeat: Infinity,
            ease: "linear",
          }}
        />
      ))}

      {/* Vignette so edges fall off and the content stays the focal point */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_35%,rgba(2,4,10,0.85)_100%)]" />
    </div>
  );
}

const PILLARS = [
  {
    icon: GitBranch,
    title: "Governed pipelines",
    text: "Stage gates with mandatory artifacts and explicit approvals before anything moves forward.",
  },
  {
    icon: Bot,
    title: "Agent execution",
    text: "AI agents pick up planned tasks and execute them under recorded, auditable runs.",
  },
  {
    icon: ShieldCheck,
    title: "End-to-end traceability",
    text: "Every feature, task and artifact stays linked to product, version, owner and audit trail.",
  },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from ?? "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  // Pre-fills from the last choice (defaults true -- see authStore's
  // getRememberMe docstring for why an unset preference isn't "false").
  const [rememberMe, setRememberMeChecked] = useState(getRememberMe);
  const login = useLogin();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Set before the login mutation so setAuth's persisted write (inside
      // useLogin's onSuccess) already lands in the right storage -- no
      // second write or page reload needed for the choice to take effect.
      setRememberMe(rememberMe);
      await login.mutateAsync({ username, password });
      navigate(from, { replace: true });
    } catch {
      // error shown below
    }
  };

  return (
    <div className="dark relative min-h-screen text-foreground">
      <ForgeBackdrop />

      <div className="relative z-10 grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
        {/* Left: branding / product panel (desktop only) */}
        <div className="hidden flex-col justify-between p-12 lg:flex">
          <Logo />

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="max-w-lg"
          >
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-indigo-400/25 bg-indigo-500/10 px-3 py-1 text-xs font-medium tracking-wide text-indigo-300">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              AI delivery control plane
            </p>
            <h1 className="text-4xl font-semibold leading-tight tracking-tight">
              Plan, govern and execute software with AI agents.
            </h1>

            <div className="mt-10 flex flex-col gap-6">
              {PILLARS.map((p, i) => (
                <motion.div
                  key={p.title}
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.5, delay: 0.2 + i * 0.12 }}
                  className="flex items-start gap-4"
                >
                  <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2.5">
                    <p.icon className="h-5 w-5 text-indigo-300" />
                  </div>
                  <div>
                    <p className="font-medium">{p.title}</p>
                    <p className="text-sm text-muted-foreground">{p.text}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          <p className="font-mono text-xs text-muted-foreground/70">
            ForgeHub · API v1 · products → pipelines → tasks → agents → audit
          </p>
        </div>

        {/* Right: sign-in panel */}
        <div className="flex items-center justify-center p-6 lg:border-l lg:border-white/[0.06] lg:bg-black/30 lg:backdrop-blur-md">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="w-full max-w-sm"
          >
            {/* Mobile-only brand header (left panel is hidden) */}
            <div className="mb-8 flex flex-col items-center gap-2 lg:hidden">
              <LogoMark className="h-14 w-14 drop-shadow-[0_0_18px_rgba(99,102,241,0.45)]" />
              <span className="text-xl font-semibold tracking-tight">ForgeHub</span>
            </div>

            <div className="rounded-xl border border-white/10 bg-card/60 p-8 shadow-2xl shadow-indigo-950/40 backdrop-blur-xl">
              <div className="mb-6">
                <h2 className="text-2xl font-semibold tracking-tight">Welcome back</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Sign in to your workspace
                </p>
              </div>

              <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="username">Username</Label>
                  <div className="relative">
                    <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="username"
                      autoFocus
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="Enter your username"
                      className="pl-9"
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-9 pr-9"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                <label className="flex items-center gap-2 text-sm text-muted-foreground select-none">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMeChecked(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-indigo-500"
                  />
                  Stay logged in
                </label>

                {login.error && (
                  <p className="text-xs text-destructive">{login.error.message}</p>
                )}

                <Button
                  type="submit"
                  disabled={login.isPending || !username || !password}
                  className="mt-2 gap-2"
                >
                  {login.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <LogIn className="h-4 w-4" />
                  )}
                  Sign in
                </Button>
              </form>
            </div>

            <p className="mt-6 text-center text-xs text-muted-foreground/70">
              Restricted access — activity on this platform is audited.
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  );
}

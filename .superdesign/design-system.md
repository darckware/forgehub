# ForgeHub Design System — Agent Activity

## Product context

ForgeHub is Marcelo's primary operator console for coordinating an ecosystem of internal Hermes agents and external runtime agents. It is a professional product/admin surface: a calm mission-control ledger, dense enough for rapid diagnosis while keeping failures, blockers, approval gates, and ownership changes unmistakable.

The Agent Activity target is an existing page being redesigned as a hybrid operational view. It must explain live teamwork from canonical ForgeHub records, especially Messages/agent demands, governed executions, progress checkpoints, approvals, notifications, and ForgeRouter telemetry. It must never imply that decorative animation is authoritative state.

## Key jobs to be done

- See which project and task every agent is working on now.
- Understand the agent's current action, latest verified checkpoint, and point of resumption.
- Follow requests between agents, including sender, recipient, response requirement, and waiting state.
- Surface errors, heartbeat loss, quota/limit interruption, blockers, and missing authorization.
- Ask Athos to monitor or coordinate correction from an incident.
- When an agent becomes unavailable, show a prepared handoff with compatible successors, preserved context, risks, and required approvals; always wait for Marcelo's explicit decision.
- Keep the same decision synchronized across Agent Activity, Messages, and Notifications.

## Information architecture

Use the approved hybrid structure:

1. A live agent communication map as the central visual field.
2. A persistent operational rail for incidents, blockers, pending decisions, and approvals.
3. A lower event timeline for messages, tasks, checkpoints, failures, responses, and handoffs.
4. Selecting an agent opens a contextual inspector without navigating away, showing identity, runtime health, current project/task, work package, actions, incoming/outgoing requests, dependencies, errors, authorization gates, and resume state.

## Visual language

- Preserve ForgeHub's dark navy operational palette and existing light-theme counterpart.
- Use only existing system sans typography for interface copy and system monospace for paths, slugs, hashes, commands, runtimes, timestamps, and checkpoint keys.
- Use borders and subtle surface shifts for hierarchy. Avoid glass, ornamental gradients, excessive shadows, decorative tiles, or sci-fi chrome.
- Lucide icons are the icon language. Never use emoji as interface icons.
- Circular avatars identify agents; compact badges communicate metadata; status must always include text/icon rather than color alone.
- Favor a disciplined network/operations diagram: thin directional edges, compact labeled message packets, clear selection focus, and restrained state-based motion.

## Canonical tokens

- Dark background: `hsl(222 47% 8%)`
- Dark foreground: `hsl(210 40% 98%)`
- Dark card: `hsl(222 47% 11%)`
- Dark muted surface: `hsl(217 33% 17%)`
- Dark muted foreground: `hsl(215 20% 65%)`
- Dark border: `hsl(217 33% 20%)`
- Destructive dark: `hsl(0 63% 31%)`
- Success: `hsl(160 84% 39%)`
- Warning: `hsl(38 92% 50%)`
- Focus/brand accent: `hsl(239 84% 67%)`
- Base radius: `0.5rem`; compact radius: `0.375rem`; avatars: circular.
- Base spacing unit: `0.25rem` using Tailwind's established scale.

## State semantics

- Healthy/active: green semantic state with label/icon.
- Awaiting response or human decision: amber semantic state with explicit owner and elapsed time.
- Blocked: amber-to-red depending on severity, with blocker code and next action.
- Failed/error/heartbeat lost: destructive state with error code, source, time, retry/monitor action, and resume point where available.
- Paused: neutral/blue state, differentiated from an unplanned interruption.
- Handoff proposed: visible source → candidate transfer link, never displayed as complete until Marcelo approves.
- Handoff approved/in progress/completed: distinct timeline events preserving both prior and new ownership.

## Layout and density

- Desktop-first operational canvas within the existing AppLayout/sidebar shell.
- Maintain stable geometry while data refreshes; use skeletons or reserved regions rather than layout jumps.
- Central map receives the largest region. The incident rail remains scannable without covering the map. The timeline is resizable or collapsible but stays discoverable.
- Inspector uses progressive disclosure; do not place every field directly on agent nodes.
- Dense data should use aligned rows, compact metadata, and deliberate whitespace rather than a wall of cards.
- Responsive behavior may stack the incident rail beneath the map and convert the inspector to an accessible sheet/dialog while preserving all actions.

## Motion

- Animate only real state transitions: dispatched request, received response, active execution, failure, resumed work, and confirmed handoff.
- Keep motion subtle and short; respect `prefers-reduced-motion` and provide equivalent static indicators.
- Never continuously animate idle connections or imply traffic that is not backed by current data.

## Interaction and accessibility

- Every graphical node and connection must have a keyboard-accessible equivalent and textual detail.
- Use visible focus, adequate contrast, semantic buttons, descriptive labels, and status copy.
- Critical actions require clear target and consequence. Approval/rejection decisions remain governed and auditable.
- Filtering by project, runtime, state, severity, sender, recipient, or time must not reset the user's selected context unexpectedly.
- Error and empty states must explain data source availability and recovery action.

## Source-of-truth rules

- Messages/agent demands describe communication, requests, reply relationships, senders, recipients, dispatch, and response waits.
- Work packages and task executions describe governed ownership and execution contracts.
- Progress checkpoints describe verified state, blockers, failures, heartbeat loss, evidence, and resume points.
- Governance approvals describe pending authorization and decisions.
- Notifications mirror attention-worthy events; they are not an independent decision record.
- ForgeRouter telemetry adds recent routing/runtime evidence but does not replace durable work state.
- Porthus, Aramis, and Dartan use runtime-native profile structures linked to Foundation. They must not be represented as fake internal Hermes profiles.

## Design constraints

- Use only the fonts, colors, spacing, component styles, and semantic conventions defined here and in `frontend/src/index.css`.
- Preserve the existing sidebar shell, ForgeHub logo, theme behavior, and locale system.
- No marketing-page hero treatment, novelty gradients, glass effects, invented agent activity, or decorative metrics.

# Extractable Components

## Layout Components

## AppLayout

- Source: `frontend/src/components/layout/AppLayout.tsx`
- Category: layout
- Description: Authenticated application shell with persistent sidebar, route outlet, responsive page gutters, full-bleed routing rules, and a global assistant drawer that shrinks the main content.
- Extractable props: none; route state is read from `useLocation`, and children render through React Router's `Outlet`.
- Hardcoded: full-bleed path prefixes, desktop/mobile padding rules, `h-screen` flex structure, `Sidebar`, `AssistantDrawer`, background/border/overflow classes.

## Sidebar

- Source: `frontend/src/components/layout/Sidebar.tsx`
- Category: layout
- Description: Persistent responsive navigation with desktop icon-rail mode, mobile off-canvas mode, collapsible sections/groups, Messages unread badge, search palette, user controls, and notifications.
- Extractable props: none; active route, permissions, user, navigation sections, unread count, and collapsed state are read internally.
- Hardcoded: 768px mobile breakpoint, local-storage keys, widths `w-16`/`w-60`/`w-64`, `NAV_SECTIONS`, Lucide menu/panel/shield/search icons, ForgeHub `Logo`/`LogoMark`, footer user-row composition, Ctrl/Command+K hint, all Tailwind classes.

## CommandPalette

- Source: `frontend/src/components/layout/CommandPalette.tsx`
- Category: layout
- Description: Permission-aware keyboard navigation overlay that flattens sidebar sections into a searchable command list.
- Extractable props: `sections` (`NavSectionEntry[]`), `open` (boolean), `onOpenChange` (`(open: boolean) => void`).
- Hardcoded: Ctrl/Command+K, Escape/Arrow/Enter behavior, Lucide `Search` and `X`, 15vh desktop top offset, max width `max-w-lg`, translated labels, permission filtering, overlay and result-row classes.

## NotificationBell

- Source: `frontend/src/components/layout/NotificationBell.tsx`
- Category: layout
- Description: Sidebar notification trigger with unread counter and a compact dropdown of recent persistent operational notifications.
- Extractable props: `collapsed` (boolean), `stretch` (boolean, default `true`).
- Hardcoded: Bell icon, severity colors, maximum 20 preview rows, `9+` count cap, relative-time thresholds, dropdown width `w-72`, `/notifications` destination, translated labels and all CSS classes.

## UserSettingsMenu

- Source: `frontend/src/components/layout/UserSettingsMenu.tsx`
- Category: layout
- Description: Account avatar/gear trigger with account, password, language, theme, settings, and logout workflows plus modal forms.
- Extractable props: `collapsed` (boolean), `stretch` (boolean, default `true`), `avatarUrl` (string/null), `usernameInitial` (string), `avatarTrigger` (boolean, default `false`).
- Hardcoded: menu actions and order, light/dark/system themes, pt-BR/en/es language options, Lucide account/security/theme/logout icons, dropdown width `w-48`, modal width `max-w-sm`, photo picker behavior, password minimum of 8 characters, all labels via i18n and all Tailwind classes.

## AssistantDrawer

- Source: `frontend/src/components/chat/AssistantDrawer.tsx`
- Category: layout
- Description: Global route-scoped assistant panel that hosts `ChatPane`, supports hidden screen context/form-fill instructions, and occupies space beside the page instead of covering it.
- Extractable props: none; open state, context, seed, target agent, and registered form are sourced from `assistantStore`, while the route supplies the session tab id.
- Hardcoded: manual grounding note, `forgehub-fill` fenced JSON protocol, Escape handling, route-derived `assistant:` tab key, desktop drawer sizing/placement, mobile behavior, Bot/X icons, assistant header and all CSS.

## DatabaseLayout

- Source: `frontend/src/pages/database/DatabaseLayout.tsx`
- Category: layout
- Description: Nested full-height database workspace layout with instance, database, and schema selectors above schema/diagram/query child routes.
- Extractable props: none; selected instance/database/schema are provided by `SchemaProvider`, and page content renders through `Outlet`.
- Hardcoded: `Database` and `ChevronDown` icons, selector order and labels (`Instance`, `Database`, `Schema`), header/table-count structure, monospace selection summary, compact selector styling.

## Basic Components

## Button

- Source: `frontend/src/components/ui/button.tsx`
- Category: basic
- Description: Shared accessible button primitive with semantic color and size variants.
- Extractable props: `variant` (`default`, `destructive`, `outline`, `secondary`, `ghost`, `link`; default `default`), `size` (`default`, `sm`, `lg`, `icon`; default `default`), plus native button props.
- Hardcoded: rounded-md shape, focus ring, disabled behavior, variant color-token mappings, heights/padding, typography and transition classes.

## Badge

- Source: `frontend/src/components/ui/badge.tsx`
- Category: basic
- Description: Compact pill tag for status, category, warning, success, or destructive state.
- Extractable props: `variant` (`default`, `secondary`, `destructive`, `outline`, `success`, `warning`; default `default`), plus native div props.
- Hardcoded: pill radius, border/padding/type styles, emerald success palette, amber warning palette, token-backed default/destructive/outline colors.

## Card

- Source: `frontend/src/components/ui/card.tsx`
- Category: basic
- Description: Composable bordered surface with header, title, description, content, and footer primitives.
- Extractable props: native div/heading/paragraph props and `className` for `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, and `CardFooter`.
- Hardcoded: `rounded-lg`, token-backed border/card colors, subtle shadow, 24px section padding, 24px title type, header vertical spacing, footer flex alignment.

## Input

- Source: `frontend/src/components/ui/input.tsx`
- Category: basic
- Description: Shared single-line form control with standard sizing, focus, placeholder, file-input, and disabled states.
- Extractable props: all native HTML input props, including `value`, `onChange`, `type`, `placeholder`, and `disabled`.
- Hardcoded: `h-10`, rounded-md border, background/input tokens, 14px text, focus ring, placeholder and disabled classes.

## Select

- Source: `frontend/src/components/ui/select.tsx`
- Category: basic
- Description: Shared native select control styled consistently with ForgeHub form fields.
- Extractable props: all native HTML select props, including `value`, `onChange`, `disabled`, and child options.
- Hardcoded: control height, rounded border, token colors, padding, focus ring and disabled styles.

## Textarea

- Source: `frontend/src/components/ui/textarea.tsx`
- Category: basic
- Description: Shared multiline form control with consistent border, typography, focus, and disabled states.
- Extractable props: all native HTML textarea props, including `value`, `onChange`, `placeholder`, `rows`, and `disabled`.
- Hardcoded: minimum height, rounded border, background/token colors, padding, focus ring, placeholder and disabled styles.

## Label

- Source: `frontend/src/components/ui/label.tsx`
- Category: basic
- Description: Shared form label primitive with consistent compact typography and disabled-peer treatment.
- Extractable props: all native HTML label props, especially `htmlFor` and `className`.
- Hardcoded: 14px medium typography, line-height and peer-disabled classes.

## Table

- Source: `frontend/src/components/ui/table.tsx`
- Category: basic
- Description: Responsive shared data-table family comprising table, header, body, row, head, and cell primitives.
- Extractable props: native element props and `className` for `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, and `TableCell`.
- Hardcoded: horizontal overflow wrapper, full-width 14px table, border/divider behavior, selected-row state, hover background, 48px header height, cell padding/alignment.

## Tabs

- Source: `frontend/src/components/ui/tabs.tsx`
- Category: basic
- Description: Controlled tab system with list, triggers, and conditionally rendered tab panels.
- Extractable props: `value` (active tab string), `onValueChange`, trigger `value`, trigger `title`, plus children and `className` for all parts.
- Hardcoded: muted rounded tab-list surface, active background/shadow, inactive hover colors, trigger padding/type, ARIA tab roles.

## Breadcrumb

- Source: `frontend/src/components/ui/breadcrumb.tsx`
- Category: basic
- Description: Horizontal route hierarchy with linked ancestors and a highlighted current item.
- Extractable props: `items` (`{ label: string; href?: string }[]`), `className`.
- Hardcoded: Lucide `ChevronRight`, separator sizing/color, muted base text, foreground current item, hover transition and ARIA label `Breadcrumb`.

## ConfirmDialog

- Source: `frontend/src/components/ui/confirm-dialog.tsx`
- Category: basic
- Description: Accessible confirmation modal with semantic destructive/default treatments, icon choices, loading state, and inline error display.
- Extractable props: `open`, `title`, `description`, `confirmLabel`, `cancelLabel`, `variant` (`destructive`/`default`), `icon` (`trash`/`warning`/`wrench`), `loading`, `error`, `onConfirm`, `onCancel`.
- Hardcoded: default translated strings, default destructive variant, icon inference, Escape/backdrop cancellation, `max-w-md`, colored top accent, Lucide Trash/Alert/Wrench/Loader icons, 88px minimum action widths and animation classes.

## TokenField

- Source: `frontend/src/components/ui/token-field.tsx`
- Category: basic
- Description: Secret/token input that combines password masking, visibility toggle, and clipboard copy feedback.
- Extractable props: `value`, `onChange`, `className`, plus native input props except `value`, `onChange`, and `type`.
- Hardcoded: Eye/EyeOff and Copy/Check icons, password hidden by default, 1.5-second copied state, monospace text, right-side action placement, `autoComplete="off"`.

## AgentAvatar

- Source: `frontend/src/components/AgentAvatar.tsx`
- Category: basic
- Description: Circular agent image with deterministic one- or two-letter initials fallback and standardized sizes.
- Extractable props: `name`, `avatarDataUrl`, `imageAlt` (default empty), `size` (`sm`, `md`, `lg`; default `md`), `className`.
- Hardcoded: circular bordered muted surface, uppercase initials, `sm` 36px, `md` 48px, `lg` 80px sizes, cover-fit image; companion validation accepts JPEG/PNG/WebP up to 512 KiB.

## SearchFilterInput

- Source: `frontend/src/components/SearchFilterInput.tsx`
- Category: basic
- Description: Search-icon-prefixed controlled filter used by shared document and knowledge trees.
- Extractable props: `value`, `onChange`, `placeholder`, `className`.
- Hardcoded: Lucide `Search`, minimum width 16rem, left icon positioning and muted color, input left padding `pl-8`.

## AssistantToggleButton

- Source: `frontend/src/components/AssistantToggleButton.tsx`
- Category: basic
- Description: Large icon-only control that toggles the global assistant while preserving enough space for the animated robot mark.
- Extractable props: `className`, `openTitle`; legacy `size` is accepted but intentionally ignored.
- Hardcoded: 44px square click target, `AssistantRobotIcon` at 32px, assistant store wiring, open-state secondary treatment, translated accessible labels and hover classes.

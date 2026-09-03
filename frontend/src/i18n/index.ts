import i18n from "i18next";
import { initReactI18next } from "react-i18next";

// UI language ("en" | "pt-BR") is independent of the AI chat's
// CHAT_RESPONSE_LANGUAGE (backend/app/core/config.py) -- this one covers the
// whole app shell (sidebar, dialogs, forms), not agent replies. Persisted
// per-user via User.ui_language (see useSyncUiLanguage in useAuth.ts), which
// mirrors this into localStorage so the login page (no user yet) and the
// first paint before that sync effect runs still pick up the last choice.
export const UI_LANGUAGE_STORAGE_KEY = "forgehub-ui-language";

export const SUPPORTED_UI_LANGUAGES = ["en", "pt-BR", "es"] as const;

export const NAMESPACES = ["artifact", "auditor", "crons", "deploy", "forgerouter", "vpn"] as const;
export type UiLanguage = (typeof SUPPORTED_UI_LANGUAGES)[number];

function initialLanguage(): UiLanguage {
  const stored = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
  return (SUPPORTED_UI_LANGUAGES as readonly string[]).includes(stored ?? "")
    ? (stored as UiLanguage)
    : "pt-BR";
}

// Each domain page group owns its own namespace file
// (src/i18n/locales/<lng>/<namespace>.json) instead of one giant shared
// JSON per language -- lets unrelated pages be translated independently
// (including in parallel) without every change touching the same file.
// "common" is the app shell/nav namespace (Sidebar, CommandPalette,
// UserSettingsMenu, LoginPage, ...) and is also `defaultNS`, so existing
// unprefixed t("nav.dashboard")-style calls keep resolving against it.
// Adding a namespace is just adding the file pair here -- no manual
// registration needed, this glob picks it up automatically.
const modules = import.meta.glob<{ default: Record<string, unknown> }>("./locales/*/*.json", {
  eager: true,
});

const resources: Record<string, Record<string, Record<string, unknown>>> = {};
const namespaces = new Set<string>();

for (const [path, mod] of Object.entries(modules)) {
  const match = path.match(/\.\/locales\/([^/]+)\/([^/]+)\.json$/);
  if (!match) continue;
  const [, lng, ns] = match;
  resources[lng] ??= {};
  resources[lng][ns] = mod.default;
  namespaces.add(ns);
}

i18n.use(initReactI18next).init({
  ns: Array.from(new Set([...namespaces, ...NAMESPACES])),
  resources,
  lng: initialLanguage(),
  fallbackLng: "pt-BR",
  defaultNS: "common",
  interpolation: { escapeValue: false },
  // Resources are bundled statically above (no backend/http-loader), so
  // init completes synchronously -- no Suspense/loading gate needed around
  // the app root.
});

i18n.on("languageChanged", (lng) => {
  localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, lng);
});

export default i18n;

export type Namespace = (typeof NAMESPACES)[number];

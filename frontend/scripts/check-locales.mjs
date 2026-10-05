import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const languages = ['pt-BR', 'en', 'es'];

function flatten(value, prefix = '', out = new Map()) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => flatten(item, `${prefix}[${index}]`, out));
  } else if (value !== null && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      flatten(item, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.set(prefix, value);
  }
  return out;
}

function tokens(text) {
  return [...String(text).matchAll(/{{\s*([\w.]+)(?:\s*,[^}]*)?\s*}}/g)]
    .map((match) => match[1]).sort().join(',');
}

function technicalTokens(text) {
  return [...String(text).matchAll(/\b(?:[a-z0-9_.-]+\.(?:py|json|tsx?|jsx?|md|env|sh|sql|ya?ml|log)|[a-z][a-z0-9]*(?:_[a-z0-9]+){2,})\b/gi)]
    .map((match) => match[0]);
}

export function validateLocales(root) {
  const errors = [];
  const filesByLanguage = Object.fromEntries(languages.map((language) => [
    language,
    new Set(readdirSync(join(root, language)).filter((file) => file.endsWith('.json'))),
  ]));
  const namespaces = new Set(Object.values(filesByLanguage).flatMap((files) => [...files]));

  for (const namespace of [...namespaces].sort()) {
    const catalogs = {};
    for (const language of languages) {
      if (!filesByLanguage[language].has(namespace)) {
        errors.push(`${language}/${namespace}: namespace missing`);
        catalogs[language] = new Map();
        continue;
      }
      catalogs[language] = flatten(JSON.parse(readFileSync(join(root, language, namespace), 'utf8')));
    }
    const keys = new Set(Object.values(catalogs).flatMap((catalog) => [...catalog.keys()]));
    for (const key of keys) {
      const reference = catalogs['pt-BR'].get(key);
      for (const language of languages) {
        if (!filesByLanguage[language].has(namespace)) continue;
        if (!catalogs[language].has(key)) {
          errors.push(`${language}/${namespace}: missing ${key}`);
        } else if (reference !== undefined && typeof catalogs[language].get(key) !== typeof reference) {
          errors.push(`${language}/${namespace}: type differs at ${key}`);
        } else if (typeof reference === 'string' && tokens(catalogs[language].get(key)) !== tokens(reference)) {
          errors.push(`${language}/${namespace}: interpolation differs at ${key}; expected ${tokens(reference)}`);
        } else if (typeof reference === 'string') {
          for (const token of technicalTokens(reference)) {
            if (!String(catalogs[language].get(key)).includes(token)) {
              errors.push(`${language}/${namespace}: technical token differs at ${key}; expected ${token}`);
            }
          }
        }
      }
    }
  }
  return errors;
}

if (process.argv[1]?.endsWith('check-locales.mjs')) {
  const root = process.argv[2] ?? new URL('../src/i18n/locales/', import.meta.url).pathname;
  const errors = validateLocales(root);
  if (errors.length) {
    console.error(errors.slice(0, 40).join('\n'));
    if (errors.length > 40) console.error(`... and ${errors.length - 40} more errors`);
    process.exitCode = 1;
  } else {
    console.log(`Locale catalogs match in ${languages.join(', ')}.`);
  }
}

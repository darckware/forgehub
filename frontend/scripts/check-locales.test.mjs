import { strict as assert } from 'node:assert';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { validateLocales } from './check-locales.mjs';

test('rejects missing keys and incompatible interpolation tokens', () => {
  const root = mkdtempSync(join(tmpdir(), 'forgehub-locales-'));
  try {
    for (const locale of ['pt-BR', 'en', 'es']) mkdirSync(join(root, locale));
    writeFileSync(join(root, 'pt-BR', 'common.json'), JSON.stringify({ greeting: 'Olá, {{name}}', title: 'Início' }));
    writeFileSync(join(root, 'en', 'common.json'), JSON.stringify({ greeting: 'Hello, {{name}}', title: 'Home' }));
    writeFileSync(join(root, 'es', 'common.json'), JSON.stringify({ greeting: 'Hola, {{person}}' }));
    const errors = validateLocales(root).join('\n');
    assert.match(errors, /es\/common\.json.*title/);
    assert.match(errors, /es\/common\.json.*greeting.*name/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('protects file and configuration identifiers inside translated copy', () => {
  const root = mkdtempSync(join(tmpdir(), 'forgehub-locales-'));
  try {
    for (const locale of ['pt-BR', 'en', 'es']) mkdirSync(join(root, locale));
    writeFileSync(join(root, 'pt-BR', 'common.json'), JSON.stringify({ help: 'Use telegram_audio_transcriber.py' }));
    writeFileSync(join(root, 'en', 'common.json'), JSON.stringify({ help: 'Use telegram_audio_transcriber.py' }));
    writeFileSync(join(root, 'es', 'common.json'), JSON.stringify({ help: 'Use telegrama_audio_transcriber.py' }));
    assert.match(validateLocales(root).join('\n'), /es\/common\.json.*telegram_audio_transcriber\.py/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

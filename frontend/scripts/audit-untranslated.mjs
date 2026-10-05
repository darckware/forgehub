import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const root = path.resolve(import.meta.dirname, '../src');
const roots = ['pages', 'components'];
const attributes = new Set(['title', 'placeholder', 'aria-label', 'alt', 'description', 'confirmLabel', 'cancelLabel']);
const findings = [];
process.stdout.on('error', (error) => {
  if (error.code === 'EPIPE') process.exit(0);
  throw error;
});

function walkDirectory(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) walkDirectory(fullPath);
    else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) inspect(fullPath);
  }
}

function inspect(fullPath) {
  const source = fs.readFileSync(fullPath, 'utf8');
  const ast = ts.createSourceFile(fullPath, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const relativePath = path.relative(root, fullPath);
  const add = (node, kind, raw) => {
    const value = raw.replace(/\s+/g, ' ').trim();
    if (!/[\p{L}]/u.test(value)) return;
    const line = ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1;
    findings.push({ file: relativePath, line, kind, value });
  };
  const visit = (node) => {
    if (ts.isJsxText(node)) add(node, 'text', node.text);
    if (ts.isJsxAttribute(node) && attributes.has(node.name.text) && node.initializer && ts.isStringLiteral(node.initializer)) {
      add(node, node.name.text, node.initializer.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(ast);
}

for (const section of roots) walkDirectory(path.join(root, section));
if (process.argv.includes('--json')) {
  process.stdout.write(`${JSON.stringify(findings, null, 2)}\n`);
} else {
  const counts = new Map();
  for (const item of findings) counts.set(item.file, (counts.get(item.file) ?? 0) + 1);
  for (const [file, count] of [...counts].sort((a, b) => b[1] - a[1])) {
    process.stdout.write(`${String(count).padStart(3)} ${file}\n`);
  }
  process.stdout.write(`${findings.length} candidates in ${counts.size} files. Review context: technical text and brands may be intentional.\n`);
}

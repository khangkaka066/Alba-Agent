import test from 'node:test';
import assert from 'node:assert/strict';
import { markdownBlocks, safeLink } from '../src/lib/markdown.mjs';

test('assistant Markdown preserves code, tables and lists as distinct readable blocks', () => {
  const blocks = markdownBlocks('# Result\n\n**Ready** to review.\n\n```js\nconst total = 42;\n```\n\n| File | Status |\n| --- | --- |\n| app.js | Added |\n\n1. Review\n2. Accept');
  assert.deepEqual(blocks.map(x => x.kind), ['heading', 'paragraph', 'code', 'table', 'list']);
  assert.equal(blocks[2].text, 'const total = 42;');
  assert.deepEqual(blocks[3].rows, [['app.js', 'Added']]);
  assert.deepEqual(blocks[4].items, ['Review', 'Accept']);
});

test('Markdown links never execute script or open local/session URLs', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'file:///etc/passwd', 'vbscript:foo', '/settings']) assert.equal(safeLink(value), null);
  assert.equal(safeLink('https://example.com/docs'), 'https://example.com/docs');
  assert.equal(safeLink('#result'), '#result');
  assert.equal(markdownBlocks('<img src=x onerror=alert(1)>')[0].text, '<img src=x onerror=alert(1)>');
});

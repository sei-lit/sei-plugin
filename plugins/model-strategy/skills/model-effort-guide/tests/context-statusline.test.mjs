import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const script = fileURLToPath(new URL('../scripts/context-statusline.sh', import.meta.url));

function render({ used, size, over = false, warn = 75 }) {
  const result = spawnSync('bash', [script], {
    encoding: 'utf8',
    env: { ...process.env, MODEL_STRATEGY_CTX_WARN: String(warn) },
    input: JSON.stringify({
      model: { display_name: 'Test Model' },
      context_window: {
        used_percentage: used / size * 100,
        total_input_tokens: used,
        context_window_size: size,
      },
      exceeds_200k_tokens: over,
      cost: { total_cost_usd: 1.92 },
    }),
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('large window: 250k input at 25% does not trigger a capacity warning', () => {
  const output = render({ used: 250000, size: 1000000, over: true });
  assert.match(output, /25%.*250k\/1000k/);
  assert.ok(!output.includes('\x1b[31m'));
  assert.ok(!output.includes('⚠'));
});

test('high occupancy prompts inspection without prescribing conversation clearing', () => {
  const output = render({ used: 156000, size: 200000 });
  assert.match(output, /78%.*156k\/200k/);
  assert.ok(output.includes('\x1b[31m'));
  assert.ok(output.includes('⚠'));
  assert.ok(!output.includes('/clear'));
});

test('configured warning threshold applies at its boundary', () => {
  const input = { used: 120000, size: 200000 };
  assert.ok(!render(input).includes('⚠'));
  assert.ok(render({ ...input, warn: 60 }).includes('⚠'));
});

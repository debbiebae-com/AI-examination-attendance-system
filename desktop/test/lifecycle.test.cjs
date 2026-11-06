const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const fs = require('node:fs');
const path = require('node:path');
const { allowNavigation, launcherArgs, runLauncher, stopAfterStartup } = require('../lifecycle.cjs');
const owner = '12345678-1234-1234-abcd-123456789abc';

test('only the local dashboard origin may navigate inside the desktop shell', () => {
  for (const url of ['http://127.0.0.1:3000', 'http://127.0.0.1:3000/#activity']) assert.equal(allowNavigation(url), true);
  for (const url of ['https://example.com', 'file:///etc/passwd', 'javascript:alert(1)', 'http://127.0.0.1:8000', 'http://127.0.0.1:3000.evil.com', 'not a url']) assert.equal(allowNavigation(url), false);
});
test('PowerShell receives a path with spaces as a single argument, plus non-browser ownership', () => {
  const root = 'C:\\Users\\Deborah Thompson\\ExamLens';
  const args = launcherArgs(root, 'Start', owner);
  assert.equal(args[args.indexOf('-File') + 1], path.join(root, 'start-demo.ps1'));
  assert.equal(args[args.indexOf('-Owner') + 1], owner);
  assert.ok(args.includes('-NoBrowser'));
  assert.throws(() => launcherArgs(root, 'Prepare', owner));
  assert.throws(() => launcherArgs(root, 'Start', '; stop-process *'));
});
test('service commands run hidden, without a shell, and wait for process completion', async () => {
  const logs = [];
  let invocation;
  const spawnProcess = (...args) => {
    invocation = args;
    const child = new EventEmitter();
    child.stdout = new PassThrough(); child.stderr = new PassThrough();
    setImmediate(() => { child.stdout.write('Ready'); child.emit('close', 0); });
    return child;
  };
  await runLauncher('/checkout', 'Start', owner, { spawnProcess, log: (line) => logs.push(line) });
  assert.equal(invocation[0], 'powershell.exe');
  assert.equal(invocation[2].shell, false);
  assert.equal(invocation[2].windowsHide, true);
  assert.deepEqual(logs, ['Ready']);
});
test('service failure is surfaced rather than loading an unready dashboard', async () => {
  const spawnProcess = () => {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    setImmediate(() => child.emit('close', 1));
    return child;
  };
  await assert.rejects(runLauncher('/checkout', 'Start', owner, { spawnProcess }), /Start failed/);
});
test('closing during startup waits before issuing Stop', async () => {
  let ready;
  let stopped = false;
  const startup = new Promise((resolve) => { ready = resolve; });
  const stop = stopAfterStartup(startup, async () => { stopped = true; });
  await new Promise(setImmediate);
  assert.equal(stopped, false);
  ready();
  await stop;
  assert.equal(stopped, true);
});
test('failed startup still permits cleanup; failed shutdown propagates', async () => {
  let stopped = false;
  await stopAfterStartup(Promise.reject(new Error('start')), async () => { stopped = true; });
  assert.equal(stopped, true);
  await assert.rejects(stopAfterStartup(Promise.resolve(), async () => { throw new Error('camera still running'); }), /camera still running/);
});
test('desktop entry points keep renderer privileges disabled and desktop shutdown ownership-scoped', () => {
  const main = fs.readFileSync(path.join(__dirname, '../main.cjs'), 'utf8');
  const ps = fs.readFileSync(path.join(__dirname, '../../start-demo.ps1'), 'utf8');
  assert.ok(main.includes('nodeIntegration: false'));
  assert.ok(main.includes('contextIsolation: true'));
  assert.ok(main.includes('sandbox: true'));
  assert.ok(main.includes("app.requestSingleInstanceLock()"));
  assert.ok(main.includes('setWindowOpenHandler'));
  assert.ok(ps.includes('$state.owner -ne $Owner'));
  assert.ok(ps.includes('if (-not $NoBrowser)'));
  assert.ok(ps.includes('if ($Desktop)'));
});

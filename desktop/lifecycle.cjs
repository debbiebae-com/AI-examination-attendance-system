const { spawn } = require('node:child_process');
const path = require('node:path');

const DASHBOARD_URL = 'http://127.0.0.1:3000';
function allowNavigation(url) {
  try { return new URL(url).origin === DASHBOARD_URL; }
  catch { return false; }
}
function launcherArgs(root, mode, owner) {
  if (!['Start', 'Stop'].includes(mode)) throw new Error('Unsupported desktop lifecycle action');
  if (!/^[a-f0-9-]{36}$/.test(owner)) throw new Error('Invalid desktop owner');
  return ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'start-demo.ps1'), '-Mode', mode, '-NoBrowser', '-Owner', owner];
}
function runLauncher(root, mode, owner, { spawnProcess = spawn, log = () => {} } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawnProcess('powershell.exe', launcherArgs(root, mode, owner), { cwd: root, windowsHide: true, shell: false, stdio: ['ignore', 'pipe', 'pipe'] });
    child.stdout.on('data', (chunk) => log(chunk.toString()));
    child.stderr.on('data', (chunk) => log(chunk.toString()));
    child.once('error', reject);
    child.once('close', (code) => code === 0 ? resolve() : reject(new Error(`${mode} failed (exit ${code ?? 'unknown'}). See .demo-runtime logs. Run Prepare Desktop App.cmd if setup or app files changed.`)));
  });
}
// Closing during startup must wait for the startup mutex to be released before Stop.
async function stopAfterStartup(startup, stop) {
  try { await startup; } catch { /* Start cleans up its own failed attempt. Still check Stop. */ }
  await stop();
}
module.exports = { DASHBOARD_URL, allowNavigation, launcherArgs, runLauncher, stopAfterStartup };

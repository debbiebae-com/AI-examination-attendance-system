const { app, BrowserWindow, dialog, Menu, shell } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { randomUUID } = require('node:crypto');
const { DASHBOARD_URL, allowNavigation, runLauncher, stopAfterStartup } = require('./lifecycle.cjs');
const root = path.resolve(__dirname, '..');
const runtime = path.join(root, '.demo-runtime');
const owner = randomUUID();
let window;
let startup;
let closing = false;
let allowQuit = false;
app.setName('ExamLens');
if (process.platform === 'win32') app.setAppUserModelId('ExamLens.Desktop');

function log(message) {
  try {
    fs.mkdirSync(runtime, { recursive: true });
    fs.appendFileSync(path.join(runtime, 'desktop.log'), `${new Date().toISOString()} ${message}\n`, { mode: 0o600 });
  } catch { /* A log failure must not strand the running app. */ }
}
const launch = (mode) => runLauncher(root, mode, owner, { log });
const status = (message) => window && !window.isDestroyed() ? window.loadFile(path.join(__dirname, 'loading.html'), { query: { message } }) : Promise.resolve();

async function closeApp() {
  if (closing || allowQuit) return;
  closing = true;
  try {
    await status('Closing ExamLens safely. Waiting for startup or active camera work to finish…');
    await stopAfterStartup(startup, () => launch('Stop'));
    allowQuit = true;
    app.quit();
  } catch (error) {
    log(error.message);
    await dialog.showMessageBox(window, { type: 'warning', title: 'ExamLens is still open', message: 'A demonstration task could not be stopped safely.', detail: 'Finish or cancel the camera/enrollment task, then close ExamLens again. Services have been left running to protect your work. Logs are in .demo-runtime.', buttons: ['Keep ExamLens open'] });
    closing = false;
    if (window && !window.isDestroyed()) await window.loadURL(DASHBOARD_URL).catch(() => status('Services need attention. See .demo-runtime logs, or use Stop Demo.cmd and reopen the app.'));
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
  });
  app.on('before-quit', (event) => {
    if (!allowQuit) { event.preventDefault(); void closeApp(); }
  });
  app.whenReady().then(async () => {
    if (process.platform !== 'win32') {
      dialog.showErrorBox('Windows presentation app', 'This desktop launch mode uses the prepared Windows checkout. See desktop/README.md.');
      allowQuit = true;
      app.quit();
      return;
    }
    window = new BrowserWindow({
      title: 'ExamLens', width: 1440, height: 940, minWidth: 760, minHeight: 600,
      backgroundColor: '#1a1a1a', icon: path.join(__dirname, 'icon.ico'), show: false,
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true, webviewTag: false },
    });
    window.once('ready-to-show', () => window.show());
    window.on('close', (event) => { if (!allowQuit) { event.preventDefault(); void closeApp(); } });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    for (const eventName of ['will-navigate', 'will-redirect']) {
      window.webContents.on(eventName, (event, url) => { if (!allowNavigation(url)) event.preventDefault(); });
    }
    window.webContents.on('page-title-updated', (event) => { event.preventDefault(); window.setTitle('ExamLens'); });
    window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    window.webContents.session.setPermissionCheckHandler(() => false);
    window.webContents.session.on('will-download', (_event, item) => {
      // Keep ordinary local CSV exports working without granting the renderer filesystem APIs.
      item.setSaveDialogOptions({ title: 'Save ExamLens export', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
    });
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { label: 'ExamLens', submenu: [{ label: 'Open private log folder', click: () => { fs.mkdirSync(runtime, { recursive: true }); void shell.openPath(runtime); } }, { type: 'separator' }, { label: 'Exit', accelerator: 'Alt+F4', click: () => void closeApp() }] },
      { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] },
    ]));
    startup = (async () => {
      await status('Starting your local backend and dashboard. No camera connection settings are changed.');
      if (!closing) await launch('Start');
    })();
    try {
      await startup;
      if (!closing) await window.loadURL(DASHBOARD_URL);
    } catch (error) {
      log(error.message);
      if (closing) return;
      const choice = await dialog.showMessageBox(window, { type: 'error', title: 'ExamLens could not start', message: 'The local application is not ready.', detail: `${error.message}\n\nClose old manual servers if ports 8000/3000 are occupied. Keep .env and logs private.`, buttons: ['Close', 'Open log folder'], defaultId: 0 });
      if (choice.response === 1) { fs.mkdirSync(runtime, { recursive: true }); await shell.openPath(runtime); }
      void closeApp();
    }
  }).catch((error) => {
    log(error.message);
    if (startup) void closeApp();
    else { dialog.showErrorBox('ExamLens startup error', 'The desktop window could not be created. See .demo-runtime/desktop.log.'); allowQuit = true; app.quit(); }
  });
}

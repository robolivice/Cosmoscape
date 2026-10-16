const { app, BrowserWindow, WebContentsView, dialog, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");

app.commandLine.appendSwitch("ignore-gpu-blocklist");
app.commandLine.appendSwitch("enable-gpu-rasterization");
app.commandLine.appendSwitch("force_high_performance_gpu");

let backend = null;
let win = null;
let loadingView = null;
let appView = null;
let quitting = false;

function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, "127.0.0.1", () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
  });
}

function backendCommand(port) {
  if (app.isPackaged) {
    const name = process.platform === "win32" ? "cosmoscape-backend.exe" : "cosmoscape-backend";
    const dir = path.join(process.resourcesPath, "backend");
    return { cmd: path.join(dir, name), args: ["--port", String(port)], cwd: dir };
  }
  const py = process.platform === "win32" ? "python" : "python3";
  return { cmd: py, args: ["main.py", "--port", String(port)], cwd: path.join(__dirname, "..") };
}

async function waitForBackend(port) {
  for (let i = 0; i < 240; i++) {
    if (!backend) return false;
    try {
      const r = await fetch("http://127.0.0.1:" + port + "/api/health");
      if (r.ok) return true;
    } catch (e) {}
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function killBackend() {
  if (backend) {
    try { backend.kill(); } catch (e) {}
    backend = null;
  }
}

async function waitForOnline(wc) {
  for (let i = 0; i < 120; i++) {
    if (wc.isDestroyed()) return;
    try {
      const txt = await wc.executeJavaScript(
        "(document.getElementById('status') || {}).textContent || ''"
      );
      if (txt.trim() && !/^Verifying/i.test(txt.trim())) return;
    } catch (e) {}
    await new Promise((r) => setTimeout(r, 250));
  }
}

async function start() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "icon.png"),
  });

  const prefs = { contextIsolation: true, nodeIntegration: false, devTools: !app.isPackaged };
  appView = new WebContentsView({ webPreferences: { ...prefs, backgroundThrottling: false } });
  appView.setBackgroundColor("#000000");
  loadingView = new WebContentsView({ webPreferences: prefs });
  loadingView.setBackgroundColor("#00000000");   // transparent so the page can fade

  win.contentView.addChildView(appView);          // underneath
  win.contentView.addChildView(loadingView);      // on top
  const fit = () => {
    const b = win.getContentBounds();
    const r = { x: 0, y: 0, width: b.width, height: b.height };
    appView.setBounds(r);
    loadingView.setBounds(r);
  };
  fit();
  win.on("resize", fit);

  loadingView.webContents.loadFile(path.join(__dirname, "loading.html"));

  const port = await freePort();
  const c = backendCommand(port);
  backend = spawn(c.cmd, c.args, {
    cwd: c.cwd,
    windowsHide: true,
    stdio: app.isPackaged ? "ignore" : "inherit",
  });
  backend.on("exit", () => {
    const wasRunning = backend !== null;
    backend = null;
    if (wasRunning && !quitting) {
      dialog.showErrorBox("Cosmoscape", "The backend stopped unexpectedly.");
      app.quit();
    }
  });

  const ok = await waitForBackend(port);
  if (!ok) {
    dialog.showErrorBox("Cosmoscape", "The backend did not start.");
    app.quit();
    return;
  }

  const base = "http://127.0.0.1:" + port;
  appView.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  appView.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(base)) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });
  appView.webContents.loadURL(base);

  await waitForOnline(appView.webContents);
  if (win.isDestroyed() || loadingView.webContents.isDestroyed()) return;

  await loadingView.webContents.executeJavaScript("document.body.classList.add('out')").catch(() => {});
  await new Promise((r) => setTimeout(r, 750));   // let the fade finish
  if (win.isDestroyed()) return;
  win.contentView.removeChildView(loadingView);
  loadingView.webContents.close();
  loadingView = null;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(start);
}

app.on("before-quit", () => { quitting = true; killBackend(); });
app.on("will-quit", killBackend);
app.on("window-all-closed", () => app.quit());
const { app, BrowserWindow, WebContentsView, dialog, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
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
let backendPort = null;

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

function spawnBackend(port) {
  const c = backendCommand(port);
  const proc = spawn(c.cmd, c.args, {
    cwd: c.cwd,
    windowsHide: true,
    stdio: app.isPackaged ? "ignore" : "inherit",
  });
  backend = proc;
  proc.on("exit", () => {
    if (backend !== proc) return;   // old or killed process, ignore
    backend = null;
    if (!quitting) {
      dialog.showErrorBox("Cosmoscape", "The backend stopped unexpectedly.");
      app.quit();
    }
  });
  return proc;
}

function killBackend() {
  if (backend) {
    const proc = backend;
    backend = null;
    try {
      if (process.platform === "win32") {
        spawnSync("taskkill", ["/pid", String(proc.pid), "/T", "/F"]);
      } else {
        proc.kill();
      }
    } catch (e) {}
  }
}

async function restartBackend() {
  const old = backend;
  backend = null;
  if (old) {
    const gone = new Promise((r) => old.once("exit", r));
    try {
      if (process.platform === "win32") {
        spawnSync("taskkill", ["/pid", String(old.pid), "/T", "/F"]);
      } else {
        old.kill();
      }
    } catch (e) {}
    await Promise.race([gone, new Promise((r) => setTimeout(r, 3000))]);
  }
  spawnBackend(backendPort);
  return waitForBackend(backendPort);
}

function watchBackend() {
  const root = path.join(__dirname, "..");
  const skip = /(^|[\\/])(node_modules|release|build|dist|__pycache__|venv|\.venv|\.git)([\\/]|$)/;
  let timer = null, busy = false, again = false;

  const run = async () => {
    if (busy) { again = true; return; }
    busy = true;
    console.log("[dev] Python changed, restarting backend...");
    const ok = await restartBackend();
    if (ok && appView && !appView.webContents.isDestroyed()) {
      appView.webContents.reloadIgnoringCache();
    }
    busy = false;
    if (again) { again = false; run(); }
  };

  try {
    fs.watch(root, { recursive: true }, (evt, file) => {
      if (!file || !file.endsWith(".py") || skip.test(file)) return;
      clearTimeout(timer);
      timer = setTimeout(run, 300);
    });
  } catch (e) {
    console.warn("[dev] backend watcher unavailable:", e.message);
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
    if (appView) appView.setBounds(r);
    if (loadingView) loadingView.setBounds(r);
  };
  fit();
  win.on("resize", fit);

  loadingView.webContents.loadFile(path.join(__dirname, "loading.html"));

  backendPort = await freePort();
  spawnBackend(backendPort);

    const ok = await waitForBackend(backendPort);
  if (!ok) {
    dialog.showErrorBox("Cosmoscape", "The backend did not start.");
    app.quit();
    return;
  }
  if (!app.isPackaged) watchBackend();

  const base = "http://127.0.0.1:" + backendPort;
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
  const lv = loadingView;
  loadingView = null;
  win.contentView.removeChildView(lv);
  lv.webContents.close();
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
/**
 * MeshPoint terminal tab — shell over concentrator WebSocket.
 * Layout matches New Terminal_MP (status strip, rail, output, input, footer).
 * Status strip values come from /api only (no mock / random data).
 */
class MeshTerminal {
    constructor() {
        this._initialized = false;
        this._history = [];
        this._historyIdx = -1;
        this._pendingId = null;
        this._outputEl = null;
        this._inputEl = null;
        this._connected = false;
        this._advancedMode = false;
        this._ppmHistory = [];
        this._ppmMax = 24;
        this._stripTimer = null;
        this._acItems = [];
        this._acFocusIdx = -1;

        this._promptText = "admin@meshpoint:~$";

        this._quickCmdsBasic = [
            { label: "meshpoint status", cmd: "meshpoint status" },
            { label: "meshpoint logs", cmd: "meshpoint logs" },
            { label: "meshpoint report", cmd: "meshpoint report" },
            { label: "meshcore radio", cmd: "meshpoint meshcore-radio" },
            { label: "service status", cmd: "systemctl status meshpoint --no-pager" },
            { label: "journal tail", cmd: "journalctl -u meshpoint -n 80 --no-pager" },
            { label: "CPU temp", cmd: "vcgencmd measure_temp" },
            { label: "disk usage", cmd: "df -h" },
        ];

        this._quickCmdsMeshtastic = [
            { label: "Recent text packets", cmd: "journalctl -u meshpoint -n 200 --no-pager | grep -i \"text\\|packet\\|meshtastic\"" },
            { label: "Concentrator health", cmd: "journalctl -u meshpoint -n 150 --no-pager | grep -i \"sx1302\\|concentrator\\|lgw\"" },
            { label: "RSSI/SNR tail", cmd: "journalctl -u meshpoint -n 200 --no-pager | grep -i \"rssi\\|snr\"" },
        ];

        this._quickCmdsMeshcore = [
            { label: "MeshCore logs", cmd: "journalctl -u meshpoint -n 200 --no-pager | grep -i meshcore" },
            { label: "USB devices", cmd: "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null" },
            { label: "MeshCore reconnect clues", cmd: "journalctl -u meshpoint -n 250 --no-pager | grep -i \"meshcore\\|handshake\\|reconnect\"" },
        ];

        this._quickCmdsAdvanced = [
            { label: "restart meshpoint", cmd: "sudo systemctl restart meshpoint" },
            { label: "restart watchdog", cmd: "sudo systemctl restart network-watchdog" },
            { label: "re-run setup", cmd: "sudo meshpoint setup" },
            { label: "last boot kernel", cmd: "dmesg | tail -80" },
            { label: "reset concentrator", cmd: "sudo bash /opt/meshpoint/scripts/reset_concentrator.sh" },
        ];
    }

    _apiBase() {
        const host = location.hostname || "localhost";
        const port = location.port || "8080";
        return `${location.protocol}//${host}:${port}/api`;
    }

    init() {
        if (this._initialized) return;
        this._initialized = true;

        const panel = document.getElementById("terminal-panel");
        if (!panel) return;
        panel.innerHTML = this._buildHTML();

        this._outputEl = panel.querySelector(".terminal__output");
        this._inputEl = panel.querySelector(".terminal__input");
        this._acListEl = panel.querySelector(".terminal__autocomplete-list");
        this._sparkEl = panel.querySelector(".terminal__ppm-sparkline");
        this._footerReady = panel.querySelector(".terminal__footer-ready");
        this._advancedToggle = panel.querySelector(".terminal__footer-advanced input");

        panel.querySelector(".terminal__strip-btn--clear").addEventListener("click", () => this._clearOutput());

        this._inputEl.addEventListener("keydown", (e) => this._onInputKeydown(e));
        this._inputEl.addEventListener("input", () => this._onInputChange());

        this._advancedToggle.addEventListener("change", () => {
            this._advancedMode = this._advancedToggle.checked;
            this._applyAdvancedRail(panel);
            this._printInfo(this._advancedMode ? "Advanced commands shown in rail." : "Advanced commands hidden.");
            this._printBlank();
        });

        this._buildCmdRail(panel);
        this._setupWebSocket();
        this._refreshStatusStrip();
        this._stripTimer = setInterval(() => this._refreshStatusStrip(), 15000);

        this._printInfo("Meshpoint shell ready. Pick a command from the rail or type a shell command.");
        this._printInfo("WebSocket must be connected to run commands on the device.");
        this._printBlank();
    }

    onActivated() {
        if (!this._initialized) this.init();
        this._inputEl?.focus();
        this._refreshStatusStrip();
    }

    _buildHTML() {
        return `
<div class="terminal">
  <div class="terminal__status-strip">
    <div class="terminal__status-strip-item">
      <div class="terminal__status-lamp terminal__status-lamp--warn" id="term-lamp-sx" aria-hidden="true"></div>
      <span class="terminal__status-label">SX1302</span>
      <span class="terminal__status-value" id="term-val-sx">—</span>
    </div>
    <div class="terminal__status-strip-item">
      <div class="terminal__status-lamp terminal__status-lamp--warn" id="term-lamp-mc" aria-hidden="true"></div>
      <span class="terminal__status-label">MeshCore USB</span>
      <span class="terminal__status-value" id="term-val-mc">—</span>
    </div>
    <div class="terminal__status-strip-item">
      <span class="terminal__status-label">RX</span>
      <span class="terminal__status-value terminal__status-value--cyan" id="term-strip-rx">—</span>
    </div>
    <div class="terminal__status-strip-item">
      <span class="terminal__status-label">ERR</span>
      <span class="terminal__status-value" id="term-strip-err">—</span>
    </div>
    <div class="terminal__status-strip-item">
      <span class="terminal__status-label">RF</span>
      <span class="terminal__status-value terminal__status-value--cyan" id="term-strip-rf">—</span>
    </div>
    <div class="terminal__status-strip-spacer"></div>
    <div class="terminal__ppm">
      <span class="terminal__status-label">pkt/min</span>
      <span class="terminal__status-value terminal__status-value--cyan" id="term-strip-ppm">—</span>
      <div class="terminal__ppm-sparkline" id="term-sparkline" aria-hidden="true"></div>
    </div>
    <div class="terminal__status-actions">
      <button type="button" class="terminal__strip-btn terminal__strip-btn--clear">clear</button>
    </div>
  </div>
  <div class="terminal__body">
    <aside class="terminal__rail" aria-label="Quick commands">
      <div class="terminal__rail-header">Commands</div>
      <div class="terminal__rail-list" id="term-cmd-rail"></div>
    </aside>
    <div class="terminal__main">
      <div class="terminal__output terminal-output"></div>
      <div class="terminal__input-wrap">
        <div class="terminal__autocomplete-list" id="term-ac-list"></div>
        <div class="terminal__input-row">
          <span class="terminal__prompt-prefix">${this._promptText}&nbsp;</span>
          <input class="terminal__input" type="text" autocomplete="off" spellcheck="false" placeholder="type a command…" />
        </div>
      </div>
      <div class="terminal__footer">
        <span><span class="terminal__key">↑↓</span> History</span>
        <span><span class="terminal__key">Tab</span> Complete</span>
        <span><span class="terminal__key">Ctrl+L</span> Clear</span>
        <span><span class="terminal__key">Esc</span> Cancel</span>
        <label class="terminal__footer-advanced">
          <input type="checkbox" />
          advanced
        </label>
        <div class="terminal__footer-spacer"></div>
        <div class="terminal__footer-ready terminal__footer-ready--offline" id="term-footer-ready">
          <span class="terminal__footer-ready-dot"></span>
          <span id="term-footer-ready-txt">OFFLINE</span>
        </div>
      </div>
    </div>
  </div>
</div>`;
    }

    _allRailEntries() {
        const out = [];
        const push = (label, arr, cls) => {
            arr.forEach((q) => out.push({ label: q.label, cmd: q.cmd, cls: cls || "" }));
        };
        push("MeshPoint", this._quickCmdsBasic, "");
        push("Meshtastic", this._quickCmdsMeshtastic, "");
        push("MeshCore", this._quickCmdsMeshcore, "");
        if (this._advancedMode) push("Advanced", this._quickCmdsAdvanced, "terminal__cmd-item--advanced");
        return out;
    }

    _buildCmdRail(panel) {
        const rail = panel.querySelector("#term-cmd-rail");
        if (!rail) return;
        const render = () => {
            rail.innerHTML = "";
            const groups = [
                { title: "MeshPoint", items: this._quickCmdsBasic },
                { title: "Meshtastic", items: this._quickCmdsMeshtastic },
                { title: "MeshCore", items: this._quickCmdsMeshcore },
            ];
            if (this._advancedMode) {
                groups.push({ title: "Advanced", items: this._quickCmdsAdvanced });
            }
            groups.forEach((g) => {
                const h = document.createElement("div");
                h.className = "terminal__rail-subhdr";
                h.textContent = g.title;
                rail.appendChild(h);
                g.items.forEach((q) => {
                    const el = document.createElement("div");
                    el.className = "terminal__cmd-item";
                    el.innerHTML = `<span class="terminal__cmd-sigil">&gt;</span><span>${this._esc(q.label)}</span>`;
                    el.title = q.cmd;
                    el.addEventListener("click", () => {
                        rail.querySelectorAll(".terminal__cmd-item").forEach((n) => n.classList.remove("terminal__cmd-item--active"));
                        el.classList.add("terminal__cmd-item--active");
                        this._inputEl.value = q.cmd;
                        this._inputEl.focus();
                        this._closeAutocomplete();
                        setTimeout(() => el.classList.remove("terminal__cmd-item--active"), 500);
                    });
                    rail.appendChild(el);
                });
            });
        };
        render();
        this._renderRail = render;
    }

    _applyAdvancedRail(panel) {
        if (typeof this._renderRail === "function") this._renderRail();
    }

    _setLamp(el, state) {
        if (!el) return;
        el.classList.remove("terminal__status-lamp--ok", "terminal__status-lamp--warn", "terminal__status-lamp--err");
        el.classList.add(`terminal__status-lamp--${state}`);
    }

    async _refreshStatusStrip() {
        const base = this._apiBase();
        let traffic = null;
        let status = null;
        let metrics = null;
        try {
            const [r0, r1, r2] = await Promise.all([
                fetch(`${base}/analytics/traffic`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
                fetch(`${base}/device/status`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
                fetch(`${base}/device/metrics`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
            ]);
            traffic = r0;
            status = r1;
            metrics = r2;
        } catch {
            /* leave dashes */
        }

        const sxEl = document.getElementById("term-val-sx");
        const mcEl = document.getElementById("term-val-mc");
        const rxEl = document.getElementById("term-strip-rx");
        const errEl = document.getElementById("term-strip-err");
        const rfEl = document.getElementById("term-strip-rf");
        const ppmEl = document.getElementById("term-strip-ppm");
        const lampSx = document.getElementById("term-lamp-sx");
        const lampMc = document.getElementById("term-lamp-mc");

        const sourcesRaw = status?.sources ?? metrics?.sources ?? [];
        const sources = (Array.isArray(sourcesRaw) ? sourcesRaw : [sourcesRaw])
            .flat()
            .map((s) => String(s).toLowerCase());

        const sxOn = sources.some((s) =>
            s.includes("concentrator") || s.includes("sx1302") || s.includes("lgw") || s === "rf" || s.includes("lora"));
        const mcOn = sources.some((s) => s.includes("meshcore") || s.includes("ttyusb") || s.includes("ttyacm") || s.includes("companion"));

        if (sources.length) {
            this._setLamp(lampSx, sxOn ? "ok" : "warn");
            if (sxEl) sxEl.textContent = sxOn ? "ONLINE" : "OFFLINE";
            this._setLamp(lampMc, mcOn ? "ok" : "warn");
            if (mcEl) mcEl.textContent = mcOn ? "ONLINE" : "OFFLINE";
        } else {
            this._setLamp(lampSx, "warn");
            if (sxEl) sxEl.textContent = "—";
            this._setLamp(lampMc, "warn");
            if (mcEl) mcEl.textContent = "—";
        }

        const rate = traffic?.packets_per_minute ?? traffic?.rate_per_min ?? null;
        if (ppmEl) {
            ppmEl.textContent = rate != null && Number.isFinite(Number(rate)) ? String(Number(rate).toFixed(1)) : "—";
        }
        if (rate != null && Number.isFinite(Number(rate))) {
            this._ppmHistory.push(Number(rate));
            if (this._ppmHistory.length > this._ppmMax) this._ppmHistory.shift();
        }
        this._renderSparkline();

        const region = status?.region ?? metrics?.region ?? "";
        const mhz = status?.frequency_mhz ?? metrics?.frequency_mhz ?? null;
        if (rfEl) {
            if (mhz != null && String(region)) rfEl.textContent = `${region} · ${mhz} MHz`;
            else if (mhz != null) rfEl.textContent = `${mhz} MHz`;
            else if (region) rfEl.textContent = String(region);
            else rfEl.textContent = "—";
        }

        const totalRx =
            traffic?.total_packets ??
            traffic?.packets_total ??
            traffic?.rx_total ??
            null;
        if (rxEl) {
            if (totalRx != null && Number.isFinite(Number(totalRx))) rxEl.textContent = `${Number(totalRx).toLocaleString()} packets`;
            else rxEl.textContent = "—";
        }
        if (errEl) errEl.textContent = "—";
    }

    _renderSparkline() {
        if (!this._sparkEl) return;
        this._sparkEl.innerHTML = "";
        if (!this._ppmHistory.length) return;
        const max = Math.max(...this._ppmHistory, 1e-6);
        this._ppmHistory.forEach((v) => {
            const b = document.createElement("div");
            b.className = "terminal__ppm-bar";
            b.style.height = `${Math.max(2, Math.round((v / max) * 14))}px`;
            this._sparkEl.appendChild(b);
        });
    }

    _updateFooterReady() {
        if (!this._footerReady) return;
        const txt = document.getElementById("term-footer-ready-txt");
        if (this._connected) {
            this._footerReady.classList.remove("terminal__footer-ready--offline");
            if (txt) txt.textContent = "READY";
        } else {
            this._footerReady.classList.add("terminal__footer-ready--offline");
            if (txt) txt.textContent = "OFFLINE";
        }
    }

    _setupWebSocket() {
        window.concentratorWS.on("connected", () => {
            this._connected = true;
            this._updateFooterReady();
        });
        window.concentratorWS.on("disconnected", () => {
            this._connected = false;
            this._updateFooterReady();
            this._setInputBusy(false);
        });
        window.concentratorWS.on("shell_output", (data) => {
            if (!data) return;
            const { stream, text, exit_code } = data;
            if (text != null) {
                String(text).split("\n").forEach((line, idx, arr) => {
                    if (idx === arr.length - 1 && line === "") return;
                    if (stream === "stderr") this._printError(line);
                    else this._printStdout(line);
                });
            }
            if (exit_code != null) {
                this._printExitCode(exit_code, exit_code === 0);
                this._printSeparator();
                this._setInputBusy(false);
                this._pendingId = null;
            }
        });
        this._updateFooterReady();
    }

    _onInputKeydown(e) {
        if (e.key === "Enter") {
            e.preventDefault();
            this._closeAutocomplete();
            this._submit();
            return;
        }
        if (e.key === "ArrowUp") {
            e.preventDefault();
            this._closeAutocomplete();
            this._historyPrev();
            return;
        }
        if (e.key === "ArrowDown") {
            e.preventDefault();
            this._closeAutocomplete();
            this._historyNext();
            return;
        }
        if (e.key === "Tab") {
            e.preventDefault();
            this._autocompleteTab();
            return;
        }
        if (e.key === "Escape") {
            this._closeAutocomplete();
            this._inputEl.value = "";
            this._historyIdx = -1;
            return;
        }
        if (e.ctrlKey && e.key === "l") {
            e.preventDefault();
            this._clearOutput();
        }
    }

    _onInputChange() {
        this._historyIdx = -1;
        this._openAutocomplete(this._inputEl.value);
    }

    _commandPrefixes() {
        const set = new Set();
        this._allRailEntries().forEach((e) => {
            const first = String(e.cmd).trim().split(/\s+/)[0];
            if (first) set.add(first);
        });
        return Array.from(set).sort();
    }

    _openAutocomplete(partial) {
        const prefix = partial.trim();
        if (!prefix || !this._acListEl) {
            this._closeAutocomplete();
            return;
        }
        const lower = prefix.toLowerCase();
        this._acItems = this._commandPrefixes().filter((c) => c.toLowerCase().startsWith(lower) && c.length > lower.length);
        if (!this._acItems.length) {
            const exact = this._commandPrefixes().filter((c) => c.toLowerCase() === lower);
            if (exact.length) {
                this._closeAutocomplete();
                return;
            }
        }
        if (!this._acItems.length) {
            this._closeAutocomplete();
            return;
        }
        this._acFocusIdx = -1;
        this._renderAutocomplete();
        this._acListEl.classList.add("terminal__autocomplete-list--open");
    }

    _renderAutocomplete() {
        if (!this._acListEl) return;
        this._acListEl.innerHTML = "";
        this._acItems.forEach((name, i) => {
            const el = document.createElement("div");
            el.className = "terminal__autocomplete-item" + (i === this._acFocusIdx ? " terminal__autocomplete-item--focused" : "");
            el.innerHTML = `<span style="color:var(--accent-cyan);font-weight:600">${this._esc(name)}</span><span class="terminal__autocomplete-hint">command</span>`;
            el.addEventListener("mousedown", (ev) => {
                ev.preventDefault();
                this._inputEl.value = `${name} `;
                this._closeAutocomplete();
                this._inputEl.focus();
            });
            this._acListEl.appendChild(el);
        });
    }

    _closeAutocomplete() {
        this._acItems = [];
        this._acFocusIdx = -1;
        if (this._acListEl) {
            this._acListEl.innerHTML = "";
            this._acListEl.classList.remove("terminal__autocomplete-list--open");
        }
    }

    _autocompleteTab() {
        if (!this._acItems.length) {
            this._openAutocomplete(this._inputEl.value);
            return;
        }
        this._acFocusIdx = (this._acFocusIdx + 1) % this._acItems.length;
        const pick = this._acItems[this._acFocusIdx];
        this._inputEl.value = `${pick} `;
        this._renderAutocomplete();
    }

    _submit() {
        const raw = this._inputEl.value.trim();
        if (!raw) return;
        if (!this._connected) {
            this._printWarn("Not connected to device WebSocket.");
            this._printBlank();
            return;
        }

        this._printCmd(raw);
        this._printBlank();
        this._history.unshift(raw);
        if (this._history.length > 100) this._history.pop();
        this._historyIdx = -1;
        this._pendingId = `cmd_${Date.now()}`;
        this._setInputBusy(true);

        try {
            window.concentratorWS.socket.send(JSON.stringify({
                type: "shell_command",
                data: { command: raw, command_id: this._pendingId },
            }));
        } catch (err) {
            this._printError(`Failed to send: ${err.message}`);
            this._setInputBusy(false);
        }
        this._inputEl.value = "";
        this._closeAutocomplete();
    }

    _setInputBusy(busy) {
        this._inputEl.disabled = busy;
    }

    _historyPrev() {
        if (!this._history.length) return;
        this._historyIdx = Math.min(this._historyIdx + 1, this._history.length - 1);
        this._inputEl.value = this._history[this._historyIdx] || "";
    }

    _historyNext() {
        this._historyIdx = Math.max(this._historyIdx - 1, -1);
        this._inputEl.value = this._historyIdx >= 0 ? (this._history[this._historyIdx] || "") : "";
    }

    _printCmd(cmd) {
        const el = document.createElement("div");
        el.className = "terminal__line terminal__line--prompt";
        el.innerHTML = `<span class="terminal__line-prompt">${this._esc(this._promptText)}</span><span class="terminal__line-cmd"> ${this._esc(cmd)}</span>`;
        this._outputEl.appendChild(el);
        this._scrollBottom();
    }

    _printStdout(text) {
        this._line("info", this._esc(text));
    }

    _printError(text) {
        this._line("error", this._esc(text));
    }

    _printInfo(text) {
        this._line("muted", this._esc(text));
    }

    _printWarn(text) {
        this._line("warn", this._esc(text));
    }

    _printBlank() {
        const el = document.createElement("div");
        el.className = "terminal__line terminal__line--blank";
        el.innerHTML = '<span class="terminal__line-text">&nbsp;</span>';
        this._outputEl.appendChild(el);
        this._scrollBottom();
    }

    _line(type, html) {
        const el = document.createElement("div");
        el.className = `terminal__line terminal__line--${type}`;
        el.innerHTML = `<span class="terminal__line-text">${html}</span>`;
        this._outputEl.appendChild(el);
        this._scrollBottom();
    }

    _printExitCode(code, ok) {
        const span = document.createElement("span");
        span.className = `terminal__badge ${ok ? "terminal__badge--green" : "terminal__badge--red"}`;
        span.textContent = ok ? `exit ${code}` : `exit ${code}`;
        const el = document.createElement("div");
        el.className = "terminal__line terminal__line--muted";
        el.appendChild(span);
        this._outputEl.appendChild(el);
        this._scrollBottom();
    }

    _printSeparator() {
        const hr = document.createElement("hr");
        hr.className = "terminal__boot-sep";
        this._outputEl.appendChild(hr);
        this._scrollBottom();
    }

    _clearOutput() {
        this._outputEl.innerHTML = "";
        this._printInfo("Output cleared.");
        this._printBlank();
    }

    _scrollBottom() {
        this._outputEl.scrollTop = this._outputEl.scrollHeight;
    }

    _esc(str) {
        const el = document.createElement("span");
        el.textContent = str ?? "";
        return el.innerHTML;
    }
}

window.meshTerminal = new MeshTerminal();

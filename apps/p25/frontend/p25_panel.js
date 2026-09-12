/** Optional P25 controls. Receiver is started only by an explicit admin action. */
class P25Panel {
    mount(root) {
        this.root = root;
        this.loaded = false;
        root.innerHTML = `<section class="lsn-section"><div class="panel">
            <div class="panel__header">P25 digital radio <span data-state>Stopped</span></div>
            <div class="lsn-panel-body"><p>Follow one local P25 system with OP25. Phase I/II voice, trunk tracking and unencrypted audio. Enter your local channels; no regional frequencies are assumed.</p>
            <form data-form><fieldset class="cfg-fieldset" data-fields><legend>Receiver setup</legend><div class="lsn-controls">
            <label class="lsn-field">System name<input name="name" maxlength="80" value="Local P25 system" required></label>
            <label class="lsn-field">Reception<select name="mode"><option value="trunked">Trunked system</option><option value="conventional">Single conventional channel</option></select></label>
            <label class="lsn-field">Control channels / conventional frequency (MHz)<input name="frequencies" required placeholder="Comma-separated local frequencies"></label>
            <label class="lsn-field">Talkgroups to follow<input name="talkgroups" placeholder="Comma-separated IDs; blank follows all"></label>
            <label class="lsn-field">NAC (decimal, 0 discovers)<input name="nac" type="number" min="0" max="4095" value="0"></label>
            <label class="lsn-field">Modulation<select name="modulation"><option value="cqpsk">CQPSK / simulcast</option><option value="fsk4">C4FM / FSK4</option></select></label>
            <label class="lsn-field">Gain (dB)<input name="gain" type="number" min="0" max="50" value="30"></label>
            <label class="lsn-field">Correction (PPM)<input name="ppm" type="number" min="-200" max="200" value="0"></label>
            <label class="lsn-field">RTL-SDR device index<input name="device" type="number" min="0" max="15" value="0"></label>
            <label><input name="phase2" type="checkbox" checked> Decode Phase II voice</label>
            <label><input name="tdma_control" type="checkbox"> TDMA control channel</label>
            </div><p>For a conventional channel, clear talkgroups and TDMA control. Stop before editing settings. Your last successful setup is remembered in this browser.</p></fieldset>
            <div class="lsn-controls"><button class="terminal-button" type="submit" data-start>Start P25</button><button class="terminal-button" type="button" data-stop>Stop receiver</button><button class="terminal-button" type="button" data-play>Play audio</button></div></form>
            <p role="status" data-message></p><audio controls preload="none" data-audio></audio>
            <p data-audio-state>No decoded audio yet. A running process does not confirm reception.</p>
            <details><summary>Receiver diagnostics</summary><pre data-log style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:260px;overflow:auto"></pre></details>
            </div></div></section>`;
        this.form = root.querySelector('[data-form]');
        this.audio = root.querySelector('[data-audio]');
        try { this.fill(JSON.parse(localStorage.getItem('meshpoint.p25.setup') || 'null')); } catch (_) {}
        this.form.addEventListener('submit', async event => {
            event.preventDefault();
            try {
                const settings = this.read();
                await this.request('/start', settings);
                try { localStorage.setItem('meshpoint.p25.setup', JSON.stringify(settings)); } catch (_) {}
                this.message('Receiver started. Press Play audio to listen.');
                await this.refresh();
            } catch (error) { this.message(error.message); }
        });
        root.querySelector('[data-stop]').addEventListener('click', async () => {
            try { await this.request('/stop', {}); this.stopAudio(); await this.refresh(); this.message('Receiver stopped.'); }
            catch (error) { this.message(error.message); }
        });
        root.querySelector('[data-play]').addEventListener('click', async () => {
            this.audio.src = '/api/p25/stream';
            try { await this.audio.play(); } catch (_) { this.message('Start the receiver, then use the audio player to listen.'); }
        });
    }
    message(value) { this.root.querySelector('[data-message]').textContent = value; }
    fill(settings) {
        if (!settings) return;
        for (const [name, value] of Object.entries(settings)) {
            const field = this.form.elements.namedItem(name);
            if (!field) continue;
            if (field.type === 'checkbox') field.checked = !!value;
            else field.value = Array.isArray(value) ? value.join(', ') : value;
        }
    }
    read() {
        const fields = this.form.elements;
        const list = name => {
            const value = fields.namedItem(name).value.trim();
            if (!value && name === 'talkgroups') return [];
            const parts = value.split(',').map(v => v.trim());
            if (parts.some(v => !v || !Number.isFinite(Number(v)))) throw new Error('Enter numeric frequencies and talkgroups separated by commas.');
            return parts.map(Number);
        };
        return {name:fields.name.value, mode:fields.mode.value, frequencies:list('frequencies'), talkgroups:list('talkgroups'),
            nac:Number(fields.nac.value), modulation:fields.modulation.value, gain:Number(fields.gain.value), ppm:Number(fields.ppm.value),
            device:Number(fields.device.value), phase2:fields.phase2.checked, tdma_control:fields.tdma_control.checked};
    }
    async request(path, body) {
        const response = await fetch('/api/p25'+path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the receiver settings and try again.');
        return data;
    }
    async refresh() {
        try {
            const status = await this.request('/status');
            if (!this.loaded && status.settings) this.fill(status.settings);
            this.loaded = true;
            this.root.querySelector('[data-state]').textContent = status.running ? 'Receiver running' : 'Stopped';
            this.root.querySelector('[data-fields]').disabled = status.running;
            this.root.querySelector('[data-start]').disabled = status.running || (status.dongle_owner && status.dongle_owner !== 'p25');
            this.root.querySelector('[data-play]').disabled = !status.running;
            this.root.querySelector('[data-log]').textContent = status.logs.join('\n');
            this.root.querySelector('[data-audio-state]').textContent = status.audio_bytes ? `${status.audio_bytes} encoded audio bytes received` : 'No decoded audio yet. A running process does not confirm reception.';
            if (status.last_error) this.message(status.last_error);
            if (!status.running) this.stopAudio();
        } catch (error) { this.message(error.message); }
    }
    stopAudio() { this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); }
    show() { this.refresh(); this.timer = setInterval(() => this.refresh(), 2000); }
    hide() { clearInterval(this.timer); this.stopAudio(); }
}
window.registerPageHook({host:'rtlsdr', label:'P25', make:() => new P25Panel()});

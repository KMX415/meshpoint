/**
 * Optional UI sound design. Off by default.
 *
 * Generates short, soft synthesised tones via WebAudio for a small
 * vocabulary of UI events. No external assets — keeps the sound
 * footprint zero bytes when disabled.
 *
 * Single responsibility: synthesise + emit. Toggle state lives in
 * localStorage; settings UI flips the flag and other modules call
 * window.soundEngine.play(name).
 *
 * Supported events: 'connect', 'disconnect', 'error', 'success'.
 */
class SoundEngine {
    constructor(storageKey = 'meshpoint:sound:enabled:v1') {
        this._key = storageKey;
        this._ctx = null;
        this._enabled = this._readEnabled();
    }

    isEnabled() { return this._enabled; }

    setEnabled(enabled) {
        this._enabled = !!enabled;
        try { localStorage.setItem(this._key, this._enabled ? '1' : '0'); } catch (_e) {}
        if (this._enabled) {
            // Probe sound so the operator knows it worked.
            this.play('success');
        }
    }

    play(name) {
        if (!this._enabled) return;
        const ctx = this._getContext();
        if (!ctx) return;
        const recipe = SoundEngine._recipes[name] || SoundEngine._recipes.success;
        SoundEngine._render(ctx, recipe);
    }

    _readEnabled() {
        try {
            return localStorage.getItem(this._key) === '1';
        } catch (_e) { return false; }
    }

    _getContext() {
        try {
            if (!this._ctx) {
                const Ctor = window.AudioContext || window.webkitAudioContext;
                if (!Ctor) return null;
                this._ctx = new Ctor();
            }
            if (this._ctx.state === 'suspended') this._ctx.resume();
            return this._ctx;
        } catch (_e) { return null; }
    }

    static _render(ctx, recipe) {
        const now = ctx.currentTime;
        recipe.notes.forEach((note, idx) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = note.type || 'sine';
            osc.frequency.value = note.freq;
            const start = now + idx * (recipe.interval ?? 0.05);
            const end = start + (note.duration ?? 0.12);
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(note.gain ?? 0.05, start + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.0001, end);
            osc.connect(gain).connect(ctx.destination);
            osc.start(start);
            osc.stop(end + 0.02);
        });
    }
}

SoundEngine._recipes = {
    connect: {
        interval: 0.05,
        notes: [
            { freq: 660, duration: 0.08, gain: 0.04 },
            { freq: 880, duration: 0.12, gain: 0.05 },
        ],
    },
    disconnect: {
        interval: 0.06,
        notes: [
            { freq: 520, duration: 0.1, gain: 0.04 },
            { freq: 360, duration: 0.16, gain: 0.05 },
        ],
    },
    error: {
        interval: 0.05,
        notes: [
            { freq: 220, type: 'square', duration: 0.08, gain: 0.05 },
            { freq: 200, type: 'square', duration: 0.16, gain: 0.05 },
        ],
    },
    success: {
        interval: 0.04,
        notes: [
            { freq: 740, duration: 0.06, gain: 0.04 },
            { freq: 988, duration: 0.1, gain: 0.05 },
        ],
    },
};

window.SoundEngine = SoundEngine;
window.soundEngine = new SoundEngine();

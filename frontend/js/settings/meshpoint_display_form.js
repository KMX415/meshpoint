/**
 * Settings → Meshpoint: display unit preferences (local browser only).
 */

class MeshpointDisplayForm {
    constructor(rootEl) {
        this.root = rootEl;
        this._statusEl = rootEl.querySelector('[data-display-units-status]');
        this._tempInputs = Array.from(rootEl.querySelectorAll('[data-display-temp]'));
        this._distInputs = Array.from(rootEl.querySelectorAll('[data-display-distance]'));
        this._bind();
        this._syncFromStorage();
    }

    _bind() {
        const onChange = () => this._save();
        this._tempInputs.forEach((el) => el.addEventListener('change', onChange));
        this._distInputs.forEach((el) => el.addEventListener('change', onChange));
    }

    _syncFromStorage() {
        const prefs = window.MeshpointDisplayUnits.getPrefs();
        this._tempInputs.forEach((el) => {
            el.checked = el.value === prefs.temperature;
        });
        this._distInputs.forEach((el) => {
            el.checked = el.value === prefs.distance;
        });
    }

    _save() {
        const temp = this._tempInputs.find((el) => el.checked);
        const dist = this._distInputs.find((el) => el.checked);
        window.MeshpointDisplayUnits.savePrefs({
            temperature: temp ? temp.value : 'fahrenheit',
            distance: dist ? dist.value : 'imperial',
        });
        this._setStatus('success', 'Saved. Node cards and details will use these units.');
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.MeshpointDisplayForm = MeshpointDisplayForm;

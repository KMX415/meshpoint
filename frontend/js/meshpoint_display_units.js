/**
 * Browser-local display unit preferences for the Meshpoint dashboard.
 *
 * Meshtastic telemetry stores temperature in Celsius and altitude in meters.
 * This module converts at display time only; edge storage is unchanged.
 */

const STORAGE_KEY = 'meshpoint.displayUnits';
const CHANGE_EVENT = 'meshpoint:display-units';

const DEFAULTS = {
    temperature: 'fahrenheit',
    distance: 'imperial',
};

function _load() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return { ...DEFAULTS };
        const parsed = JSON.parse(raw);
        return {
            temperature: parsed.temperature === 'celsius' ? 'celsius' : 'fahrenheit',
            distance: parsed.distance === 'metric' ? 'metric' : 'imperial',
        };
    } catch (_e) {
        return { ...DEFAULTS };
    }
}

let _prefs = _load();

class MeshpointDisplayUnits {
    static getPrefs() {
        return { ..._prefs };
    }

    static savePrefs(next) {
        _prefs = {
            temperature: next.temperature === 'celsius' ? 'celsius' : 'fahrenheit',
            distance: next.distance === 'metric' ? 'metric' : 'imperial',
        };
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(_prefs));
        } catch (_e) {
            /* private mode / quota */
        }
        window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { ..._prefs } }));
    }

    static onChange(handler) {
        window.addEventListener(CHANGE_EVENT, handler);
        return () => window.removeEventListener(CHANGE_EVENT, handler);
    }

    /** @param {number|null|undefined} celsius */
    static formatTemperature(celsius) {
        if (celsius == null || Number.isNaN(Number(celsius))) return null;
        const c = Number(celsius);
        if (_prefs.temperature === 'celsius') {
            return `${c.toFixed(1)}\u00B0C`;
        }
        return `${(c * 9 / 5 + 32).toFixed(1)}\u00B0F`;
    }

    /** @param {number|null|undefined} meters */
    static formatAltitude(meters) {
        if (meters == null || Number.isNaN(Number(meters))) return null;
        const m = Number(meters);
        if (_prefs.distance === 'metric') {
            return `${Math.round(m)} m`;
        }
        return `${Math.round(m * 3.28084)} ft`;
    }

    /** @param {number|null|undefined} km */
    static formatDistanceKm(km) {
        if (km == null || Number.isNaN(Number(km))) return null;
        const k = Number(km);
        if (_prefs.distance === 'metric') {
            return k < 1 ? `${Math.round(k * 1000)} m` : `${k.toFixed(k < 10 ? 1 : 0)} km`;
        }
        const mi = k * 0.621371;
        if (mi < 0.1) return `${Math.round(k * 1000 * 3.28084)} ft`;
        return `${mi.toFixed(mi < 10 ? 1 : 0)} mi`;
    }

    /** Temperature in Celsius for dew-point math. */
    static temperatureCelsiusForCalc(displayedOrStoredC) {
        return Number(displayedOrStoredC);
    }

    static temperatureUnitLabel() {
        return _prefs.temperature === 'celsius' ? 'C' : 'F';
    }

    /** Grid step for approximate location privacy (2-decimal lat/lon). */
    static get APPROXIMATE_LOCATION_PRIVACY_KM() {
        return 1.1;
    }

    /** Select option label for approximate MQTT/mesh location privacy. */
    static approximateLocationOptionLabel() {
        const dist = MeshpointDisplayUnits.formatDistanceKm(
            MeshpointDisplayUnits.APPROXIMATE_LOCATION_PRIVACY_KM,
        );
        return dist ? `Approximate (~${dist})` : 'Approximate (reduced precision)';
    }
}

window.MeshpointDisplayUnits = MeshpointDisplayUnits;

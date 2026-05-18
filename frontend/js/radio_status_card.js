/**
 * Radio tab — TX Status card.
 *
 * Renders an industrial duty-cycle gauge (SVG arc + tick marks) plus
 * a status lamp (READY / WARN / DISABLED) and a TX enable toggle.
 * Owned by the radio orchestrator (radio_settings.js); exposed as
 * window.RadioStatusCard so script-tag loading works without a
 * bundler.
 */
class _DutyGauge {
    constructor(rootEl) {
        this._root = rootEl;
        this._arc = rootEl.querySelector('.duty-gauge__arc-fill');
        this._ticks = rootEl.querySelector('.duty-gauge__ticks');
        this._valueEl = rootEl.querySelector('.duty-gauge__value');
        this._capEl = rootEl.querySelector('.duty-gauge__cap');
        this._cx = 100;
        this._cy = 110;
        this._r = 70;
        this._renderTicks();
    }

    render(usedPercent, capPercent) {
        const used = Number.isFinite(usedPercent) ? usedPercent : 0;
        const cap = Number.isFinite(capPercent) && capPercent > 0
            ? capPercent
            : 100;
        const fillFraction = Math.min(used / cap, 1);
        const endpoint = this._pointAt(this._r, fillFraction);
        this._arc.setAttribute(
            'd',
            `M 30 110 A ${this._r} ${this._r} 0 0 1 `
            + `${endpoint.x.toFixed(2)} ${endpoint.y.toFixed(2)}`,
        );

        this._arc.classList.remove(
            'duty-gauge__arc-fill--mid',
            'duty-gauge__arc-fill--high',
        );
        if (fillFraction >= 0.8) {
            this._arc.classList.add('duty-gauge__arc-fill--high');
        } else if (fillFraction >= 0.5) {
            this._arc.classList.add('duty-gauge__arc-fill--mid');
        }

        this._valueEl.innerHTML = `${used.toFixed(1)}<span>%</span>`;
        this._capEl.textContent = `of ${cap.toFixed(1)}% allotted`;
    }

    _renderTicks() {
        this._ticks.innerHTML = '';
        for (let i = 0; i <= 10; i++) {
            const t = i / 10;
            const isMajor = (i % 5 === 0);
            const outerR = isMajor ? 80 : 78;
            const innerR = isMajor ? 67 : 70;
            const outer = this._pointAt(outerR, t);
            const inner = this._pointAt(innerR, t);
            const line = document.createElementNS(
                'http://www.w3.org/2000/svg', 'line',
            );
            line.setAttribute('x1', outer.x.toFixed(2));
            line.setAttribute('y1', outer.y.toFixed(2));
            line.setAttribute('x2', inner.x.toFixed(2));
            line.setAttribute('y2', inner.y.toFixed(2));
            if (isMajor) line.classList.add('tick--major');
            this._ticks.appendChild(line);
        }
    }

    _pointAt(radius, fraction) {
        return {
            x: this._cx - radius * Math.cos(Math.PI * fraction),
            y: this._cy - radius * Math.sin(Math.PI * fraction),
        };
    }
}


class RadioStatusCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._gauge = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card', 'r-card--readout');
        rootEl.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">TX Status</h3>
                <span class="status-lamp" id="r-tx-lamp">
                    <span class="status-lamp__dot"></span>
                    <span class="status-lamp__label">--</span>
                </span>
            </div>
            <div class="duty-gauge">
                <svg class="duty-gauge__svg" viewBox="0 0 200 130"
                     preserveAspectRatio="xMidYMid meet">
                    <path class="duty-gauge__arc-bg"
                          d="M 30 110 A 70 70 0 0 1 170 110"
                          fill="none" stroke-width="14"
                          stroke-linecap="round" />
                    <path class="duty-gauge__arc-fill"
                          d="M 30 110 A 70 70 0 0 1 30 110"
                          fill="none" stroke-width="14"
                          stroke-linecap="round" />
                    <g class="duty-gauge__ticks"></g>
                </svg>
                <div class="duty-gauge__readout">
                    <div class="duty-gauge__value">0.0<span>%</span></div>
                    <div class="duty-gauge__cap">of 0.0% allotted</div>
                </div>
            </div>
            <div class="r-readout-grid">
                <div class="r-readout-row">
                    <span class="r-readout-row__label">TX Enabled</span>
                    <span class="r-readout-row__value" id="r-tx-state">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Duty cap</span>
                    <span class="r-readout-row__value" id="r-tx-cap">--</span>
                </div>
            </div>
            <a class="r-config-link" href="#/configuration/transmit">
                <span>Edit transmit settings</span>
                <span aria-hidden="true">→</span>
            </a>
        `;

        this._gauge = new _DutyGauge(rootEl.querySelector('.duty-gauge'));
    }

    render(config) {
        const tx = config.transmit || {};
        const duty = config.duty_cycle || {};
        const used = duty.used_percent || 0;
        const cap = tx.max_duty_cycle_percent || 1;
        this._gauge.render(used, cap);
        this._renderLamp(tx.enabled, used, cap);
        const stateEl = this._root.querySelector('#r-tx-state');
        const capEl = this._root.querySelector('#r-tx-cap');
        stateEl.textContent = tx.enabled ? 'On' : 'Off';
        stateEl.dataset.state = tx.enabled ? 'on' : 'off';
        capEl.textContent = `${(cap || 0).toFixed(1)}%`;
    }

    _renderLamp(enabled, used, cap) {
        const lamp = this._root.querySelector('#r-tx-lamp');
        const label = lamp.querySelector('.status-lamp__label');
        lamp.classList.remove(
            'status-lamp--ready',
            'status-lamp--warn',
            'status-lamp--off',
        );
        if (!enabled) {
            lamp.classList.add('status-lamp--off');
            label.textContent = 'DISABLED';
            return;
        }
        const fraction = cap > 0 ? used / cap : 0;
        if (fraction >= 0.8) {
            lamp.classList.add('status-lamp--off');
            label.textContent = 'DUTY CAP';
        } else if (fraction >= 0.5) {
            lamp.classList.add('status-lamp--warn');
            label.textContent = 'BUSY';
        } else {
            lamp.classList.add('status-lamp--ready');
            label.textContent = 'READY';
        }
    }

}

window.RadioStatusCard = RadioStatusCard;

/**
 * Chat view renderer for interleaved sent/received messages.
 * Handles the message display area, compose bar, auto-scroll,
 * and lazy-loading of older messages.
 */
class MessagingChat {
    constructor(containerEl, onSend) {
        this._container = containerEl;
        this._onSend = onSend;
        this._conversation = null;
        this._messages = [];
        this._loading = false;
        this._allLoaded = false;
        this._build();
    }

    clearChat() {
        this._conversation = null;
        this._messages = [];
        this._allLoaded = false;
        this._messagesEl.innerHTML = '<div class="msg-chat__empty">Select a conversation</div>';
        this._headerName.textContent = '';
        this._headerBadge.textContent = '';
    }

    setConversation(convo) {
        this._conversation = convo;
        this._messages = [];
        this._allLoaded = false;
        this._headerName.textContent = convo.node_name || convo.node_id;
        this._headerBadge.textContent = convo.protocol === 'meshcore' ? 'MC' : 'MT';
        this._headerBadge.className = 'msg-chat__protocol-badge ' +
            (convo.protocol === 'meshcore' ? 'msg-chat__protocol-badge--mc' : 'msg-chat__protocol-badge--mt');

        this._messagesEl.innerHTML = '';
        this._input.disabled = false;
        this._sendBtn.disabled = false;
        this._input.focus();
        this._loadMessages();
    }

    addMessage(msg) {
        this._messages.push(msg);
        this._appendBubble(msg);
        this._scrollToBottom();
    }

    addOptimisticMessage(text, protocol) {
        const msg = {
            id: Date.now(),
            direction: 'sent',
            text: text,
            node_id: this._conversation?.node_id || '',
            node_name: '',
            protocol: protocol || this._conversation?.protocol || 'meshtastic',
            channel: 0,
            timestamp: new Date().toISOString(),
            status: 'sending...',
            packet_id: '',
        };
        this.addMessage(msg);
        return msg;
    }

    updateMessageStatus(tempId, status, packetId) {
        const bubble = this._messagesEl.querySelector(`[data-msg-id="${tempId}"]`);
        if (bubble) {
            const meta = bubble.querySelector('.msg-bubble__meta');
            if (meta) {
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                meta.textContent = `${time} · ${status}`;
            }
        }
    }

    clear() {
        this._conversation = null;
        this._messages = [];
        this._messagesEl.innerHTML = '';
        this._headerName.textContent = 'Select a conversation';
        this._headerBadge.textContent = '';
        this._headerBadge.className = 'msg-chat__protocol-badge';
        this._input.disabled = true;
        this._sendBtn.disabled = true;
    }

    async _loadMessages() {
        if (!this._conversation || this._loading) return;
        this._loading = true;

        try {
            const nodeId = encodeURIComponent(this._conversation.node_id);
            const res = await fetch(`/api/messages/conversation/${nodeId}?limit=50`);
            const messages = await res.json();
            this._messages = messages;

            this._messagesEl.innerHTML = '';
            if (messages.length === 0) {
                this._messagesEl.innerHTML = '<div class="msg-chat__empty">No messages yet. Say hello!</div>';
            } else {
                messages.forEach(msg => this._appendBubble(msg));
                this._scrollToBottom();
            }

            if (messages.length < 50) this._allLoaded = true;

            await fetch(`/api/messages/conversation/${nodeId}/read`, { method: 'POST' });
        } catch (e) {
            console.error('Failed to load messages:', e);
        } finally {
            this._loading = false;
        }
    }

    _appendBubble(msg) {
        const empty = this._messagesEl.querySelector('.msg-chat__empty');
        if (empty) empty.remove();

        const bubble = document.createElement('div');
        bubble.className = `msg-bubble msg-bubble--${msg.direction}`;
        bubble.dataset.msgId = msg.id;
        if (msg.packet_id) bubble.dataset.pktId = msg.packet_id;

        const time = msg.timestamp
            ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : '';
        const statusText = msg.status && msg.status !== 'delivered' && msg.status !== 'read'
            ? ` · ${msg.status}` : '';

        let senderHtml = '';
        if (msg.direction === 'received' && msg.node_name && !this._conversation?.is_broadcast) {
            senderHtml = '';
        } else if (msg.direction === 'received' && this._conversation?.is_broadcast && msg.node_name) {
            senderHtml = `<div class="msg-bubble__sender">${this._esc(msg.node_name || msg.node_id)}</div>`;
        }

        const signalHtml = this._buildSignalHtml(msg);

        bubble.innerHTML = `
            ${senderHtml}
            <div class="msg-bubble__text">${this._esc(msg.text)}</div>
            <div class="msg-bubble__meta">${time}${statusText}${signalHtml}</div>
        `;

        this._messagesEl.appendChild(bubble);
    }

    _scrollToBottom() {
        requestAnimationFrame(() => {
            this._messagesEl.scrollTop = this._messagesEl.scrollHeight;
        });
    }

    _handleSend() {
        const text = this._input.value.trim();
        if (!text || !this._conversation) return;

        this._input.value = '';
        this._onSend(text, this._conversation);
    }

    _build() {
        this._container.innerHTML = `
            <div class="msg-chat__header">
                <span class="msg-chat__name">Select a conversation</span>
                <span class="msg-chat__protocol-badge"></span>
            </div>
            <div class="msg-chat__messages"></div>
            <div class="msg-compose">
                <input class="msg-compose__input" placeholder="Type a message..." disabled maxlength="228" />
                <button class="msg-compose__send" disabled>Send</button>
            </div>
        `;

        this._headerName = this._container.querySelector('.msg-chat__name');
        this._headerBadge = this._container.querySelector('.msg-chat__protocol-badge');
        this._messagesEl = this._container.querySelector('.msg-chat__messages');
        this._input = this._container.querySelector('.msg-compose__input');
        this._sendBtn = this._container.querySelector('.msg-compose__send');

        this._sendBtn.addEventListener('click', () => this._handleSend());
        this._input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._handleSend();
            }
        });

        this._messagesEl.addEventListener('scroll', () => {
            if (this._messagesEl.scrollTop === 0 && !this._allLoaded) {
                this._loadOlderMessages();
            }
        });
    }

    async _loadOlderMessages() {
        if (!this._conversation || this._loading || this._allLoaded) return;
        if (this._messages.length === 0) return;
        this._loading = true;

        try {
            const oldest = this._messages[0];
            const nodeId = encodeURIComponent(this._conversation.node_id);
            const res = await fetch(
                `/api/messages/conversation/${nodeId}?limit=50&before=${oldest.timestamp}`
            );
            const older = await res.json();
            if (older.length === 0) {
                this._allLoaded = true;
                return;
            }

            const scrollBefore = this._messagesEl.scrollHeight;
            const frag = document.createDocumentFragment();
            older.forEach(msg => {
                const bubble = this._buildBubbleEl(msg);
                frag.appendChild(bubble);
            });
            this._messagesEl.prepend(frag);
            this._messages = [...older, ...this._messages];

            const scrollAfter = this._messagesEl.scrollHeight;
            this._messagesEl.scrollTop = scrollAfter - scrollBefore;
        } catch (e) {
            console.error('Failed to load older messages:', e);
        } finally {
            this._loading = false;
        }
    }

    _buildBubbleEl(msg) {
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble msg-bubble--${msg.direction}`;
        bubble.dataset.msgId = msg.id;
        if (msg.packet_id) bubble.dataset.pktId = msg.packet_id;
        const time = msg.timestamp
            ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : '';
        const signalHtml = this._buildSignalHtml(msg);
        bubble.innerHTML = `
            <div class="msg-bubble__text">${this._esc(msg.text)}</div>
            <div class="msg-bubble__meta">${time}${signalHtml}</div>
        `;
        return bubble;
    }

    updateBubbleSignal(packetId, rssi, snr, rxCount) {
        const bubble = this._messagesEl.querySelector(`[data-pkt-id="${packetId}"]`);
        if (!bubble) return;

        const meta = bubble.querySelector('.msg-bubble__meta');
        if (!meta) return;

        const sig = meta.querySelector('.msg-signal');
        if (sig) sig.remove();
        const rx = meta.querySelector('.msg-rx-count');
        if (rx) rx.remove();

        const fakeMsg = { direction: 'received', rssi, snr, rx_count: rxCount };
        meta.insertAdjacentHTML('beforeend', this._buildSignalHtml(fakeMsg));
    }

    _buildSignalHtml(msg) {
        if (msg.direction === 'sent' || msg.rssi == null) return '';

        const rssi = msg.rssi;
        const snr = msg.snr;
        const level = rssi > -80 ? 5 : rssi > -95 ? 4 : rssi > -110 ? 3 : rssi > -125 ? 2 : 1;
        const cls = level >= 4 ? 'excellent' : level === 3 ? 'good' : level === 2 ? 'fair' : 'poor';

        let bars = '';
        for (let i = 1; i <= 5; i++) {
            const active = i <= level ? 'active' : '';
            bars += `<span class="sig-bar sig-bar--h${i} ${active}"></span>`;
        }

        const snrStr = snr != null ? ` · ${snr.toFixed(1)} dB` : '';
        const rxStr = (msg.rx_count || 1) > 1
            ? `<span class="msg-rx-count" title="Received via ${msg.rx_count} RF paths">×${msg.rx_count}</span>`
            : '';
        return `<span class="msg-signal msg-signal--${cls}">${bars}<span class="msg-signal__val">${rssi.toFixed(1)}${snrStr}</span></span>${rxStr}`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

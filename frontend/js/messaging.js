/**
 * Main messaging panel controller for the local Meshpoint dashboard.
 * Manages the two-column layout (sidebar + chat), tab switching,
 * protocol filtering, monitor mode, WebSocket event routing, and
 * send orchestration.
 */
class MessagingPanel {
    constructor() {
        this._initialized = false;
        this._contacts = null;
        this._chat = null;
        this._activeConvo = null;
        this._monitorMode = false;
        this._txStatus = null;
    }

    init() {
        if (this._initialized) return;
        this._initialized = true;

        const panel = document.getElementById('messaging-panel');
        if (!panel) return;

        panel.innerHTML = `
            <div id="msg-tx-banner" class="msg-tx-banner" style="display:none"></div>
            <div class="messaging">
                <aside class="msg-sidebar">
                    <header class="msg-sidebar__header">
                        <div class="msg-sidebar__title-row">
                            <span class="msg-sidebar__title">Messages</span>
                            <span class="msg-sidebar__subtitle">Channels &amp; direct conversations</span>
                        </div>
                        <div class="msg-sidebar__actions">
                            <button class="msg-icon-btn" id="msg-monitor-btn" type="button" title="Monitor: show overheard DMs" aria-label="Monitor mode">
                                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/>
                                    <circle cx="12" cy="12" r="2.5"/>
                                </svg>
                            </button>
                            <button class="msg-pill-btn msg-pill-btn--accent" id="msg-new-btn" type="button">
                                <span aria-hidden="true">＋</span> New
                            </button>
                        </div>
                    </header>
                    <div class="msg-protocol-toggle" role="tablist" aria-label="Filter conversations by protocol">
                        <button class="msg-protocol-toggle__btn msg-protocol-toggle__btn--active" data-filter="all"        role="tab" aria-selected="true">All</button>
                        <button class="msg-protocol-toggle__btn"                                  data-filter="meshtastic" role="tab" aria-selected="false">MT</button>
                        <button class="msg-protocol-toggle__btn"                                  data-filter="meshcore"   role="tab" aria-selected="false">MC</button>
                    </div>
                    <div class="msg-sidebar__list" id="msg-convo-list"></div>
                </aside>
                <div class="msg-chat msg-chat--empty" id="msg-chat-area"></div>
            </div>
        `;

        const listEl = document.getElementById('msg-convo-list');
        const chatEl = document.getElementById('msg-chat-area');

        this._contacts = new MessagingContacts(listEl, (convo) => this._onConversationSelected(convo));
        this._chat = new MessagingChat(chatEl, (text, convo) => this._onSendMessage(text, convo));

        document.getElementById('msg-new-btn').addEventListener('click', () => {
            this._contacts.openContactPicker();
        });

        document.getElementById('msg-monitor-btn').addEventListener('click', () => {
            this._monitorMode = !this._monitorMode;
            const btn = document.getElementById('msg-monitor-btn');
            btn.classList.toggle('msg-icon-btn--active', this._monitorMode);
            btn.setAttribute('aria-pressed', this._monitorMode ? 'true' : 'false');
            btn.title = this._monitorMode
                ? 'Monitor ON: showing overheard DMs'
                : 'Monitor: show overheard DMs';
            this._contacts.load(this._monitorMode);
        });

        panel.querySelectorAll('.msg-protocol-toggle__btn').forEach(btn => {
            btn.addEventListener('click', () => {
                panel.querySelectorAll('.msg-protocol-toggle__btn').forEach(b => {
                    b.classList.remove('msg-protocol-toggle__btn--active');
                    b.setAttribute('aria-selected', 'false');
                });
                btn.classList.add('msg-protocol-toggle__btn--active');
                btn.setAttribute('aria-selected', 'true');
                this._contacts.setFilter(btn.dataset.filter);
            });
        });

        this._setupWebSocket();
        this._loadInitialConversations();
        this._loadStatus();
    }

    onActivated() {
        if (!this._initialized) this.init();
        this._loadInitialConversations();
    }

    async _loadInitialConversations() {
        await this._contacts.load(this._monitorMode);
        this._syncSidebarBadge();
    }

    openConversation(convo) {
        if (!this._initialized) this.init();
        this._onConversationSelected(convo);
    }

    _onConversationSelected(convo) {
        if (!convo) {
            this._activeConvo = null;
            this._chat.clearChat();
            return;
        }
        this._activeConvo = convo;
        this._chat.setConversation(convo);
        this._contacts.setActive(convo.node_id);

        // Opening a DM means the user has read it: clear server-side
        // status, drop the per-row badge, and recompute the sidebar
        // total. Broadcast/channel conversations skip mark-read by
        // design (see MessagingContacts.markConversationRead).
        Promise.resolve(this._contacts.markConversationRead(convo.node_id))
            .then(() => this._syncSidebarBadge());
    }

    async _onSendMessage(text, convo) {
        const isBroadcast = convo.is_broadcast || (convo.node_id || '').startsWith('broadcast:');
        const destination = isBroadcast ? 'broadcast' : convo.node_id;

        const tempMsg = this._chat.addOptimisticMessage(text, convo.protocol);

        try {
            const res = await fetch('/api/messages/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    destination: destination,
                    protocol: convo.protocol || 'meshtastic',
                    channel: convo.channel || 0,
                }),
            });

            if (!res.ok) {
                const errBody = await res.json().catch(() => ({}));
                const reason = errBody.detail || errBody.error || `HTTP ${res.status}`;
                this._chat.updateMessageStatus(tempMsg.id, `failed: ${reason}`, '');
                return;
            }

            const result = await res.json();
            if (result.success) {
                this._chat.updateMessageStatus(tempMsg.id, 'sent', result.packet_id);
                this._contacts.addOrUpdateConversation({
                    node_id: convo.node_id,
                    node_name: convo.node_name,
                    protocol: convo.protocol,
                    text: text,
                    direction: 'sent',
                    timestamp: new Date().toISOString(),
                });
            } else {
                const reason = result.error || 'unknown error';
                this._chat.updateMessageStatus(tempMsg.id, `failed: ${reason}`, '');
            }
        } catch (e) {
            console.error('Send failed:', e);
            this._chat.updateMessageStatus(tempMsg.id, 'network error', '');
        }
    }

    _setupWebSocket() {
        window.concentratorWS.on('message_received', (data) => {
            const isOverheard = data.direction === 'overheard';

            if (isOverheard && !this._monitorMode) {
                return;
            }

            const isViewingThisConvo =
                this._activeConvo && data.node_id === this._activeConvo.node_id;
            if (isViewingThisConvo) {
                const chParts = (data.node_id || '').split(':');
                const chIdx = chParts.length >= 3 ? parseInt(chParts[2], 10) || 0 : 0;
                const msg = {
                    id: Date.now(),
                    direction: data.direction || 'received',
                    text: data.text,
                    node_id: data.node_id,
                    node_name: data.node_name || '',
                    protocol: data.protocol || 'meshtastic',
                    channel: chIdx,
                    timestamp: new Date().toISOString(),
                    status: 'delivered',
                    packet_id: data.packet_id || '',
                    source_id: data.source_id || '',
                    destination_id: data.destination_id || '',
                };
                if (data.rssi != null) msg.rssi = data.rssi;
                if (data.snr != null) msg.snr = data.snr;
                this._chat.addMessage(msg);

                // Server still has this row marked unread until the
                // explicit mark-read POST fires, so a future page
                // refresh would show a stale badge for a message we
                // already read live in front of the user. Push
                // through here too. addOrUpdateConversation below
                // already skips the local unread bump when the
                // node_id matches the active conversation.
                Promise.resolve(this._contacts.markConversationRead(data.node_id))
                    .then(() => this._syncSidebarBadge());
            }
            this._contacts.addOrUpdateConversation(data);

            // Sidebar Messages badge derives from the per-conversation
            // unread counts that MessagingContacts maintains (seeded
            // from the server's read-state aware
            // /api/messages/conversations response on load, kept fresh
            // by addOrUpdateConversation here). DM-vs-broadcast
            // filtering happens inside getDmUnreadTotal because
            // public/broadcast channels are routinely spammy on real
            // meshes and we want this badge to stay a meaningful "you
            // got a DM" signal, not a public-channel firehose.
            this._syncSidebarBadge();
        });

        window.concentratorWS.on('message_updated', (data) => {
            if (this._activeConvo && data.node_id === this._activeConvo.node_id) {
                this._chat.updateBubbleSignal(
                    data.packet_id, data.rssi, data.snr, data.rx_count
                );
            }
        });

        window.concentratorWS.on('message_sent', (data) => {
            this._contacts.addOrUpdateConversation({
                ...data,
                direction: 'sent',
            });
        });
    }

    async _loadStatus() {
        try {
            const res = await fetch('/api/messages/status');
            const status = await res.json();
            this._txStatus = status;
            this._renderTxBanner(status);
        } catch (e) {
            this._renderTxBanner(null);
        }
    }

    _renderTxBanner(status) {
        const banner = document.getElementById('msg-tx-banner');
        if (!banner) return;

        if (!status) {
            banner.style.display = 'block';
            banner.className = 'msg-tx-banner msg-tx-banner--error';
            banner.innerHTML = 'TX status unavailable';
            return;
        }

        const mt = status.meshtastic || {};
        const mc = status.meshcore || {};

        if (!mt.enabled && !mc.connected) {
            banner.style.display = 'block';
            banner.className = 'msg-tx-banner msg-tx-banner--warn';
            banner.innerHTML = 'TX not configured. <a href="#" onclick="document.querySelector(\'[data-tab=radio]\').click();return false">Open Radio tab</a> to enable.';
            return;
        }

        if (mt.enabled && !mt.node_id) {
            banner.style.display = 'block';
            banner.className = 'msg-tx-banner msg-tx-banner--warn';
            banner.innerHTML = 'Node ID not set. <a href="#" onclick="document.querySelector(\'[data-tab=radio]\').click();return false">Set in Radio tab</a>.';
            return;
        }

        banner.style.display = 'none';
    }

    /**
     * Single source of truth for the sidebar Messages badge.
     * Recomputes from MessagingContacts._conversations[].unread_count
     * (DM-only, see getDmUnreadTotal). Call after any state change
     * that could have moved the total: initial load, live message
     * received, conversation marked read.
     */
    _syncSidebarBadge() {
        const badge = document.getElementById('msg-unread-badge');
        if (!badge) return;
        const total = this._contacts ? this._contacts.getDmUnreadTotal() : 0;
        if (total > 0) {
            badge.textContent = String(total);
            badge.style.display = 'inline-block';
        } else {
            badge.textContent = '';
            badge.style.display = 'none';
        }
    }

    /**
     * Backwards-compat shim for the sidebar controller, which calls
     * this when the user navigates to the Messages route. With the
     * server-driven unread model the badge no longer needs to be
     * force-cleared on tab activation: clearing only happens when a
     * specific conversation is opened. Just resync from current
     * state so a stale badge from before the user clicked away gets
     * recomputed.
     */
    resetUnreadBadge() {
        this._syncSidebarBadge();
    }
}

window.messagingPanel = new MessagingPanel();

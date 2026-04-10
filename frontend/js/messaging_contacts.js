/**
 * Conversation list sidebar and contact picker for the messaging panel.
 * Loads conversations from the API, renders them in the sidebar,
 * and provides a modal for starting new conversations.
 */
class MessagingContacts {
    constructor(listEl, onSelect) {
        this._listEl = listEl;
        this._onSelect = onSelect;
        this._channels = [];
        this._conversations = [];
        this._activeNodeId = null;
        this._filter = 'all';
    }

    async load(includeOverheard = false) {
        try {
            const [convosRes, channelsRes] = await Promise.all([
                fetch(includeOverheard
                    ? '/api/messages/conversations?include_overheard=true'
                    : '/api/messages/conversations'),
                fetch('/api/messages/channels'),
            ]);
            this._conversations = await convosRes.json();
            this._channels = await channelsRes.json();
            this.render();
        } catch (e) {
            console.error('Failed to load conversations:', e);
        }
    }

    render() {
        this._listEl.innerHTML = '';

        const filteredChannels = this._filter === 'all'
            ? this._channels
            : this._channels.filter(c => c.protocol === this._filter);

        if (filteredChannels.length > 0) {
            const label = document.createElement('div');
            label.className = 'msg-sidebar__section-label';
            label.textContent = 'Channels';
            this._listEl.appendChild(label);

            filteredChannels.forEach(ch => {
                const convo = this._channelToConvo(ch);
                const el = this._buildConvoEl(convo);
                this._listEl.appendChild(el);
            });
        }

        const dmConvos = (this._filter === 'all'
            ? this._conversations
            : this._conversations.filter(c => c.protocol === this._filter)
        ).filter(c => !c.is_broadcast);

        if (dmConvos.length > 0) {
            const label = document.createElement('div');
            label.className = 'msg-sidebar__section-label';
            label.textContent = 'Direct Messages';
            this._listEl.appendChild(label);

            dmConvos.forEach(convo => {
                const el = this._buildConvoEl(convo);
                this._listEl.appendChild(el);
            });
        }

        if (filteredChannels.length === 0 && dmConvos.length === 0) {
            this._listEl.innerHTML = '<div class="msg-chat__empty">No conversations yet</div>';
        }
    }

    _channelToConvo(ch) {
        const existing = this._conversations.find(c => c.node_id === ch.node_id);
        return {
            node_id: ch.node_id,
            node_name: ch.name,
            protocol: ch.protocol,
            channel: ch.channel || 0,
            is_broadcast: true,
            last_message: existing ? existing.last_message : '',
            last_timestamp: existing ? existing.last_timestamp : '',
            unread_count: existing ? existing.unread_count : 0,
        };
    }

    setFilter(protocol) {
        this._filter = protocol;
        this.render();
    }

    setActive(nodeId) {
        this._activeNodeId = nodeId;
        this._listEl.querySelectorAll('.msg-convo').forEach(el => {
            el.classList.toggle('msg-convo--active', el.dataset.nodeId === nodeId);
        });
    }

    addOrUpdateConversation(msg) {
        const existing = this._conversations.find(c => c.node_id === msg.node_id);
        if (existing) {
            existing.last_message = msg.text || msg.last_message || '';
            existing.last_timestamp = msg.timestamp || new Date().toISOString();
            if (msg.direction === 'received' && msg.node_id !== this._activeNodeId) {
                existing.unread_count = (existing.unread_count || 0) + 1;
            }
        } else {
            this._conversations.unshift({
                node_id: msg.node_id,
                node_name: msg.node_name || msg.node_id,
                protocol: msg.protocol || 'meshtastic',
                last_message: msg.text || '',
                last_timestamp: msg.timestamp || new Date().toISOString(),
                unread_count: msg.direction === 'received' ? 1 : 0,
                is_broadcast: (msg.node_id || '').startsWith('broadcast:'),
            });
        }
        this._sortByRecent();
        this.render();
        if (this._activeNodeId) this.setActive(this._activeNodeId);
    }

    async openContactPicker() {
        try {
            const res = await fetch('/api/messages/contacts');
            const contacts = await res.json();
            this._showModal(contacts);
        } catch (e) {
            console.error('Failed to load contacts:', e);
        }
    }

    _buildConvoEl(convo) {
        const el = document.createElement('div');
        el.className = 'msg-convo';
        if (convo.is_broadcast) el.classList.add('msg-convo--channel');
        if (convo.node_id === this._activeNodeId) el.classList.add('msg-convo--active');
        el.dataset.nodeId = convo.node_id;

        const isChannel = !!convo.is_broadcast;
        const iconClass = isChannel
            ? 'msg-convo__icon--channel'
            : convo.protocol === 'meshcore'
                ? 'msg-convo__icon--mc'
                : 'msg-convo__icon--mt';

        const iconText = isChannel
            ? '#'
            : (convo.node_name || '?').slice(0, 2).toUpperCase();

        const displayName = isChannel
            ? convo.node_name || `Ch ${convo.channel || 0}`
            : convo.node_name || convo.node_id;

        const protoBadge = convo.protocol === 'meshcore' ? 'MC' : 'MT';

        const timeStr = convo.last_timestamp
            ? new Date(convo.last_timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : '';

        el.innerHTML = `
            <div class="msg-convo__icon ${iconClass}">${iconText}</div>
            <div class="msg-convo__info">
                <div class="msg-convo__name">${this._esc(displayName)} <span class="msg-convo__proto-badge msg-convo__proto-badge--${convo.protocol === 'meshcore' ? 'mc' : 'mt'}">${protoBadge}</span></div>
                <div class="msg-convo__preview">${this._esc(convo.last_message || '')}</div>
            </div>
            <div class="msg-convo__meta">
                <div class="msg-convo__time">${timeStr}</div>
                ${convo.unread_count > 0 ? `<div class="msg-convo__unread">${convo.unread_count}</div>` : ''}
                <button class="msg-convo__delete" title="Delete conversation">&times;</button>
            </div>
        `;

        el.querySelector('.msg-convo__delete').addEventListener('click', (e) => {
            e.stopPropagation();
            this._deleteConversation(convo);
        });

        el.addEventListener('click', () => {
            this.setActive(convo.node_id);
            this._onSelect(convo);
        });
        return el;
    }

    _showModal(contacts) {
        const overlay = document.createElement('div');
        overlay.className = 'msg-modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'msg-modal';
        modal.innerHTML = `
            <div class="msg-modal__header">
                <span class="msg-modal__title">New Conversation</span>
                <button class="msg-modal__close">&times;</button>
            </div>
            <input class="msg-modal__search" placeholder="Search nodes..." />
            <div class="msg-modal__list"></div>
        `;

        const list = modal.querySelector('.msg-modal__list');
        const search = modal.querySelector('.msg-modal__search');

        const renderContacts = (filter) => {
            list.innerHTML = '';
            const filtered = filter
                ? contacts.filter(c => (c.name || '').toLowerCase().includes(filter) || (c.node_id || '').toLowerCase().includes(filter))
                : contacts;

            filtered.forEach(contact => {
                const item = document.createElement('div');
                item.className = 'msg-contact';
                const pClass = contact.protocol === 'meshcore' ? 'msg-contact__protocol--mc' : 'msg-contact__protocol--mt';
                item.innerHTML = `
                    <span class="msg-contact__name">${this._esc(contact.name || contact.node_id)}</span>
                    <span class="msg-contact__protocol ${pClass}">${contact.protocol === 'meshcore' ? 'MC' : 'MT'}</span>
                `;
                item.addEventListener('click', () => {
                    overlay.remove();
                    this._onSelect({
                        node_id: contact.node_id,
                        node_name: contact.name || contact.node_id,
                        protocol: contact.protocol,
                        is_broadcast: false,
                    });
                });
                list.appendChild(item);
            });
        };

        renderContacts('');
        search.addEventListener('input', () => renderContacts(search.value.toLowerCase()));
        modal.querySelector('.msg-modal__close').addEventListener('click', () => overlay.remove());
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        search.focus();
    }

    async _deleteConversation(convo) {
        try {
            const res = await fetch(`/api/messages/conversation/${encodeURIComponent(convo.node_id)}`, {
                method: 'DELETE',
            });
            if (!res.ok) return;
            this._conversations = this._conversations.filter(c => c.node_id !== convo.node_id);
            if (this._activeNodeId === convo.node_id) {
                this._activeNodeId = null;
                this._onSelect(null);
            }
            this.render();
        } catch (e) {
            console.error('Failed to delete conversation:', e);
        }
    }

    _sortByRecent() {
        this._conversations.sort((a, b) => {
            const ta = a.last_timestamp ? new Date(a.last_timestamp).getTime() : 0;
            const tb = b.last_timestamp ? new Date(b.last_timestamp).getTime() : 0;
            return tb - ta;
        });
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

/** Configuration → GPS — position broadcast interval editor. */

class PositionBroadcastCard {
    constructor(api, { meshcore = false } = {}) {
        // PiMesh's existing scheduler sends MeshCore identity adverts. Retain
        // its persisted interval and API while presenting the protocol's terms.
        this._inner = new window.BroadcastIntervalCard(api, {
            title: meshcore ? 'MeshCore advertisement interval' : 'Position broadcast interval',
            hint: meshcore
                ? 'How often PiMesh announces its MeshCore identity. Advertisements include the configured location. Set 0 to pause scheduled advertisements; manual adverts remain available.'
                : 'How often this Meshpoint sends POSITION packets on the mesh '
                + '(Meshtastic app map). Separate from NodeInfo identity broadcasts.',
            saveLabel: meshcore ? 'Save advertisement interval' : 'Save position interval',
            putUrl: '/api/config/position',
            configKey: 'position',
            cardId: meshcore ? 'cfg-meshcore-advert-interval' : 'cfg-position-interval',
        });
    }

    mount(root) {
        this._inner.mount(root);
    }

    render(config) {
        this._inner.render(config);
    }
}

window.PositionBroadcastCard = PositionBroadcastCard;

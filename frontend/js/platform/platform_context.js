/**
 * Platform helpers for gateway vs WisMesh Node (meshtasticd) installs.
 */

function isNodePlatform(config) {
    return (config && config.device && config.device.platform) === 'node';
}

function isWismeshNode(config) {
    return isNodePlatform(config)
        && config.platform_ui
        && config.platform_ui.variant === 'wismesh_node';
}

function platformLabel(config) {
    return isNodePlatform(config) ? 'WisMesh Node' : 'Gateway';
}

function meshtasticdRuntime(config) {
    if (!config || !config.meshtasticd_runtime) return {};
    return config.meshtasticd_runtime;
}

function meshtasticdConfig(config) {
    const capture = (config && config.capture) || {};
    return capture.meshtasticd || {};
}

window.PlatformContext = {
    isNodePlatform,
    isWismeshNode,
    platformLabel,
    meshtasticdRuntime,
    meshtasticdConfig,
};

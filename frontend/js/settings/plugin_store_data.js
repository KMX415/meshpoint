/** Display metadata only. Installability always comes from a trusted source API. */
window.MESHPOINT_MODULES = [
    ['reticulum', 'Reticulum', 'Networks', 'Connect beyond the usual mesh.', 'LXMF messages, peer discovery and NomadNet pages over an RNode or a network interface.', 'RNode for LoRa · optional network connection', 'network'],
    ['rtlsdr', 'RTL-SDR Hub', 'Radio', 'One place for your receivers.', 'The shared workspace for radio, aircraft, sensors and pager modules. Start here for RTL-SDR.', 'RTL-SDR USB receiver', 'spectrum'],
    ['p25', 'P25', 'Radio', 'Follow local digital radio.', 'Receive unencrypted P25 Phase I/II voice with trunk tracking, talkgroup filters and browser audio. Hardware validation pending.', 'RTL-SDR Hub · OP25 · GNU Radio · ffmpeg', 'wave'],
    ['radio', 'Radio', 'Radio', 'Tune into something new.', 'Listen to FM, AM and SSB, save stations and view FM RDS information.', 'RTL-SDR Hub · rtl_fm · ffmpeg', 'wave'],
    ['dab', 'DAB+', 'Radio', 'Digital radio, on your dashboard.', 'Scan Band III ensembles and play DAB or DAB+ where those services are available. L-Band is not supported.', 'RTL-SDR Hub · welle-cli · DAB coverage', 'wave'],
    ['adsb', 'ADS-B', 'Aviation', 'See the traffic overhead.', 'Track 1090 MHz aircraft signals with a live aircraft table and map.', 'RTL-SDR Hub · dump1090 · 1090 MHz antenna', 'plane'],
    ['acars', 'ACARS', 'Aviation', 'Explore aircraft datalink.', 'Choose local ACARS VHF channels and inspect received aircraft datalink messages.', 'RTL-SDR Hub · acarsdec · VHF antenna', 'plane'],
    ['rtl433', 'RTL433', 'Sensors', 'Listen to the world around you.', 'Choose the frequency used by your weather station, remote sensor or other supported OOK/FSK device.', 'RTL-SDR Hub · rtl_433', 'sensor'],
    ['pagers', 'Pagers', 'Paging', 'A dedicated pager workspace.', 'Inspect received POCSAG messages with controls for your local frequency and receiver.', 'RTL-SDR Hub · rtl_fm · multimon-ng', 'pager'],
    ['pocsag', 'POCSAG', 'Paging', 'Explore amateur paging.', 'Receive POCSAG512, 1200 and 2400 signals. Choose the frequency used in your region.', 'RTL-SDR Hub · rtl_fm · multimon-ng', 'pager'],
    ['p2000', 'P2000', 'Paging', 'Dutch FLEX dispatch signals.', 'Decode P2000 transmissions on 169.65 MHz with a dedicated message view.', 'RTL-SDR Hub · multimon-ng · Netherlands coverage', 'pager'],
].map(([id, name, category, tagline, description, hardware, icon]) => ({id, name, category, tagline, description, hardware, icon, kind:'app'}));

window.meshpointModuleIcon = function (name) {
    const paths = {
        network:'<circle cx="12" cy="12" r="3"/><circle cx="4" cy="4" r="2"/><circle cx="20" cy="5" r="2"/><circle cx="19" cy="20" r="2"/><circle cx="4" cy="20" r="2"/><path d="m6 6 4 4m4 0 4-4m-4 8 4 4M6 18l4-4"/>',
        spectrum:'<path d="M3 19V9m4 10V5m5 14V2m5 17V7m4 12V12"/>',
        wave:'<path d="M2 12h3l3-8 4 16 4-16 3 8h3"/>',
        plane:'<path d="m12 3 2 7 7 5v2l-7-2v5l2 2-4-1-4 1 2-2v-5l-7 2v-2l7-5 2-7Z"/>',
        sensor:'<circle cx="12" cy="15" r="2"/><path d="M8 10a6 6 0 0 1 8 0M5 7a10 10 0 0 1 14 0M12 17v5"/>',
        pager:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 9h10v4H7zM7 16h2m3 0h2"/>',
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(paths[name] || paths.spectrum)+'</svg>';
};

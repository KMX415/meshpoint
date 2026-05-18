/**
 * Terminal ASCII splash banner.
 *
 * Writes a one-shot welcome banner directly into the xterm buffer
 * the first time a session connects. Uses ANSI color codes so the
 * banner picks up the Tokyo Night Storm palette already configured
 * by TerminalRenderer. Subsequent reconnects skip the banner so
 * the operator isn't trained to scroll past noise.
 *
 * Single responsibility: paint the banner. The orchestrator
 * (TerminalPanelController) calls render() once per session.
 */
class TerminalSplash {
    constructor() {
        this._shown = false;
    }

    render(renderer, sessionInfo) {
        if (!renderer || !renderer.term) return;
        if (this._shown) return;
        this._shown = true;
        const term = renderer.term;
        const lines = TerminalSplash._buildLines(sessionInfo || {});
        for (const line of lines) {
            term.writeln(line);
        }
        term.writeln('');
    }

    reset() {
        // Called when the user explicitly disconnects so the next
        // fresh connect re-paints the banner.
        this._shown = false;
    }

    static _buildLines(info) {
        const cyan = '\x1b[38;5;39m';
        const dim = '\x1b[38;5;245m';
        const accent = '\x1b[38;5;213m';
        const reset = '\x1b[0m';
        const bold = '\x1b[1m';

        // figlet "ANSI Shadow" font, lightly pruned.
        const art = [
            ' ███╗   ███╗███████╗███████╗██╗  ██╗██████╗  ██████╗ ██╗███╗   ██╗████████╗',
            ' ████╗ ████║██╔════╝██╔════╝██║  ██║██╔══██╗██╔═══██╗██║████╗  ██║╚══██╔══╝',
            ' ██╔████╔██║█████╗  ███████╗███████║██████╔╝██║   ██║██║██╔██╗ ██║   ██║   ',
            ' ██║╚██╔╝██║██╔══╝  ╚════██║██╔══██║██╔═══╝ ██║   ██║██║██║╚██╗██║   ██║   ',
            ' ██║ ╚═╝ ██║███████╗███████║██║  ██║██║     ╚██████╔╝██║██║ ╚████║   ██║   ',
            ' ╚═╝     ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝╚═╝  ╚═══╝   ╚═╝   ',
        ];

        const rule = ' ─────────────────────────────────────────────────────────────────────────';
        const host = info.hostname ? String(info.hostname) : 'meshpoint';
        const user = info.user ? String(info.user) : 'meshpoint';
        const shell = info.shell ? String(info.shell).split('/').pop() : 'sh';
        const pid = info.pid ? `pid ${info.pid}` : '';
        const meta = [
            `${user}@${host}`,
            shell,
            pid,
        ].filter(Boolean).join('  ·  ');

        const lines = [];
        lines.push('');
        for (const row of art) {
            lines.push(`${cyan}${row}${reset}`);
        }
        lines.push(`${dim}${rule}${reset}`);
        lines.push(`  ${bold}${accent}meshpoint${reset}${dim}  console session  ·  ${meta}${reset}`);
        lines.push(`${dim}${rule}${reset}`);
        lines.push('');
        lines.push(
            `  ${dim}Type ${reset}${cyan}help${reset}${dim} for shell tips.`
            + `  ${reset}${cyan}Ctrl+Shift+F${reset}${dim} find.`
            + `  ${reset}${cyan}Ctrl+Shift+C${reset}${dim} copy.${reset}`,
        );
        lines.push('');
        return lines;
    }
}

window.TerminalSplash = TerminalSplash;

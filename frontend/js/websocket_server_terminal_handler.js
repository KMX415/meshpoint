/**
 * Optional backend helper for shell command WebSocket support.
 * This is a Node.js example handler for `shell_command` -> `shell_output`.
 * Integrate on your server side if you want the Terminal tab to execute commands.
 */
const { spawn } = require("child_process");

const BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",
    "chmod -R 777 /",
    "chown -R",
    "> /dev/sda",
];

const COMMAND_TIMEOUT_MS = 30000;

function attachTerminalHandler(ws) {
    let activeProcess = null;

    ws.on("message", (raw) => {
        let msg;
        try { msg = JSON.parse(raw); } catch { return; }
        if (msg.type !== "shell_command") return;

        const { command, command_id } = msg.data || {};
        if (!command || typeof command !== "string") return;
        const cmdLower = command.trim().toLowerCase();

        for (const blocked of BLOCKED_COMMANDS) {
            if (cmdLower.includes(blocked)) {
                send(ws, { stream: "stderr", text: `Blocked: "${blocked}"`, command_id });
                send(ws, { exit_code: 1, command_id });
                return;
            }
        }

        if (activeProcess) {
            try { activeProcess.kill(); } catch {}
            activeProcess = null;
        }

        const proc = spawn("bash", ["-c", command], {
            env: { ...process.env, TERM: "xterm-256color" },
            cwd: process.env.HOME || "/",
        });
        activeProcess = proc;

        const timeoutHandle = setTimeout(() => {
            if (activeProcess === proc) {
                try { proc.kill("SIGTERM"); } catch {}
                send(ws, { stream: "stderr", text: "Killed: command timed out.", command_id });
                send(ws, { exit_code: 124, command_id });
                activeProcess = null;
            }
        }, COMMAND_TIMEOUT_MS);

        proc.stdout.on("data", (chunk) => send(ws, { stream: "stdout", text: chunk.toString(), command_id }));
        proc.stderr.on("data", (chunk) => send(ws, { stream: "stderr", text: chunk.toString(), command_id }));
        proc.on("close", (code) => {
            clearTimeout(timeoutHandle);
            send(ws, { exit_code: code ?? 0, command_id });
            activeProcess = null;
        });
        proc.on("error", (err) => {
            clearTimeout(timeoutHandle);
            send(ws, { stream: "stderr", text: `Process error: ${err.message}`, command_id });
            send(ws, { exit_code: 1, command_id });
            activeProcess = null;
        });
    });

    ws.on("close", () => {
        if (activeProcess) {
            try { activeProcess.kill(); } catch {}
            activeProcess = null;
        }
    });
}

function send(ws, data) {
    try {
        if (ws.readyState === 1) ws.send(JSON.stringify({ type: "shell_output", data }));
    } catch {}
}

module.exports = { attachTerminalHandler };

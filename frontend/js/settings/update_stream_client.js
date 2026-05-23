/**
 * Consumes NDJSON streams from ``/api/update/apply/stream`` and
 * ``/api/update/rollback/stream``.
 */

class UpdateStreamClient {
    /**
     * @param {string} url
     * @param {object} body JSON request body
     * @param {(event: object) => void} onEvent called for each parsed line
     * @returns {Promise<object|null>} final ApplyResult payload or null
     */
    static async postNdjson(url, body, onEvent) {
        const response = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/x-ndjson',
            },
            body: JSON.stringify(body),
        });
        if (!response.ok) {
            const err = new Error(`HTTP ${response.status}`);
            err.status = response.status;
            throw err;
        }
        if (!response.body) {
            throw new Error('Streaming not supported in this browser.');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalResult = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let newline = buffer.indexOf('\n');
            while (newline >= 0) {
                const line = buffer.slice(0, newline).trim();
                buffer = buffer.slice(newline + 1);
                if (line) {
                    const event = JSON.parse(line);
                    onEvent(event);
                    if (event.type === 'result') {
                        finalResult = event.result || null;
                    }
                }
                newline = buffer.indexOf('\n');
            }
        }
        const tail = buffer.trim();
        if (tail) {
            const event = JSON.parse(tail);
            onEvent(event);
            if (event.type === 'result') {
                finalResult = event.result || null;
            }
        }
        return finalResult;
    }
}

window.UpdateStreamClient = UpdateStreamClient;

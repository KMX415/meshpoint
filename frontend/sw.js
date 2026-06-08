/**
 * Minimal service worker for LAN dashboard push notifications.
 * The main app posts show-notification messages while a tab is open.
 */
self.addEventListener('install', (event) => {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type !== 'show-notification') return;
    const title = data.title || 'Meshpoint';
    const options = {
        body: data.body || '',
        tag: data.tag || 'meshpoint-alert',
        renotify: true,
        data: data.payload || {},
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
            for (const client of clients) {
                if ('focus' in client) return client.focus();
            }
            if (self.clients.openWindow) return self.clients.openWindow('/');
            return undefined;
        }),
    );
});

const CACHE_NAME = 'kia-ai-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});

// Handle incoming push notifications
self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (e) {
        data = { title: 'Nuevo mensaje', body: event.data ? event.data.text() : '' };
    }

    const title = data.title || '💬 Nuevo mensaje WhatsApp';
    const options = {
        body: data.body || '',
        icon: 'https://hotboatchile.com/wp-content/uploads/cropped-Screenshot_3-192x192.jpg',
        badge: 'https://hotboatchile.com/wp-content/uploads/cropped-Screenshot_3-32x32.jpg',
        tag: data.phone || 'general',
        renotify: true,
        data: {
            phone: data.phone || null,
            // El panel admin se sirve en "/" (ver app/main.py) — "/admin-bookings"
            // nunca existió como ruta y devolvía 404 al abrir la notificación con
            // la app cerrada (con la app abierta, el otro branch de abajo la
            // enfoca y navega por postMessage, por eso no siempre fallaba).
            url: data.phone ? `/?phone=${data.phone}` : '/',
        },
        vibrate: [200, 100, 200],
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

// Handle notification tap → open/focus app at the right chat
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = event.notification.data?.url || '/';
    const phone = event.notification.data?.phone;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // App already open → focus and navigate
            for (const client of clientList) {
                if ('focus' in client) {
                    client.focus();
                    if (phone) {
                        client.postMessage({ type: 'OPEN_CHAT', phone });
                    }
                    return;
                }
            }
            // App closed → open it
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});

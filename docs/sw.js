self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'Digest AI', {
      body: data.body || 'Nuovo digest disponibile!',
      icon: 'https://masmerenda-lab.github.io/ai-digest/icon-192.png',
      badge: 'https://masmerenda-lab.github.io/ai-digest/icon-192.png',
      data: { url: data.url || 'https://masmerenda-lab.github.io/ai-digest/' },
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      const url = event.notification.data.url;
      for (const client of list) {
        if (client.url === url && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

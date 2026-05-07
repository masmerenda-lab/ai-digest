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
  const url = event.notification.data.url;
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      // Cerca una finestra già aperta sul dominio e naviga direttamente al digest
      for (const client of list) {
        if ('navigate' in client) return client.navigate(url).then(c => c?.focus());
      }
      return clients.openWindow(url);
    })
  );
});

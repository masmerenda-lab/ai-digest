// Sostituire con la VAPID_PUBLIC_KEY reale dopo aver eseguito la generazione keys
const VAPID_PUBLIC_KEY = 'BFjOBWVXRmrwQLkJqAH29gcbzx104Bg4_DAFCDuClaHvHNAO4gWUW5c1csadlVBdq2YpPLA-m-GPeg0KjC0CC3Y';
const WORKER_URL = 'SOSTITUIRE_CON_URL_CLOUDFLARE_WORKER';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

async function iscrivi() {
  const btn = document.getElementById('btn-iscrivi');
  const stato = document.getElementById('stato');

  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    stato.textContent = '⚠️ Il tuo browser non supporta le notifiche push.';
    stato.className = 'stato errore';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Iscrizione in corso…';
  stato.textContent = '';

  try {
    const reg = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;

    const perm = await Notification.requestPermission();
    if (perm !== 'granted') {
      stato.textContent = '❌ Permesso notifiche negato. Abilitalo dalle impostazioni del browser.';
      stato.className = 'stato errore';
      btn.disabled = false;
      btn.textContent = 'Iscriviti alle notifiche';
      return;
    }

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });

    const resp = await fetch(`${WORKER_URL}/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub),
    });

    if (!resp.ok) throw new Error(`Worker ha risposto ${resp.status}`);

    stato.textContent = '✅ Iscritto! Riceverai una notifica ad ogni nuovo digest.';
    stato.className = 'stato ok';
    btn.textContent = '✓ Iscritto';
    localStorage.setItem('subscribed', '1');
  } catch (err) {
    console.error(err);
    stato.textContent = `❌ Errore durante l'iscrizione: ${err.message}`;
    stato.className = 'stato errore';
    btn.disabled = false;
    btn.textContent = 'Riprova';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btn-iscrivi');
  if (!btn) return;
  if (localStorage.getItem('subscribed')) {
    btn.textContent = '✓ Già iscritto';
    btn.disabled = true;
  }
  btn.addEventListener('click', iscrivi);

  // Carica lista digest
  fetch('/digests.json')
    .then(r => r.json())
    .then(list => {
      const ul = document.getElementById('digest-list');
      if (!ul || !list.length) return;
      ul.innerHTML = list.slice(0, 5).map(d =>
        `<li><a href="/digests/${d.date}.html">${d.title} <span class="digest-date">${d.date}</span></a></li>`
      ).join('');
    })
    .catch(() => {});
});

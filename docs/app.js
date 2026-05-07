const VAPID_PUBLIC_KEY = 'BFjOBWVXRmrwQLkJqAH29gcbzx104Bg4_DAFCDuClaHvHNAO4gWUW5c1csadlVBdq2YpPLA-m-GPeg0KjC0CC3Y';
const WORKER_URL = 'https://ai-digest-notify.masmerenda.workers.dev';

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
    const reg = await navigator.serviceWorker.register('./sw.js');
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
    const { id } = await resp.json();

    stato.textContent = '✅ Iscritto! Riceverai una notifica ad ogni nuovo digest.';
    stato.className = 'stato ok';
    btn.textContent = '✓ Iscritto';
    localStorage.setItem('subscribed', '1');
    localStorage.setItem('subscription_id', id);

    mostraDisiscriviti();
    aggiornaContatore();
  } catch (err) {
    console.error(err);
    stato.textContent = `❌ Errore durante l'iscrizione: ${err.message}`;
    stato.className = 'stato errore';
    btn.disabled = false;
    btn.textContent = 'Iscriviti alle notifiche';
  }
}

async function disiscriviti() {
  const stato = document.getElementById('stato');
  const btn = document.getElementById('btn-disiscriviti');
  btn.disabled = true;
  btn.textContent = 'Disiscrizione in corso…';

  try {
    const reg = await navigator.serviceWorker.getRegistration('./sw.js');
    if (reg) {
      const sub = await reg.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
    }

    const id = localStorage.getItem('subscription_id');
    if (id) {
      await fetch(`${WORKER_URL}/unsubscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id }),
      });
    }

    localStorage.removeItem('subscribed');
    localStorage.removeItem('subscription_id');

    const btnIscrivi = document.getElementById('btn-iscrivi');
    btnIscrivi.disabled = false;
    btnIscrivi.textContent = 'Iscriviti alle notifiche';

    document.getElementById('disiscriviti-box').style.display = 'none';
    stato.textContent = 'Disiscritto. Puoi reiscriverti quando vuoi.';
    stato.className = 'stato';
    aggiornaContatore();
  } catch (err) {
    console.error(err);
    stato.textContent = `❌ Errore disiscrizione: ${err.message}`;
    stato.className = 'stato errore';
    btn.disabled = false;
    btn.textContent = 'Disiscriviti';
  }
}

function mostraDisiscriviti() {
  const box = document.getElementById('disiscriviti-box');
  if (box) box.style.display = 'block';
}

async function aggiornaContatore() {
  try {
    const r = await fetch(`${WORKER_URL}/subscribers/count`);
    const { count } = await r.json();
    const el = document.getElementById('contatore');
    if (el) el.textContent = count === 1 ? '1 persona iscritta' : `${count} persone iscritte`;
  } catch {}
}

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btn-iscrivi');
  if (!btn) return;

  if (localStorage.getItem('subscribed')) {
    btn.textContent = '✓ Iscritto';
    btn.disabled = true;
    mostraDisiscriviti();
  }
  btn.addEventListener('click', iscrivi);

  const btnDis = document.getElementById('btn-disiscriviti');
  if (btnDis) btnDis.addEventListener('click', disiscriviti);

  aggiornaContatore();

  // Carica lista digest in homepage
  fetch('./digests.json')
    .then(r => r.json())
    .then(list => {
      const ul = document.getElementById('digest-list');
      if (!ul || !list.length) return;
      ul.innerHTML = list.slice(0, 5).map(d =>
        `<li><a href="./digests/${d.date}.html">${d.title} <span class="digest-date">${d.date}</span></a></li>`
      ).join('');
    })
    .catch(() => {});
});

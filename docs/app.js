const VAPID_PUBLIC_KEY = 'BFjOBWVXRmrwQLkJqAH29gcbzx104Bg4_DAFCDuClaHvHNAO4gWUW5c1csadlVBdq2YpPLA-m-GPeg0KjC0CC3Y';
const WORKER_URL = 'https://ai-digest-notify.masmerenda.workers.dev';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

function getChecked(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(el => el.value);
}

function setChecked(name, values) {
  document.querySelectorAll(`input[name="${name}"]`).forEach(cb => {
    cb.checked = values.includes(cb.value);
  });
}

// ---------------------------------------------------------------------------
// Gestione viste
// ---------------------------------------------------------------------------

function mostraFormIscrizione() {
  document.getElementById('view-subscribe').style.display = 'block';
  document.getElementById('view-profile').style.display = 'none';
  // Ripristina preferenze salvate nei checkbox di iscrizione
  const saved = localStorage.getItem('subscription_preferences');
  if (saved) {
    try { setChecked('cat', JSON.parse(saved)); } catch {}
  }
}

function mostraProfiloIscritto() {
  document.getElementById('view-subscribe').style.display = 'none';
  document.getElementById('view-profile').style.display = 'block';
  // Sincronizza checkbox profilo con preferenze salvate
  const saved = localStorage.getItem('subscription_preferences');
  if (saved) {
    try { setChecked('pref', JSON.parse(saved)); } catch {}
  }
}

// ---------------------------------------------------------------------------
// Verifica stato iscrizione all'avvio
// ---------------------------------------------------------------------------

async function verificaIscrizione() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
  try {
    const reg = await navigator.serviceWorker.getRegistration('./sw.js');
    if (!reg) { mostraFormIscrizione(); return; }
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      localStorage.setItem('subscribed', '1');
      mostraProfiloIscritto();
    } else {
      localStorage.removeItem('subscribed');
      localStorage.removeItem('subscription_id');
      mostraFormIscrizione();
    }
  } catch {
    mostraFormIscrizione();
  }
}

// ---------------------------------------------------------------------------
// Iscrizione
// ---------------------------------------------------------------------------

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

    const preferences = getChecked('cat');
    const resp = await fetch(`${WORKER_URL}/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...sub.toJSON(), preferences }),
    });
    if (!resp.ok) throw new Error(`Worker ha risposto ${resp.status}`);
    const { id } = await resp.json();

    localStorage.setItem('subscribed', '1');
    localStorage.setItem('subscription_id', id);
    localStorage.setItem('subscription_preferences', JSON.stringify(preferences));

    mostraProfiloIscritto();
    aggiornaContatore();
  } catch (err) {
    console.error(err);
    document.getElementById('stato').textContent = `❌ Errore: ${err.message}`;
    document.getElementById('stato').className = 'stato errore';
    document.getElementById('btn-iscrivi').disabled = false;
    document.getElementById('btn-iscrivi').textContent = 'Iscriviti alle notifiche';
  }
}

// ---------------------------------------------------------------------------
// Aggiorna preferenze
// ---------------------------------------------------------------------------

async function aggiornaPreferenze() {
  const btn = document.getElementById('btn-update-prefs');
  const stato = document.getElementById('prefs-stato');
  const id = localStorage.getItem('subscription_id');

  if (!id) {
    stato.textContent = '⚠️ ID iscrizione non trovato. Disiscriviti e reiscriviti.';
    stato.className = 'stato errore';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvataggio…';

  try {
    const preferences = getChecked('pref');
    if (!preferences.length) {
      stato.textContent = '⚠️ Seleziona almeno una categoria.';
      stato.className = 'stato errore';
      btn.disabled = false;
      btn.textContent = 'Salva preferenze';
      return;
    }

    const resp = await fetch(`${WORKER_URL}/update-preferences`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, preferences }),
    });
    if (!resp.ok) throw new Error(`Errore ${resp.status}`);

    localStorage.setItem('subscription_preferences', JSON.stringify(preferences));
    stato.textContent = '✅ Preferenze aggiornate!';
    stato.className = 'stato ok';
    setTimeout(() => { stato.textContent = ''; stato.className = 'stato'; }, 3000);
  } catch (err) {
    stato.textContent = `❌ ${err.message}`;
    stato.className = 'stato errore';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salva preferenze';
  }
}

// ---------------------------------------------------------------------------
// Disiscrizione
// ---------------------------------------------------------------------------

async function disiscriviti() {
  const btn = document.getElementById('btn-disiscriviti');
  const stato = document.getElementById('prefs-stato');
  btn.disabled = true;
  btn.textContent = 'Disiscrizione…';

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
    mostraFormIscrizione();
    aggiornaContatore();
  } catch (err) {
    stato.textContent = `❌ Errore: ${err.message}`;
    stato.className = 'stato errore';
    btn.disabled = false;
    btn.textContent = 'Disiscriviti';
  }
}

// ---------------------------------------------------------------------------
// Contatore
// ---------------------------------------------------------------------------

async function aggiornaContatore() {
  try {
    const r = await fetch(`${WORKER_URL}/subscribers/count`);
    const { count } = await r.json();
    const el = document.getElementById('contatore');
    if (el) el.textContent = count === 1 ? '1 persona iscritta' : `${count} persone iscritte`;
  } catch {}
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-iscrivi')?.addEventListener('click', iscrivi);
  document.getElementById('btn-update-prefs')?.addEventListener('click', aggiornaPreferenze);
  document.getElementById('btn-disiscriviti')?.addEventListener('click', disiscriviti);

  verificaIscrizione();
  aggiornaContatore();

  // Digest settimanali
  fetch('./weekly.json')
    .then(r => r.json())
    .then(list => {
      if (!list.length) return;
      const sec = document.getElementById('weekly-section');
      const ul = document.getElementById('weekly-list');
      if (!sec || !ul) return;
      sec.style.display = 'block';
      ul.innerHTML = list.slice(0, 3).map(d =>
        `<li><a href="./${d.url}">${d.title} <span class="digest-date">${d.week}</span></a></li>`
      ).join('');
    })
    .catch(() => {});

  // Ultimi digest
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

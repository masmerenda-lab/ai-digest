#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Digest Quotidiano AI
====================
Raccoglie le ultime notizie sull'AI da GitHub Trending, Hacker News e Reddit,
le categorizza e riassume tramite Google Gemini, e genera un PDF quotidiano.

Autore: AI Assistant
Versione: 1.0
"""

import os
import json
import subprocess
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from fpdf import FPDF
import google.generativeai as genai
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# Carica le variabili d'ambiente dal file .env
load_dotenv(Path(__file__).parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Cartella di output per i PDF generati
OUTPUT_DIR = Path.home() / "Documenti" / "AI_Digests"

# File di log nella stessa cartella dello script
LOG_FILE = Path(__file__).parent / "digest.log"

# Parole chiave per filtrare contenuti AI da fonti generiche.
# Divise in due gruppi: quelle che richiedono match esatto di parola (\b)
# e quelle che possono essere sottostringhe.
AI_KEYWORDS_EXACT = [
    r"\bai\b", r"\bllm\b", r"\bgpt\b", r"\bnlp\b", r"\brag\b",
    r"\bml\b",
]
AI_KEYWORDS_SUBSTR = [
    "artificial intelligence", "machine learning", "deep learning",
    "transformer", "neural network", "computer vision",
    "diffusion model", "stable diffusion", "chatgpt", "claude ai",
    "pytorch", "tensorflow", "hugging face", "langchain", "openai",
    "anthropic", "mistral", "llama", "generative ai", "vector db",
    "embedding model", "fine-tun", "foundation model", "multimodal",
    "reinforcement learning", "large language", "copilot",
    "open-swe", "unsloth", "vllm", "adk-python",
]

import re as _re

def _is_ai_content(text: str) -> bool:
    """Verifica se il testo e' pertinente all'AI con filtro preciso."""
    text_lower = text.lower()
    # Check substring keywords
    if any(kw in text_lower for kw in AI_KEYWORDS_SUBSTR):
        return True
    # Check word-boundary keywords (evita falsi positivi come "detail" che contiene nulla, ecc.)
    if any(_re.search(kw, text_lower) for kw in AI_KEYWORDS_EXACT):
        return True
    return False

# Headers HTTP comuni per evitare blocchi
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Setup logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modulo 1: Scraping GitHub Trending
# ---------------------------------------------------------------------------

def scrape_github_trending() -> list[dict]:
    """
    Scrape i repository in tendenza su GitHub filtrati per argomenti AI.
    Controlla sia la sezione Python che quella generale.

    Returns:
        Lista di dict con: nome, descrizione, stelle_oggi, url, fonte
    """
    repos = []
    urls = [
        "https://github.com/trending/python?since=daily",
        "https://github.com/trending?since=daily",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Ogni repository e' un tag <article class="Box-row">
            for article in soup.select("article.Box-row"):
                # Estrai path del repo (es. "owner/repo-name")
                h2 = article.select_one("h2 a")
                if not h2:
                    continue
                repo_path = h2.get("href", "").strip("/")
                repo_name = repo_path.replace("/", " / ")
                repo_url = f"https://github.com/{repo_path}"

                # Descrizione del repository
                desc_el = article.select_one("p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                # Stelle guadagnate oggi (solitamente nell'ultimo span float-right)
                stars_el = article.select_one("span.d-inline-block.float-sm-right")
                stars_today = stars_el.get_text(strip=True) if stars_el else ""

                # Filtra: tieni solo repo rilevanti per AI
                testo = repo_name + " " + description
                if _is_ai_content(testo):
                    repos.append({
                        "nome": repo_name,
                        "descrizione": description,
                        "stelle_oggi": stars_today,
                        "url": repo_url,
                        "fonte": "GitHub Trending",
                    })

        except requests.RequestException as e:
            logger.warning(f"Errore scraping GitHub ({url}): {e}")

    # Rimuovi duplicati basandosi sull'URL
    seen = set()
    unique_repos = []
    for r in repos:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique_repos.append(r)

    logger.info(f"GitHub Trending: trovati {len(unique_repos)} repository AI")
    return unique_repos[:20]  # Limita a 20 per non sovraccaricare Gemini


# ---------------------------------------------------------------------------
# Modulo 2: Fetch Hacker News (Firebase API)
# ---------------------------------------------------------------------------

def fetch_hackernews() -> list[dict]:
    """
    Recupera le top stories di Hacker News filtrate per argomenti AI.
    Usa la Firebase REST API ufficiale (nessuna chiave richiesta).

    Returns:
        Lista di dict con: titolo, url, punteggio, commenti, fonte
    """
    items = []

    try:
        # Recupera gli ID delle top 500 storie
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=15,
        )
        resp.raise_for_status()
        story_ids = resp.json()[:300]  # Esamina i primi 300 ID

        for story_id in story_ids:
            if len(items) >= 25:
                break
            try:
                story_resp = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    timeout=8,
                )
                story = story_resp.json()
                if not story or story.get("type") != "story":
                    continue

                title = story.get("title", "")
                # Filtra per keyword AI (con word-boundary per evitare falsi positivi)
                if _is_ai_content(title):
                    items.append({
                        "titolo": story.get("title", ""),
                        "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "punteggio": story.get("score", 0),
                        "commenti": story.get("descendants", 0),
                        "fonte": "Hacker News",
                    })
            except Exception:
                continue  # Salta item problematici senza crashare

    except requests.RequestException as e:
        logger.warning(f"Errore Hacker News: {e}")

    logger.info(f"Hacker News: trovati {len(items)} articoli AI")
    return items


# ---------------------------------------------------------------------------
# Modulo 3: Fetch Reddit
# ---------------------------------------------------------------------------

def fetch_reddit() -> list[dict]:
    """
    Recupera i post piu' votati di oggi dai subreddit AI piu' rilevanti.
    Usa l'API JSON pubblica di Reddit (nessuna chiave richiesta).

    Returns:
        Lista di dict con: titolo, url, permalink, punteggio, subreddit, fonte
    """
    posts = []

    # Subreddit da monitorare, in ordine di priorita'
    subreddits = [
        "MachineLearning",
        "artificial",
        "LocalLLaMA",
        "deeplearning",
        "learnmachinelearning",
    ]

    reddit_headers = {
        "User-Agent": "AI-Digest-Bot/1.0 (by /u/digest_bot)"
    }

    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=10"
            resp = requests.get(url, headers=reddit_headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                # Salta i post moderati o rimossi
                if p.get("removed_by_category") or not p.get("title"):
                    continue
                posts.append({
                    "titolo": p.get("title", ""),
                    "url": p.get("url", ""),
                    "permalink": f"https://reddit.com{p.get('permalink', '')}",
                    "punteggio": p.get("score", 0),
                    "subreddit": sub,
                    "fonte": f"Reddit r/{sub}",
                })

            # Piccola pausa per non martellare Reddit
            time.sleep(1)

        except requests.RequestException as e:
            logger.warning(f"Errore Reddit r/{sub}: {e}")

    logger.info(f"Reddit: trovati {len(posts)} post")
    return posts[:25]  # Limita a 25


# ---------------------------------------------------------------------------
# Modulo 4: Summarizzazione con Google Gemini
# ---------------------------------------------------------------------------

def summarize_with_gemini(
    github_data: list[dict],
    hn_data: list[dict],
    reddit_data: list[dict],
) -> dict:
    """
    Invia tutti i dati grezzi a Google Gemini per analisi, categorizzazione
    e riassunto in italiano. Gemini restituisce un JSON strutturato con
    le 3 sezioni del digest.

    Returns:
        Dict con chiavi: nuovi_strumenti, repo_trending, aggiornamenti_framework
    """
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Modello Gemini in uso: gemini-2.5-flash")

    # Combina tutti i dati in un unico oggetto per il prompt
    raw_data = {
        "github_trending": github_data,
        "hacker_news": hn_data,
        "reddit": reddit_data,
    }

    prompt = f"""Sei un esperto analista di intelligenza artificiale. Analizza i dati raccolti oggi da GitHub Trending, Hacker News e Reddit e crea un digest strutturato in italiano.

DATI RACCOLTI (JSON grezzo):
{json.dumps(raw_data, ensure_ascii=False, indent=2)}

Il tuo compito:
1. Analizza tutti gli elementi
2. Classificali in 3 categorie (vedi sotto)
3. Scegli i 5-8 piu' significativi per ogni categoria
4. Scrivi un riassunto di 2-3 frasi in italiano per ognuno

CATEGORIE:
- "nuovi_strumenti": Nuovi tool AI, prodotti, servizi, assistenti, API, piattaforme lanciate di recente o con aggiornamenti importanti
- "repo_trending": Repository GitHub con forte crescita di stelle, progetti open-source emergenti, demo virali
- "aggiornamenti_framework": Aggiornamenti a librerie/framework esistenti (PyTorch, TensorFlow, JAX, HuggingFace, LangChain, ecc.)

FORMATO OUTPUT (JSON puro, nessun testo aggiuntivo, nessun markdown):
{{
  "nuovi_strumenti": [
    {{
      "titolo": "Nome strumento o servizio",
      "riassunto": "2-3 frasi in italiano. Cosa fa, perche' e' rilevante, per chi e' utile.",
      "url": "URL diretto allo strumento/articolo",
      "fonte": "Fonte originale (es. Hacker News, Reddit r/MachineLearning)"
    }}
  ],
  "repo_trending": [
    {{
      "titolo": "owner/nome-repository",
      "riassunto": "2-3 frasi in italiano. Cosa fa il repo, perche' sta guadagnando popolarita'.",
      "stelle_oggi": "stelle guadagnate oggi (es. +1.234 stelle oggi) o stringa vuota se non disponibile",
      "url": "URL GitHub del repository",
      "fonte": "GitHub Trending"
    }}
  ],
  "aggiornamenti_framework": [
    {{
      "titolo": "Nome framework - versione o tipo aggiornamento",
      "riassunto": "2-3 frasi in italiano sulle novita' principali dell'aggiornamento.",
      "url": "URL alla release notes o all'annuncio",
      "fonte": "Fonte"
    }}
  ]
}}

REGOLE IMPORTANTI:
- Rispondi SOLO con il JSON valido, zero testo prima o dopo
- I riassunti devono essere SEMPRE in italiano
- Se un elemento non ha un URL valido, usa il permalink Reddit o il link HN
- Preferisci qualita' alla quantita': meglio 5 elementi ottimi che 8 mediocri
- Se una categoria ha pochi dati, e' accettabile avere anche solo 2-3 elementi"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Rimuovi eventuali delimitatori markdown se Gemini li aggiunge
        if text.startswith("```"):
            parts = text.split("```")
            # Prendi il contenuto tra i primi backtick
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        logger.info(
            f"Gemini: "
            f"{len(result.get('nuovi_strumenti', []))} strumenti, "
            f"{len(result.get('repo_trending', []))} repo, "
            f"{len(result.get('aggiornamenti_framework', []))} framework"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Errore parsing JSON da Gemini: {e}")
        logger.debug(f"Risposta grezza: {response.text[:500]}")
        # Fallback: usa i dati grezzi senza riassunto AI
        return _fallback_struttura(github_data, hn_data, reddit_data)

    except Exception as e:
        logger.error(f"Errore chiamata Gemini: {e}")
        return _fallback_struttura(github_data, hn_data, reddit_data)


def _fallback_struttura(github_data, hn_data, reddit_data) -> dict:
    """
    Struttura di fallback usata se Gemini non e' disponibile.
    Usa i dati grezzi senza riassunto AI.
    """
    logger.warning("Uso struttura di fallback (senza riassunto AI)")
    return {
        "nuovi_strumenti": [
            {
                "titolo": item["titolo"],
                "riassunto": item.get("url", ""),
                "url": item.get("url", ""),
                "fonte": item["fonte"],
            }
            for item in (hn_data + reddit_data)[:6]
        ],
        "repo_trending": [
            {
                "titolo": r["nome"],
                "riassunto": r.get("descrizione", "Nessuna descrizione disponibile."),
                "stelle_oggi": r.get("stelle_oggi", ""),
                "url": r["url"],
                "fonte": r["fonte"],
            }
            for r in github_data[:6]
        ],
        "aggiornamenti_framework": [],
    }


# ---------------------------------------------------------------------------
# Modulo 5: Generazione PDF
# ---------------------------------------------------------------------------

class DigestPDF(FPDF):
    """Classe FPDF personalizzata con header e footer del digest."""

    def footer(self):
        """Footer con numero pagina e data generazione."""
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(160, 160, 160)
        data = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.cell(
            0, 10,
            f"Pagina {self.page_no()} | Generato il {data} | Digest Quotidiano AI",
            align="C",
        )


def _tronca_url(url: str, max_len: int = 85) -> str:
    """Tronca URL lunghi per la visualizzazione nel PDF."""
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."


def genera_pdf(dati: dict, output_path: Path) -> None:
    """
    Genera il PDF del digest AI con design pulito e professionale.

    Args:
        dati: Dict strutturato da Gemini con le 3 sezioni
        output_path: Percorso completo del file PDF da creare
    """
    pdf = DigestPDF()
    pdf.set_auto_page_break(auto=True, margin=22)

    # Carica font Unicode DejaVu per supporto completo caratteri (en-dash, accenti, ecc.)
    dejavu_dir = "/usr/share/fonts/truetype/dejavu"
    pdf.add_font("DejaVu", "",  f"{dejavu_dir}/DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", f"{dejavu_dir}/DejaVuSans-Bold.ttf")

    pdf.add_page()

    data_oggi = datetime.now().strftime("%d %B %Y")

    # -----------------------------------------------------------------------
    # INTESTAZIONE (sfondo blu scuro)
    # -----------------------------------------------------------------------
    pdf.set_fill_color(20, 30, 55)
    pdf.rect(0, 0, 210, 48, "F")

    pdf.set_y(7)
    pdf.set_font("DejaVu", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 13, "Digest Quotidiano AI", align="C", ln=True)

    pdf.set_font("DejaVu", "", 12)
    pdf.set_text_color(180, 200, 240)
    pdf.cell(0, 8, data_oggi, align="C", ln=True)

    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(140, 165, 210)
    pdf.cell(
        0, 7,
        "Le ultime novita' nel mondo dell'intelligenza artificiale",
        align="C", ln=True,
    )

    pdf.set_y(55)

    # -----------------------------------------------------------------------
    # Funzione helper per disegnare una sezione
    # -----------------------------------------------------------------------
    def scrivi_sezione(
        titolo_sezione: str,
        elementi: list,
        colore_accent: tuple,
        icona: str = "",
    ) -> None:
        """Disegna una sezione del digest con titolo e lista di elementi."""
        if not elementi:
            logger.warning(f"Sezione '{titolo_sezione}' vuota, saltata.")
            return

        # Sfondo leggero per il titolo sezione
        pdf.set_fill_color(245, 247, 252)
        pdf.set_font("DejaVu", "B", 13)
        pdf.set_text_color(*colore_accent)
        pdf.cell(0, 11, f"  {icona}  {titolo_sezione}", ln=True, fill=True)

        # Linea colorata sotto il titolo
        r, g, b = colore_accent
        pdf.set_draw_color(r, g, b)
        pdf.set_line_width(0.8)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)

        for i, item in enumerate(elementi, start=1):
            titolo = item.get("titolo", "N/D")
            riassunto = item.get("riassunto", "")
            url = item.get("url", "")
            fonte = item.get("fonte", "")
            stelle = item.get("stelle_oggi", "")

            # Numero + titolo elemento
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(25, 30, 55)
            pdf.multi_cell(0, 6, f"{i}. {titolo}")
            pdf.ln(1)

            # Riassunto (testo principale)
            if riassunto:
                pdf.set_font("DejaVu", "", 9)
                pdf.set_text_color(55, 60, 85)
                pdf.multi_cell(0, 5.5, riassunto)
                pdf.ln(1)

            # Stelle (solo per sezione repo GitHub)
            if stelle:
                pdf.set_font("DejaVu", "B", 8)
                pdf.set_text_color(200, 130, 0)
                pdf.cell(0, 5, f"  Stelle oggi: {stelle}", ln=True)

            # Metadati: URL e fonte
            if url:
                pdf.set_font("DejaVu", "", 8)
                pdf.set_text_color(50, 110, 190)
                pdf.cell(0, 5, f"  Link: {_tronca_url(url)}", ln=True)

            if fonte:
                pdf.set_font("DejaVu", "", 8)
                pdf.set_text_color(130, 130, 150)
                pdf.cell(0, 5, f"  Fonte: {fonte}", ln=True)

            # Separatore sottile tra elementi
            pdf.set_draw_color(215, 220, 235)
            pdf.set_line_width(0.15)
            pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
            pdf.ln(7)

        pdf.ln(4)

    # -----------------------------------------------------------------------
    # Scrittura delle 3 sezioni
    # -----------------------------------------------------------------------
    scrivi_sezione(
        "Nuovi Strumenti e Servizi AI",
        dati.get("nuovi_strumenti", []),
        colore_accent=(34, 130, 80),   # Verde
        icona="[TOOL]",
    )

    scrivi_sezione(
        "Repository GitHub in Tendenza",
        dati.get("repo_trending", []),
        colore_accent=(40, 110, 185),  # Blu
        icona="[REPO]",
    )

    scrivi_sezione(
        "Aggiornamenti Framework e Librerie",
        dati.get("aggiornamenti_framework", []),
        colore_accent=(175, 85, 30),   # Arancio
        icona="[UPDATE]",
    )

    # Crea la cartella di output se non esiste
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Salva il PDF
    pdf.output(str(output_path))
    logger.info(f"PDF salvato in: {output_path}")


# ---------------------------------------------------------------------------
# Modulo 6: Pubblicazione web + Web Push
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).parent / "web"
TEMPLATES_DIR = Path(__file__).parent / "templates"
WORKER_URL = os.getenv("WORKER_URL", "")
NOTIFY_SECRET = os.getenv("NOTIFY_SECRET", "")
GITHUB_PAGES_BASE_URL = os.getenv("GITHUB_PAGES_BASE_URL", "")


def genera_html(dati: dict, data_str: str, pdf_path: Path | None = None) -> Path:
    """Genera la pagina HTML del digest usando il template Jinja2."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("digest.html.j2")

    date_obj = datetime.strptime(data_str, "%Y-%m-%d")
    date_long = date_obj.strftime("%-d %B %Y")

    pdf_url = None
    if pdf_path and GITHUB_PAGES_BASE_URL:
        pdf_url = f"{GITHUB_PAGES_BASE_URL.rstrip('/')}/digests/{pdf_path.name}"

    html = template.render(
        date=data_str,
        date_long=date_long,
        data=dati,
        pdf_url=pdf_url,
    )

    output_path = WEB_DIR / "digests" / f"{data_str}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(f"HTML salvato in: {output_path}")
    return output_path


def aggiorna_indice(data_str: str, titolo: str) -> None:
    """Aggiunge il digest corrente in cima a web/digests.json."""
    indice_path = WEB_DIR / "digests.json"
    try:
        entries = json.loads(indice_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        entries = []

    # Evita duplicati per la stessa data
    entries = [e for e in entries if e.get("date") != data_str]
    entries.insert(0, {"date": data_str, "title": titolo})

    indice_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Indice aggiornato: {len(entries)} digest totali")


def pubblica_su_github_pages() -> None:
    """Committa e pusha web/ sul repository GitHub Pages."""
    repo_dir = Path(__file__).parent
    try:
        subprocess.run(["git", "add", "web/"], cwd=repo_dir, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_dir, capture_output=True
        )
        if result.returncode == 0:
            logger.info("GitHub Pages: nessuna modifica da committare.")
            return
        data_str = datetime.now().strftime("%Y-%m-%d")
        subprocess.run(
            ["git", "commit", "-m", f"digest: {data_str}"],
            cwd=repo_dir, check=True, capture_output=True
        )
        subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
        logger.info("GitHub Pages: push completato.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"GitHub Pages push fallito: {e.stderr.decode(errors='replace')}")


def notifica_iscritti(titolo: str, data_str: str, riassunto: str = "") -> None:
    """Invia Web Push a tutti gli iscritti tramite il Cloudflare Worker."""
    if not WORKER_URL or not NOTIFY_SECRET:
        logger.warning("WORKER_URL o NOTIFY_SECRET mancanti — notifiche saltate.")
        return

    page_url = (
        f"{GITHUB_PAGES_BASE_URL.rstrip('/')}/digests/{data_str}.html"
        if GITHUB_PAGES_BASE_URL
        else "/"
    )

    try:
        resp = requests.post(
            f"{WORKER_URL.rstrip('/')}/notify",
            headers={"Authorization": f"Bearer {NOTIFY_SECRET}", "Content-Type": "application/json"},
            json={"title": titolo, "body": riassunto or "Nuovo digest disponibile!", "url": page_url},
            timeout=20,
        )
        resp.raise_for_status()
        stats = resp.json()
        logger.info(f"Web Push inviato: {stats}")
    except Exception as e:
        logger.warning(f"Notifiche Web Push fallite: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Pipeline completa: raccolta dati -> Gemini -> PDF -> HTML -> GitHub Pages -> Web Push.
    """
    logger.info("=" * 55)
    logger.info("  AVVIO DIGEST QUOTIDIANO AI")
    logger.info("=" * 55)

    if not GEMINI_API_KEY:
        logger.error(
            "GEMINI_API_KEY non trovata!\n"
            "Crea il file ~/ai_digest/.env con:\n"
            "  GEMINI_API_KEY=la-tua-chiave"
        )
        raise SystemExit(1)

    # --- Fase 1: Raccolta dati ---
    logger.info("[1/4] Raccolta dati da GitHub Trending...")
    github_data = scrape_github_trending()

    logger.info("[1/4] Raccolta dati da Hacker News...")
    hn_data = fetch_hackernews()

    logger.info("[1/4] Raccolta dati da Reddit...")
    reddit_data = fetch_reddit()

    totale = len(github_data) + len(hn_data) + len(reddit_data)
    logger.info(f"Dati raccolti: {totale} elementi totali")

    if totale == 0:
        logger.error("Nessun dato raccolto. Controlla la connessione internet.")
        raise SystemExit(1)

    # --- Fase 2: Elaborazione con Gemini ---
    logger.info("[2/4] Elaborazione con Google Gemini...")
    dati_strutturati = summarize_with_gemini(github_data, hn_data, reddit_data)

    data_str = datetime.now().strftime("%Y-%m-%d")

    # --- Fase 3: Generazione PDF + HTML ---
    logger.info("[3/4] Generazione PDF e HTML...")
    output_file = OUTPUT_DIR / f"AI_Digest_{data_str}.pdf"
    genera_pdf(dati_strutturati, output_file)
    genera_html(dati_strutturati, data_str, pdf_path=output_file)

    titolo_digest = f"Digest AI – {datetime.now().strftime('%-d %B %Y')}"
    aggiorna_indice(data_str, titolo_digest)

    # --- Fase 4: Pubblicazione e notifiche ---
    logger.info("[4/4] Pubblicazione su GitHub Pages e invio notifiche...")
    pubblica_su_github_pages()

    primo_riassunto = ""
    strumenti = dati_strutturati.get("nuovi_strumenti", [])
    if strumenti:
        primo_riassunto = strumenti[0].get("riassunto", "")[:120]

    notifica_iscritti(titolo_digest, data_str, primo_riassunto)

    logger.info("=" * 55)
    logger.info(f"  COMPLETATO -> {output_file}")
    logger.info("=" * 55)
    print(f"\nDigest generato con successo!\nFile: {output_file}\n")


if __name__ == "__main__":
    main()

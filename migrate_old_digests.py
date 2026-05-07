#!/usr/bin/env python3
"""
Migra i vecchi PDF in docs/digests/ e genera pagine HTML wrapper per ciascuno.
Aggiorna docs/digests.json con tutte le voci, ordinando dal più recente.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

PDF_DIR = Path.home() / "Documenti" / "AI_Digests"
DOCS_DIR = Path(__file__).parent / "docs" / "digests"
INDEX_PATH = Path(__file__).parent / "docs" / "digests.json"
PAGES_BASE = "https://masmerenda-lab.github.io/ai-digest"

DOCS_DIR.mkdir(parents=True, exist_ok=True)

def html_wrapper(date_str: str, pdf_filename: str) -> str:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_long = date_obj.strftime("%-d %B %Y")
    pdf_url = f"../digests/{pdf_filename}"
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Digest AI – {date_str}</title>
  <link rel="stylesheet" href="../style.css">
  <style>
    .digest-header {{ background: #141e37; color: #fff; padding: 2rem 1.5rem 1.5rem; text-align: center; }}
    .digest-header h1 {{ margin: 0 0 0.3rem; font-size: 1.6rem; }}
    .digest-header .date {{ color: #b4c8f0; font-size: 0.95rem; }}
    .pdf-box {{ margin: 2rem 1rem; text-align: center; }}
    .pdf-box embed {{ width: 100%; height: 80vh; border: 1px solid #e0e4f0; border-radius: 6px; }}
    .pdf-box .no-pdf {{ padding: 2rem; background: #f4f6fb; border-radius: 8px; font-size: 0.9rem; color: #60607a; }}
    .dl-btn {{ display: inline-block; margin: 1rem auto; background: #141e37; color: #fff; padding: 0.6rem 1.5rem; border-radius: 6px; text-decoration: none; font-size: 0.9rem; }}
    .dl-btn:hover {{ background: #286eb9; }}
    .back-link {{ display: block; text-align: center; padding: 1rem; font-size: 0.85rem; color: #326ebe; }}
  </style>
</head>
<body>
  <div class="digest-header">
    <h1>Digest Quotidiano AI</h1>
    <div class="date">{date_long}</div>
  </div>
  <div class="pdf-box">
    <a class="dl-btn" href="{pdf_url}" download>⬇ Scarica PDF</a>
    <br>
    <embed src="{pdf_url}" type="application/pdf"
      onerror="this.style.display='none';document.getElementById('nopdf').style.display='block'">
    <div id="nopdf" class="no-pdf" style="display:none">
      Il tuo browser non supporta la visualizzazione inline dei PDF.
      <br><a href="{pdf_url}">Scarica il PDF</a>
    </div>
  </div>
  <a class="back-link" href="../index.html">← Tutti i digest</a>
</body>
</html>"""

# Carica indice esistente
try:
    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    entries = []

existing_dates = {e["date"] for e in entries}
added = 0

for pdf_path in sorted(PDF_DIR.glob("AI_Digest_*.pdf")):
    # Estrai data dal nome file: AI_Digest_2026-03-20.pdf
    date_str = pdf_path.stem.replace("AI_Digest_", "")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"  SKIP (data non valida): {pdf_path.name}")
        continue

    # Copia PDF in docs/digests/
    dest_pdf = DOCS_DIR / pdf_path.name
    if not dest_pdf.exists():
        shutil.copy2(pdf_path, dest_pdf)

    # Genera HTML wrapper se non esiste già un HTML completo
    html_path = DOCS_DIR / f"{date_str}.html"
    if not html_path.exists():
        html_path.write_text(html_wrapper(date_str, pdf_path.name), encoding="utf-8")
        print(f"  Creato: {html_path.name}")
        added += 1
    else:
        print(f"  Esiste già: {html_path.name} (salto)")

    # Aggiungi all'indice se non c'è
    if date_str not in existing_dates:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        titolo = f"Digest AI – {date_obj.strftime('%-d %B %Y')}"
        entries.append({"date": date_str, "title": titolo})
        existing_dates.add(date_str)

# Ordina per data decrescente e salva
entries.sort(key=lambda e: e["date"], reverse=True)
INDEX_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\nMigrazione completata: {added} nuove pagine HTML create.")
print(f"Indice aggiornato: {len(entries)} digest totali.")

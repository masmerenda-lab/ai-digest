#!/bin/bash
# =============================================================================
# setup.sh - Configurazione automatica del Digest Quotidiano AI
# =============================================================================
# Questo script:
#   1. Verifica i requisiti di sistema
#   2. Crea il virtual environment Python
#   3. Installa le dipendenze
#   4. Crea la cartella di output per i PDF
#   5. Configura il cron job per l'esecuzione alle 8:00 ogni mattina
#   6. Guida alla configurazione della chiave API Gemini
# =============================================================================

set -e  # Interrompi in caso di errore

# --- Colori per output leggibile ---
VERDE='\033[0;32m'
GIALLO='\033[1;33m'
ROSSO='\033[0;31m'
BLU='\033[0;34m'
RESET='\033[0m'
GRASSETTO='\033[1m'

# --- Percorsi ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SCRIPT_PY="$SCRIPT_DIR/digest.py"
ENV_FILE="$SCRIPT_DIR/.env"
OUTPUT_DIR="$HOME/Documenti/AI_Digests"
PYTHON_BIN="$VENV_DIR/bin/python"
LOG_FILE="$SCRIPT_DIR/digest.log"

echo ""
echo -e "${GRASSETTO}${BLU}=================================================${RESET}"
echo -e "${GRASSETTO}${BLU}   SETUP DIGEST QUOTIDIANO AI - Google Gemini   ${RESET}"
echo -e "${GRASSETTO}${BLU}=================================================${RESET}"
echo ""

# =============================================================================
# STEP 1: Verifica requisiti di sistema
# =============================================================================
echo -e "${GRASSETTO}[1/5] Verifica requisiti di sistema...${RESET}"

# Controlla Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${ROSSO}ERRORE: Python 3 non trovato!${RESET}"
    echo "Installa Python 3 con: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "  Python trovato: ${VERDE}$PYTHON_VER${RESET}"

# Controlla python3-venv
if ! python3 -c "import venv" &>/dev/null; then
    echo -e "${ROSSO}ERRORE: modulo venv non disponibile!${RESET}"
    echo "Installa con: sudo apt install python3-venv"
    exit 1
fi

# Controlla cron
if ! command -v crontab &>/dev/null; then
    echo -e "${ROSSO}ERRORE: crontab non trovato!${RESET}"
    echo "Installa con: sudo apt install cron"
    exit 1
fi

echo -e "  ${VERDE}Tutti i requisiti soddisfatti.${RESET}"

# =============================================================================
# STEP 2: Virtual environment
# =============================================================================
echo ""
echo -e "${GRASSETTO}[2/5] Configurazione virtual environment Python...${RESET}"

if [ -d "$VENV_DIR" ]; then
    echo -e "  Virtual environment gia' esistente, lo aggiorno..."
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
else
    echo -e "  Creazione virtual environment in: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip --quiet
fi

echo -e "  ${VERDE}Virtual environment pronto.${RESET}"

# =============================================================================
# STEP 3: Installazione dipendenze
# =============================================================================
echo ""
echo -e "${GRASSETTO}[3/5] Installazione dipendenze Python...${RESET}"

"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" --quiet

echo -e "  ${VERDE}Dipendenze installate con successo.${RESET}"

# =============================================================================
# STEP 4: Cartella output e configurazione API key
# =============================================================================
echo ""
echo -e "${GRASSETTO}[4/5] Configurazione cartella output e API key...${RESET}"

# Crea cartella output PDF
mkdir -p "$OUTPUT_DIR"
echo -e "  Cartella PDF creata: ${VERDE}$OUTPUT_DIR${RESET}"

# Gestione file .env con chiave API
if [ -f "$ENV_FILE" ] && grep -q "GEMINI_API_KEY=." "$ENV_FILE" 2>/dev/null; then
    CURRENT_KEY=$(grep "GEMINI_API_KEY" "$ENV_FILE" | cut -d'=' -f2)
    if [ "$CURRENT_KEY" != "inserisci-qui-la-tua-chiave-google-gemini" ] && [ -n "$CURRENT_KEY" ]; then
        echo -e "  Chiave API Gemini gia' configurata: ${VERDE}${CURRENT_KEY:0:8}...${RESET}"
    else
        _configura_api_key
    fi
else
    _configura_api_key() {
        echo ""
        echo -e "  ${GIALLO}========================================${RESET}"
        echo -e "  ${GIALLO}  CONFIGURAZIONE CHIAVE API GEMINI     ${RESET}"
        echo -e "  ${GIALLO}========================================${RESET}"
        echo ""
        echo -e "  Per ottenere la tua chiave API gratuita Google Gemini:"
        echo -e "  1. Vai su: https://aistudio.google.com/app/apikey"
        echo -e "  2. Clicca su 'Create API Key'"
        echo -e "  3. Copia la chiave generata"
        echo ""
        read -rp "  Inserisci la tua GEMINI_API_KEY: " api_key

        if [ -z "$api_key" ]; then
            echo -e "  ${GIALLO}Chiave non inserita. Configurala manualmente in: $ENV_FILE${RESET}"
            cp "$SCRIPT_DIR/.env.example" "$ENV_FILE" 2>/dev/null || true
        else
            echo "GEMINI_API_KEY=$api_key" > "$ENV_FILE"
            echo -e "  ${VERDE}Chiave API salvata in $ENV_FILE${RESET}"
        fi
    }
    _configura_api_key
fi

# =============================================================================
# STEP 5: Cron job
# =============================================================================
echo ""
echo -e "${GRASSETTO}[5/5] Configurazione cron job (ogni giorno alle 8:00)...${RESET}"

# Costruisci il comando cron con percorsi assoluti
CRON_CMD="0 8 * * * cd $SCRIPT_DIR && $PYTHON_BIN $SCRIPT_PY >> $LOG_FILE 2>&1"
CRON_MARKER="# AI-Digest-Daily"

# Controlla se il cron job e' gia' installato
if crontab -l 2>/dev/null | grep -q "AI-Digest-Daily"; then
    echo -e "  Cron job gia' installato. Aggiorno il comando..."
    # Rimuovi la vecchia entry e aggiungila aggiornata
    (crontab -l 2>/dev/null | grep -v "AI-Digest-Daily" | grep -v "digest.py") | crontab -
fi

# Aggiungi il nuovo cron job
(crontab -l 2>/dev/null; echo "$CRON_MARKER"; echo "$CRON_CMD") | crontab -

echo -e "  ${VERDE}Cron job configurato: esecuzione ogni giorno alle 08:00${RESET}"
echo ""
echo -e "  Verifica con: ${BLU}crontab -l${RESET}"
echo -e "  Cron installato:"
crontab -l 2>/dev/null | grep -A1 "AI-Digest" | sed 's/^/    /'

# =============================================================================
# RIEPILOGO FINALE
# =============================================================================
echo ""
echo -e "${GRASSETTO}${VERDE}=================================================${RESET}"
echo -e "${GRASSETTO}${VERDE}   SETUP COMPLETATO CON SUCCESSO!               ${RESET}"
echo -e "${GRASSETTO}${VERDE}=================================================${RESET}"
echo ""
echo -e "  ${GRASSETTO}Riepilogo configurazione:${RESET}"
echo -e "  • Script:        $SCRIPT_PY"
echo -e "  • Venv:          $VENV_DIR"
echo -e "  • PDF output:    $OUTPUT_DIR"
echo -e "  • Log:           $LOG_FILE"
echo -e "  • Esecuzione:    ogni giorno alle 08:00"
echo ""
echo -e "  ${GRASSETTO}Per eseguire il digest ADESSO (test):${RESET}"
echo -e "  ${BLU}cd $SCRIPT_DIR && $PYTHON_BIN digest.py${RESET}"
echo ""
echo -e "  ${GRASSETTO}Per vedere il log in tempo reale:${RESET}"
echo -e "  ${BLU}tail -f $LOG_FILE${RESET}"
echo ""
echo -e "  ${GIALLO}NOTA: Assicurati che la chiave API in .env sia valida${RESET}"
echo -e "  ${GIALLO}prima della prima esecuzione automatica.${RESET}"
echo ""

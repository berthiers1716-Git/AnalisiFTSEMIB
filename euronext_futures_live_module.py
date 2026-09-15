# File: euronext_futures_live_module.py
#
# Recupera i dati LIVE (delayed 15') dalla pagina Settlement Prices di Euronext
# per il FUTURE FIB-DMIL (a differenza di euronext_live_module.py, che copre le
# OPZIONI MIB-DMIL). Stessa idea, stesso meccanismo di sessione: qui l'endpoint
# AJAX e il formato della tabella sono per ANALOGIA con quello delle opzioni,
# NON verificati ispezionando il traffico di rete reale del browser (non è
# possibile farlo da qui). Vedi mostra_diagnostica_grezza(): se il parsing
# normale fallisce, salva la risposta grezza su file per poterla controllare e
# correggere il regex in un colpo solo, invece di procedere a tentativi.
#
# Nato dall'esigenza di archiviare l'Open Interest del future prima che una
# scadenza (es. Set 2026, "settimana della strega") esca dall'elenco quotato e
# sparisca dalla pagina live - qui viene tenuto uno storico locale persistente
# indipendente da cosa Euronext continua o smette di mostrare.
#
# Ultima modifica: 2026-09-14
# -----------------------------------------------------------------------------

import re
import os
import calendar
import datetime as dt
import numpy as np
import pandas as pd
import requests

REFERER = "https://live.euronext.com/en/product/index-futures/FIB-DMIL/settlement-prices"
ENDPOINT = "https://live.euronext.com/en/ajax/getTabPrices/FIB-DMIL/futures"

# Scadenze di riserva (formato MM-01-YYYY), usate solo se la lettura dinamica
# dalla pagina fallisce. Il future FIB ha solo il ciclo trimestrale (a
# differenza delle opzioni MIBO, che hanno anche le mensili) - vedi screenshot
# dell'11/09/2026: Sep 2026, Dec 2026, Mar 2027, Jun 2027.
SCADENZE_NOTE = ["09-01-2026", "12-01-2026", "03-01-2027", "06-01-2027"]

_MESI_EN = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
    'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12',
}
_DELIVERY_MONTHS_BLOCK_RE = re.compile(
    r'Select Delivery Month\(s\)(.*?)Trade Date', re.DOTALL
)
_MESE_ANNO_RE = re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b')

# Riga tabella GENERICA (non lega ai nomi delle classi CSS, solo 9 <td> in un
# <tr>): Delivery, Open, High, Low, Last, Change, Settle, Volume, Open Interest.
# Scelta deliberatamente tollerante perché non abbiamo potuto verificare i nomi
# esatti delle classi come per le opzioni (vedi nota in testa al file).
_ROW_RE = re.compile(
    r'<tr[^>]*>\s*'
    r'<td[^>]*>\s*(\w{3}\s+\d{4})\s*</td>\s*'   # Delivery, es. "Sep 2026"
    r'<td[^>]*>([^<]*)</td>\s*'                  # Open
    r'<td[^>]*>([^<]*)</td>\s*'                  # High
    r'<td[^>]*>([^<]*)</td>\s*'                  # Low
    r'<td[^>]*>([^<]*)</td>\s*'                  # Last
    r'<td[^>]*>([^<]*)</td>\s*'                  # Change
    r'<td[^>]*>([^<]*)</td>\s*'                  # Settle
    r'<td[^>]*>([^<]*)</td>\s*'                  # Volume
    r'<td[^>]*>([^<]*)</td>\s*'                  # Open Interest
    r'</tr>',
    re.DOTALL
)


def crea_sessione():
    """Crea una sessione requests e visita prima la pagina normale (come fa un
    browser) per ottenere il cookie di sessione necessario alla chiamata AJAX."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    })
    session.get(REFERER, timeout=15)
    return session


def fetch_scadenze_disponibili(session):
    """Legge dalla pagina Settlement Prices le scadenze future attualmente
    quotate (stessa idea del modulo opzioni: la pagina le elenca in chiaro
    nella sezione "Select Delivery Month(s)"). Fallback su SCADENZE_NOTE se
    il parsing fallisce per qualsiasi motivo."""
    try:
        resp = session.get(REFERER, timeout=15)
        resp.raise_for_status()
        blocco = _DELIVERY_MONTHS_BLOCK_RE.search(resp.text)
        if not blocco:
            return list(SCADENZE_NOTE)
        trovate = _MESE_ANNO_RE.findall(blocco.group(1))
        if not trovate:
            return list(SCADENZE_NOTE)
        scadenze = {f"{_MESI_EN[mese]}-01-{anno}" for mese, anno in trovate}
        return sorted(scadenze, key=lambda s: (s[-4:], s[:2]))
    except Exception:
        return list(SCADENZE_NOTE)


def fetch_live_html(session, expiries=None, trade_date=None):
    """
    expiries: lista di stringhe 'MM-01-YYYY' (default: SCADENZE_NOTE).
    trade_date: stringa 'MM-DD-YYYY' (default: oggi).

    NOTA: i nomi dei parametri POST ('mt', 'md[]', 'td') sono per analogia col
    modulo opzioni - non verificati per le futures specificamente.

    Returns: testo HTML grezzo della risposta.
    """
    if expiries is None:
        expiries = SCADENZE_NOTE
    if trade_date is None:
        trade_date = dt.date.today().strftime("%m-%d-%Y")

    data = [("mt", "M")] + [("md[]", e) for e in expiries] + [("td", trade_date)]
    headers = {
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": REFERER,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    resp = session.post(ENDPOINT, data=data, headers=headers, timeout=45)
    resp.raise_for_status()
    return resp.text


def _terzo_venerdi(year, month_num):
    c = calendar.Calendar()
    fridays = [d for d in c.itermonthdates(year, month_num)
               if d.weekday() == 4 and d.month == month_num]
    return pd.Timestamp(fridays[2])


def _numero_pulito(s):
    s = (s or "").strip().replace(",", "")
    if s in ('', 'N/A', '-'):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_live_html(html_text, trade_date=None):
    """
    Fa il parsing della risposta HTML (una riga per scadenza, non a blocchi
    come le opzioni). Solleva ValueError con un messaggio esplicito se non
    trova righe riconoscibili - usa mostra_diagnostica_grezza() in quel caso.

    Returns: DataFrame con colonne Scadenza (data di terzo-venerdi'),
             Mese_Anno (stringa "Sep 2026"), Open, High, Low, Last, Change,
             Settle, Volume, OI, Data_Scarico.
    """
    righe = []
    for m in _ROW_RE.finditer(html_text):
        mon_year_str, open_s, high_s, low_s, last_s, change_s, settle_s, vol_s, oi_s = m.groups()
        mon_abbr, year_s = mon_year_str.split()
        year = int(year_s)
        month_num = dt.datetime.strptime(mon_abbr, "%b").month
        scadenza = _terzo_venerdi(year, month_num)

        righe.append({
            'Scadenza': scadenza,
            'Mese_Anno': mon_year_str,
            'Open': _numero_pulito(open_s),
            'High': _numero_pulito(high_s),
            'Low': _numero_pulito(low_s),
            'Last': _numero_pulito(last_s),
            'Change': _numero_pulito(change_s),
            'Settle': _numero_pulito(settle_s),
            'Volume': _numero_pulito(vol_s),
            'OI': _numero_pulito(oi_s),
            'Data_Scarico': pd.to_datetime(trade_date).date() if trade_date else dt.date.today(),
        })

    if not righe:
        raise ValueError(
            "Nessuna riga riconosciuta nella risposta - il formato reale probabilmente "
            "differisce dall'ipotesi usata qui. Usa mostra_diagnostica_grezza() per "
            "salvare la risposta grezza e sistemare il regex."
        )
    return pd.DataFrame(righe)


def mostra_diagnostica_grezza(session, percorso_output="debug_futures_raw.html", expiries=None, trade_date=None):
    """Scarica la risposta grezza e la salva su file, senza tentare il parsing.
    Da usare se fetch_live_html+parse_live_html falliscono: ispezionando questo
    file si può correggere ENDPOINT/_ROW_RE in un colpo solo."""
    html_text = fetch_live_html(session, expiries=expiries, trade_date=trade_date)
    with open(percorso_output, 'w', encoding='utf-8') as f:
        f.write(html_text)
    print(f"Risposta grezza salvata in: {percorso_output} ({len(html_text)} caratteri)")
    print("Anteprima primi 500 caratteri:")
    print(html_text[:500])
    return html_text


def aggiorna_storico_oi(df_oggi, log_path):
    """Aggiunge lo snapshot di oggi allo storico persistente su CSV, senza
    duplicare se rilanciato più volte lo stesso giorno per la stessa scadenza
    (chiave: Data_Scarico + Scadenza). Pensato per sopravvivere anche quando
    Euronext toglie una scadenza scaduta dalla pagina live (es. Set 2026 dopo
    il settlement) - una volta salvata qui, resta.
    """
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    df_oggi = df_oggi.copy()
    df_oggi['Data_Scarico'] = df_oggi['Data_Scarico'].astype(str)
    df_oggi['Scadenza'] = pd.to_datetime(df_oggi['Scadenza']).dt.date.astype(str)

    if os.path.exists(log_path):
        storico = pd.read_csv(log_path)
        storico['Data_Scarico'] = storico['Data_Scarico'].astype(str)
        storico['Scadenza'] = storico['Scadenza'].astype(str)
    else:
        storico = pd.DataFrame(columns=df_oggi.columns)

    chiave = ['Data_Scarico', 'Scadenza']
    esistenti = set(storico[chiave].apply(tuple, axis=1)) if not storico.empty else set()
    nuove = df_oggi[~df_oggi[chiave].apply(tuple, axis=1).isin(esistenti)]

    combinato = pd.concat([storico, nuove], ignore_index=True) if not nuove.empty else storico
    combinato = combinato.sort_values(['Data_Scarico', 'Scadenza']).reset_index(drop=True)
    combinato.to_csv(log_path, index=False)
    return len(nuove), combinato

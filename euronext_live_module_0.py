# File: euronext_live_module.py
#
# Recupera ed elabora i dati LIVE (delayed 15') dalla pagina Settlement Prices
# di Euronext per MIB-DMIL, tramite l'endpoint AJAX che la pagina stessa usa
# (individuato ispezionando il traffico di rete del browser).
#
# A differenza del file copia-incolla (euronext_module.parse_euronext_text),
# qui il formato e' vero HTML, e ogni blocco-scadenza riporta un orario preciso
# ("as of DD Mon YYYY HH:MM CET") diverso da blocco a blocco: viene usato per
# popolare automaticamente la colonna "ora" nel log eventi, senza doverla
# scrivere a mano.
# -----------------------------------------------------------------------------

import re
import datetime as dt
import numpy as np
import pandas as pd
import requests

ENDPOINT = "https://live.euronext.com/en/ajax/getTabPrices/MIB-DMIL/options"
REFERER = "https://live.euronext.com/en/product/index-options/MIB-DMIL/settlement-prices"

# Elenco di riserva delle scadenze note (formato MM-01-YYYY richiesto dall'endpoint).
# Va aggiornato di tanto in tanto man mano che le vecchie scadono e ne aprono di nuove
# (Euronext le elenca nella stessa pagina, sezione "Select Delivery Month(s)").
SCADENZE_NOTE = [
    "08-01-2026", "09-01-2026", "10-01-2026", "12-01-2026", "03-01-2027",
    "06-01-2027", "12-01-2027", "06-01-2028", "12-01-2028", "06-01-2029",
    "12-01-2029", "12-01-2030", "12-01-2031", "12-01-2032",
]

_HEADER_RE = re.compile(
    r'<h3>(\w{3} \d{4}) Prices as of (\d{1,2} \w{3} \d{4}) (\d{2}:\d{2}) CET</h3>'
)
_ROW_RE = re.compile(
    r'<td class="strike[^"]*"><small>([\d.]+)</small></td>\s*'
    r'<td class="type">([CP])</td>\s*'
    r'<td class="open[^"]*">([^<]*)</td>\s*'
    r'<td class="high[^"]*">([^<]*)</td>\s*'
    r'<td class="low[^"]*">([^<]*)</td>\s*'
    r'<td class="last[^"]*">([^<]*)</td>\s*'
    r'<td class="change[^"]*">([^<]*)</td>\s*'
    r'<td class="settle[^"]*">([^<]*)</td>\s*'
    r'<td class="volume[^"]*">([^<]*)</td>\s*'
    r'<td class="interest[^"]*">([^<]*)</td>',
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


def fetch_live_html(session, expiries=None, trade_date=None):
    """
    expiries: lista di stringhe 'MM-01-YYYY' (default: SCADENZE_NOTE, tutte).
    trade_date: stringa 'MM-DD-YYYY' (default: oggi).

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
    resp = session.post(ENDPOINT, data=data, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_live_html(html_text):
    """
    Fa il parsing della risposta HTML AJAX (a blocchi per scadenza, ognuno con
    il proprio orario "as of").

    Returns: df_raw con colonne Strike, Type, Settle, Vol, OI, Expiration Date,
             Ora_Aggiornamento (stringa HH:MM), Data_Aggiornamento (datetime.date)
    """
    headers = list(_HEADER_RE.finditer(html_text))
    if not headers:
        raise ValueError("Nessun blocco scadenza trovato nella risposta (formato inatteso).")

    rows = []
    for i, h in enumerate(headers):
        mon_year_str, date_str, time_str = h.groups()  # es. "Aug 2026", "22 Jul 2026", "17:27"
        mon_abbr, year = mon_year_str.split()
        year = int(year)
        month_num = dt.datetime.strptime(mon_abbr, "%b").month
        update_date = dt.datetime.strptime(date_str, "%d %b %Y").date()

        # Scadenza MIBO standard: terzo venerdi' del mese
        import calendar
        c = calendar.Calendar()
        fridays = [d for d in c.itermonthdates(year, month_num)
                   if d.weekday() == 4 and d.month == month_num]
        expiration_date = pd.Timestamp(fridays[2])

        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(html_text)
        segment = html_text[start:end]

        for m in _ROW_RE.finditer(segment):
            strike_s, typ, _o, _h_, _l, _last, _chg, settle_s, vol_s, oi_s = m.groups()
            try:
                strike = float(strike_s)
                settle = float(settle_s)
                vol = float(vol_s.strip()) if vol_s.strip() not in ('', 'N/A') else 0.0
                oi_s_clean = oi_s.strip()
                oi = float(oi_s_clean) if oi_s_clean not in ('-', '', 'N/A') else np.nan
            except ValueError:
                continue
            rows.append({
                'Strike': strike, 'Type': 'Call' if typ == 'C' else 'Put',
                'Settle': settle, 'Vol': vol, 'OI': oi,
                'Expiration Date': expiration_date,
                'Ora_Aggiornamento': time_str,
                'Data_Aggiornamento': update_date,
            })

    if not rows:
        raise ValueError("Nessuna riga dati estratta (la risposta potrebbe essere vuota o cambiata formato).")

    return pd.DataFrame(rows)


def log_significant_volume_events_live(df_raw, spot_price, contract_multiplier, threshold, log_path):
    """
    Come euronext_module.log_significant_volume_events, ma per i dati ottenuti da
    fetch_live_html/parse_live_html: la data di riferimento e l'ora vengono prese
    automaticamente dal timestamp "as of" di ciascun blocco (niente da scrivere a
    mano), invece di un'unica data per l'intero file come nel copia-incolla.
    """
    import os
    from euronext_module import _LOG_COLS, _default_for_col

    df = df_raw[df_raw['Vol'] > threshold].copy()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if os.path.exists(log_path):
        existing = pd.read_csv(log_path)
        for col in _LOG_COLS:
            if col not in existing.columns:
                existing[col] = _default_for_col(col)
        existing['stato_conferma'] = existing['stato_conferma'].astype(object).fillna('in attesa')
        existing['significativo'] = existing['significativo'].astype(object).where(existing['significativo'].notna(), True)
        existing['ora'] = existing['ora'].astype(object).fillna('')
    else:
        existing = pd.DataFrame(columns=_LOG_COLS)

    if df.empty:
        return 0, 0, existing

    df['data_riferimento'] = df['Data_Aggiornamento'].astype(str)
    df['scadenza'] = df['Expiration Date'].dt.date.astype(str)
    df['notional_stimato_eur'] = df['Vol'] * df['Settle'] * contract_multiplier
    df['spot'] = spot_price
    df['moneyness'] = (df['Strike'] / spot_price) if spot_price else np.nan
    new_rows = df.rename(columns={
        'Strike': 'strike', 'Type': 'tipo', 'Vol': 'volume', 'OI': 'oi', 'Settle': 'settle',
        'Ora_Aggiornamento': 'ora'
    })
    new_rows['stato_conferma'] = 'in attesa'
    new_rows['significativo'] = True
    new_rows['spot_preciso'] = np.nan
    new_rows['oi_giorno_precedente'] = np.nan
    new_rows['delta_oi'] = np.nan
    new_rows = new_rows[_LOG_COLS]

    key_cols = ['data_riferimento', 'scadenza', 'strike', 'tipo']
    new_rows['_key'] = new_rows[key_cols].astype(str).agg('|'.join, axis=1)
    existing['_key'] = existing[key_cols].astype(str).agg('|'.join, axis=1) if not existing.empty else pd.Series([], dtype=str)

    existing_keys = set(existing['_key']) if not existing.empty else set()
    to_add = new_rows[~new_rows['_key'].isin(existing_keys)].drop(columns='_key')

    n_oi_fixed = 0
    if not existing.empty:
        for _, nrow in new_rows[new_rows['_key'].isin(existing_keys)].iterrows():
            mask = existing['_key'] == nrow['_key']
            if existing.loc[mask, 'oi'].isna().any() and not pd.isna(nrow['oi']):
                existing.loc[mask, 'oi'] = nrow['oi']
                n_oi_fixed += 1
    existing = existing.drop(columns='_key', errors='ignore')

    if not to_add.empty or n_oi_fixed > 0:
        combined = pd.concat([existing, to_add], ignore_index=True)
        combined = combined.sort_values(['data_riferimento', 'scadenza', 'strike']).reset_index(drop=True)
        combined.to_csv(log_path, index=False)
    else:
        combined = existing

    return len(to_add), n_oi_fixed, combined

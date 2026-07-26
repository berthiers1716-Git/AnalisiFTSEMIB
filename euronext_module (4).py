# File: euronext_module.py
#
# Modulo per caricare ed elaborare un export FTSEMIB copiato da Euronext (formato a
# blocchi per scadenza, tab-separated), portandolo allo stesso schema dati prodotto
# da data_module.py per la CBOE. Euronext NON fornisce Delta/Gamma/IV: vengono
# derivati qui invertendo Black-Scholes dal prezzo "Settle" di ciascuna opzione.
# -----------------------------------------------------------------------------

import calendar
import numpy as np
import pandas as pd
from scipy.stats import norm as _norm
from scipy.optimize import brentq

MIN_T = 1.0 / 365.25

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}


def third_friday(year, month):
    """Scadenza MIBO standard: terzo venerdi' del mese (specifiche Borsa Italiana)."""
    c = calendar.Calendar()
    fridays = [d for d in c.itermonthdates(year, month)
               if d.weekday() == 4 and d.month == month]
    return pd.Timestamp(fridays[2])


def parse_euronext_text(text):
    """
    Fa il parsing del testo Euronext (copia-incolla dalla pagina delle opzioni,
    tab-separated, a blocchi per scadenza).

    Returns: (df_raw, analysis_date)
      df_raw ha colonne: Strike, Type ('Call'/'Put'), Settle, Vol, OI, Expiration Date
      (TUTTE le scadenze trovate nel testo, nessun filtro).
    """
    lines = text.split('\n')

    blocks = []  # (month_abbr, year, analysis_date, start_idx)
    for i, line in enumerate(lines):
        s = line.strip()
        m = None
        for mon in MONTH_MAP:
            if s.startswith(mon + ' '):
                m = mon
                break
        if m and 'Prices -' in s:
            try:
                left, right = s.split('Prices -')
                mon_abbr, year_s = left.strip().split()
                analysis_date = pd.to_datetime(right.strip())
                blocks.append((mon_abbr, int(year_s), analysis_date, i))
            except Exception:
                continue

    if not blocks:
        raise ValueError("Nessun blocco scadenza trovato (atteso: 'Mon YYYY Prices - ...').")

    analysis_date = blocks[0][2]
    rows = []
    for idx, (mon_abbr, year, _, start_idx) in enumerate(blocks):
        expiration_date = third_friday(year, MONTH_MAP[mon_abbr])
        end_idx = blocks[idx + 1][3] if idx + 1 < len(blocks) else len(lines)
        header_found = False
        for line in lines[start_idx + 1:end_idx]:
            parts = line.split('\t')
            if not header_found:
                if parts and parts[0].strip() == 'Strike':
                    header_found = True
                continue
            if not parts or parts[0].strip() in ('', 'Total'):
                continue
            if len(parts) < 10:
                continue
            try:
                strike = float(parts[0])
                opt_type = 'Call' if parts[1].strip() == 'C' else 'Put'
                settle = float(parts[7])
                vol = float(parts[8])
                oi_raw = parts[9].strip()
                oi = float(oi_raw) if oi_raw not in ('-', '') else np.nan
            except (ValueError, IndexError):
                continue
            rows.append({
                'Strike': strike, 'Type': opt_type, 'Settle': settle,
                'Vol': vol, 'OI': oi, 'Expiration Date': expiration_date
            })

    if not rows:
        raise ValueError("Nessuna riga dati estratta dal testo incollato.")

    return pd.DataFrame(rows), analysis_date


def _bs_price(S, K, T, r, q, sigma, opt_type):
    if sigma <= 0 or T <= 0:
        return max(S - K, 0.0) if opt_type == 'Call' else max(K - S, 0.0)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == 'Call':
        return S * np.exp(-q * T) * _norm.cdf(d1) - K * np.exp(-r * T) * _norm.cdf(d2)
    return K * np.exp(-r * T) * _norm.cdf(-d2) - S * np.exp(-q * T) * _norm.cdf(-d1)


def _implied_vol(price, S, K, T, r, q, opt_type):
    """Ritorna np.nan se il prezzo viola i limiti no-arbitraggio (Settle anomalo)."""
    intrinsic = max(S - K, 0.0) if opt_type == 'Call' else max(K - S, 0.0)
    if price < intrinsic - 1e-6:
        return np.nan
    lo, hi = 1e-4, 5.0
    f_lo = _bs_price(S, K, T, r, q, lo, opt_type) - price
    f_hi = _bs_price(S, K, T, r, q, hi, opt_type) - price
    if f_lo * f_hi > 0:
        return np.nan
    try:
        return brentq(lambda sig: _bs_price(S, K, T, r, q, sig, opt_type) - price, lo, hi, xtol=1e-6)
    except Exception:
        return np.nan


def enrich_with_greeks(df_raw, spot, analysis_date, risk_free_rate, dividend_yield,
                        contract_multiplier):
    """Aggiunge DTE, IV (da Settle via inversione BS), Delta, Gamma, Vanna e le
    esposizioni nozionali (GEX/DEX/VEX). Ritorna anche il conteggio di righe scartate
    per Settle non invertibile (fuori limiti no-arbitraggio)."""
    df = df_raw.copy()
    df['DTE_Days'] = (df['Expiration Date'] - analysis_date).dt.days
    df['DTE_Years'] = df['DTE_Days'] / 365.25
    r, q = risk_free_rate, dividend_yield

    ivs, deltas, gammas, vannas = [], [], [], []
    for row in df.itertuples():
        T = max(row.DTE_Years, MIN_T)
        iv = _implied_vol(row.Settle, spot, row.Strike, T, r, q, row.Type)
        if np.isnan(iv):
            ivs.append(np.nan); deltas.append(np.nan); gammas.append(np.nan); vannas.append(np.nan)
            continue
        d1 = (np.log(spot / row.Strike) + (r - q + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
        d2 = d1 - iv * np.sqrt(T)
        delta = np.exp(-q * T) * _norm.cdf(d1) if row.Type == 'Call' else np.exp(-q * T) * (_norm.cdf(d1) - 1)
        gamma = np.exp(-q * T) * _norm.pdf(d1) / (spot * iv * np.sqrt(T))
        vanna = -_norm.pdf(d1) * d2 / iv
        ivs.append(iv); deltas.append(delta); gammas.append(gamma); vannas.append(vanna)

    df['IV'] = ivs
    df['Delta'] = deltas
    df['Gamma'] = gammas
    df['Vanna'] = vannas
    n_discarded = int(df['IV'].isna().sum())

    df['Delta'] = df['Delta'].fillna(0)
    df['Gamma'] = df['Gamma'].fillna(0)
    df['Vanna'] = df['Vanna'].fillna(0)
    df['Moneyness'] = df['Strike'] / spot

    df['GEX_Notional'] = df['Gamma'] * df['OI'] * contract_multiplier * (spot / 100.0) * spot
    df['GEX_Signed'] = np.where(df['Type'] == 'Call', df['GEX_Notional'], -df['GEX_Notional'])
    df['DEX_Notional'] = df['Delta'] * df['OI'] * contract_multiplier * spot
    df['VEX_Notional'] = df['Vanna'] * df['OI'] * contract_multiplier * spot * 0.01

    return df, n_discarded


# =============================================================================
# LOG PERSISTENTE DI EVENTI VOLUME SIGNIFICATIVI
# =============================================================================
import os
import re

_LOG_COLS = ['data_riferimento', 'scadenza', 'strike', 'tipo', 'volume', 'oi',
             'settle', 'notional_stimato_eur', 'spot', 'moneyness',
             'oi_giorno_precedente', 'delta_oi', 'stato_conferma', 'significativo',
             'ora', 'spot_preciso']

_COL_DEFAULTS = {
    'stato_conferma': 'in attesa',
    'significativo': True,
    'ora': '',
    'spot_preciso': np.nan,
}


def _default_for_col(col):
    return _COL_DEFAULTS.get(col, np.nan)


def log_significant_volume_events(df_raw, analysis_date, spot_price, contract_multiplier,
                                   threshold, log_path):
    """
    Filtra df_raw (TUTTE le scadenze) per Volume > soglia, calcola una stima del
    notional in euro impegnato (utile per gli strike deep ITM su scadenze lunghe, dove
    anche pochi contratti pesano molto piu' del volume grezzo suggerirebbe), ed
    appende gli eventi nuovi a un log CSV persistente su disco.

    Se una riga con la stessa chiave (data+scadenza+strike+tipo) esiste gia' ma con OI
    mancante (es. file caricato la sera prima che l'OI fosse disponibile), e il nuovo
    file la riporta con OI presente, la riga viene AGGIORNATA invece che ignorata.

    Returns: (n_nuovi_eventi, n_oi_completati, df_log_completo)
    """
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

    df['data_riferimento'] = analysis_date.date().isoformat()
    df['scadenza'] = df['Expiration Date'].dt.date.astype(str)
    df['notional_stimato_eur'] = df['Vol'] * df['Settle'] * contract_multiplier
    df['spot'] = spot_price
    df['moneyness'] = (df['Strike'] / spot_price) if spot_price else np.nan
    new_rows = df.rename(columns={
        'Strike': 'strike', 'Type': 'tipo', 'Vol': 'volume', 'OI': 'oi', 'Settle': 'settle'
    })
    for col in ['oi_giorno_precedente', 'delta_oi']:
        new_rows[col] = np.nan
    new_rows['stato_conferma'] = 'in attesa'
    new_rows['significativo'] = True
    new_rows['ora'] = ''
    new_rows['spot_preciso'] = np.nan
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


def _scan_dati_folder(folder):
    """Trova i file CSV con nome YYYYMMDD.csv nella cartella indicata. Ritorna {date: filepath}."""
    files = {}
    if not os.path.isdir(folder):
        return files
    for fname in os.listdir(folder):
        m = re.match(r'^(\d{8})\.csv$', fname)
        if m:
            try:
                d = pd.to_datetime(m.group(1), format='%Y%m%d').date()
                files[d] = os.path.join(folder, fname)
            except Exception:
                continue
    return files


def _oi_lookup_from_file(filepath):
    """Legge un file Euronext dal disco e ritorna {(scadenza, strike, tipo): OI}."""
    with open(filepath, encoding='utf-8-sig') as f:
        text = f.read()
    df, _ = parse_euronext_text(text)
    df['scadenza'] = df['Expiration Date'].dt.date.astype(str)
    lookup = {}
    for row in df.itertuples():
        lookup[(row.scadenza, row.Strike, row.Type)] = row.OI
    return lookup


def reconcile_log(log_path, dati_folder, confirm_ratio=0.30):
    """
    Scansiona dati_folder (file YYYYMMDD.csv) per:
    1) completare l'OI mancante del giorno stesso dell'evento, se ora disponibile;
    2) confrontare l'OI del giorno dell'evento con quella del giorno precedente
       disponibile in cartella, e classificare se il volume e' stato "confermato"
       da un aumento di OI coerente, "non confermato" (OI stabile), o segnala
       una chiusura di posizioni (OI in calo).

    Returns: (n_oi_completati, n_confermati_o_aggiornati, df_log_completo)
    """
    if not os.path.exists(log_path):
        return 0, 0, pd.DataFrame(columns=_LOG_COLS)
    log_df = pd.read_csv(log_path)
    for col in _LOG_COLS:
        if col not in log_df.columns:
            log_df[col] = _default_for_col(col)
    log_df['stato_conferma'] = log_df['stato_conferma'].astype(object).fillna('in attesa')
    log_df['significativo'] = log_df['significativo'].astype(object).where(log_df['significativo'].notna(), True)
    log_df['ora'] = log_df['ora'].astype(object).fillna('')
    if log_df.empty:
        return 0, 0, log_df

    files_by_date = _scan_dati_folder(dati_folder)
    _cache = {}

    def get_lookup(d):
        if d not in _cache:
            _cache[d] = _oi_lookup_from_file(files_by_date[d]) if d in files_by_date else None
        return _cache[d]

    n_oi_filled = 0
    n_confirmed = 0
    for idx, row in log_df.iterrows():
        event_date = pd.to_datetime(row['data_riferimento']).date()
        key = (row['scadenza'], row['strike'], row['tipo'])

        if pd.isna(row['oi']):
            same_day = get_lookup(event_date)
            if same_day is not None and key in same_day and not pd.isna(same_day[key]):
                log_df.at[idx, 'oi'] = same_day[key]
                n_oi_filled += 1

        _stato_attuale = row.get('stato_conferma')
        needs_confirm = pd.isna(_stato_attuale) or str(_stato_attuale).startswith('in attesa')
        if needs_confirm:
            prev_dates = sorted([d for d in files_by_date if d < event_date], reverse=True)
            if prev_dates:
                prev_lookup = get_lookup(prev_dates[0])
                oi_event = log_df.at[idx, 'oi']
                if prev_lookup is not None and key in prev_lookup and not pd.isna(prev_lookup[key]) and not pd.isna(oi_event):
                    oi_prev = prev_lookup[key]
                    delta = oi_event - oi_prev
                    vol = row['volume'] if row['volume'] else 0
                    ratio = (delta / vol) if vol else 0
                    if ratio >= confirm_ratio:
                        stato = 'Confermato (OI in aumento)'
                    elif ratio <= -confirm_ratio:
                        stato = 'Chiusura posizioni (OI in calo)'
                    else:
                        stato = 'Non confermato (OI stabile)'
                    log_df.at[idx, 'oi_giorno_precedente'] = oi_prev
                    log_df.at[idx, 'delta_oi'] = delta
                    log_df.at[idx, 'stato_conferma'] = stato
                    n_confirmed += 1
                else:
                    log_df.at[idx, 'stato_conferma'] = 'in attesa (nessun file precedente in cartella)'
            else:
                log_df.at[idx, 'stato_conferma'] = 'in attesa (nessun file precedente in cartella)'

    log_df.to_csv(log_path, index=False)
    return n_oi_filled, n_confirmed, log_df


def update_log_fields(log_path, edited_subset, editable_cols=('significativo', 'ora', 'spot_preciso')):
    """
    Aggiorna le colonne indicate (es. 'significativo', 'ora', 'spot_preciso') nel log
    su disco, in base a un sottoinsieme modificato (es. quello mostrato/editato
    nell'interfaccia, anche se filtrato per data o stato). Il merge avviene per
    chiave (data_riferimento, scadenza, strike, tipo), cosi' le righe filtrate/nascoste
    nella vista non vengono perse.

    Returns: (n_righe_modificate, df_log_completo_aggiornato)
    """
    if not os.path.exists(log_path):
        return 0, pd.DataFrame(columns=_LOG_COLS)
    log_df = pd.read_csv(log_path)
    for col in _LOG_COLS:
        if col not in log_df.columns:
            log_df[col] = _default_for_col(col)
    log_df['significativo'] = log_df['significativo'].astype(object).where(log_df['significativo'].notna(), True)
    log_df['ora'] = log_df['ora'].astype(object).fillna('')

    key_cols = ['data_riferimento', 'scadenza', 'strike', 'tipo']
    log_df['_key'] = log_df[key_cols].astype(str).agg('|'.join, axis=1)
    edited = edited_subset.copy()
    edited['_key'] = edited[key_cols].astype(str).agg('|'.join, axis=1)
    edited_by_key = edited.set_index('_key')

    n_changed = 0
    for idx, row in log_df.iterrows():
        k = row['_key']
        if k not in edited_by_key.index:
            continue
        erow = edited_by_key.loc[k]
        row_changed = False
        for col in editable_cols:
            if col not in erow.index:
                continue
            new_val, old_val = erow[col], row[col]
            both_nan = (pd.isna(new_val) if not isinstance(new_val, bool) else False) and \
                       (pd.isna(old_val) if not isinstance(old_val, bool) else False)
            if both_nan or new_val == old_val:
                continue
            log_df.at[idx, col] = new_val
            row_changed = True
        if row_changed:
            n_changed += 1

    log_df = log_df.drop(columns='_key')
    if n_changed > 0:
        log_df.to_csv(log_path, index=False)
    return n_changed, log_df

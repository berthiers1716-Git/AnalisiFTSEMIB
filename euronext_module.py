# File: euronext_module.py
#
# Modulo per caricare ed elaborare un export FTSEMIB copiato da Euronext (formato a
# blocchi per scadenza, tab-separated), portandolo allo stesso schema dati prodotto
# da data_module.py per la CBOE. Euronext NON fornisce Delta/Gamma/IV: vengono
# derivati qui invertendo Black-Scholes dal prezzo "Settle" di ciascuna opzione.
# -----------------------------------------------------------------------------

import calendar
import datetime as dt
import numpy as np
import pandas as pd
from scipy.stats import norm as _norm
from scipy.optimize import brentq

from calculations_module import calculate_max_pain, calculate_pc_ratios, calculate_expected_move

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
             'ora', 'spot_preciso', 'nota']

_COL_DEFAULTS = {
    'stato_conferma': 'in attesa',
    'significativo': True,
    'ora': '',
    'spot_preciso': np.nan,
    'nota': '',
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
        existing['nota'] = existing['nota'].astype(object).fillna('')
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
    new_rows['nota'] = ''
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
    log_df['nota'] = log_df['nota'].astype(object).fillna('')
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
    log_df['nota'] = log_df['nota'].astype(object).fillna('')

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


# =============================================================================
# STORICO TOTALI GIORNALIERI (Volume e OI aggregati su TUTTE le scadenze)
# =============================================================================
def log_totali_giornalieri(df_raw, analysis_date, log_path, spot=None):
    """
    Calcola il Volume totale e l'Open Interest totale (somma su TUTTE le
    scadenze presenti nel file, non solo quella selezionata nell'app) e li
    aggiunge/aggiorna in un log storico CSV (una riga per data), utile per
    seguire nel tempo se il mercato nel complesso si muove o resta laterale -
    e se questo e' correlato con il movimento dello spot (se fornito).

    Se la data e' gia' presente nel log, la riga viene aggiornata (non
    duplicata) - utile se ricarichi lo stesso giorno con dati piu' completi.
    Se spot=None e la data esisteva gia' con uno spot registrato, quel valore
    viene mantenuto invece di essere cancellato.

    Returns: df_storico_completo (ordinato per data)
    """
    data_str = analysis_date.date().isoformat()
    volume_totale = df_raw['Vol'].sum()
    oi_totale = df_raw['OI'].sum(skipna=True)  # NaN ignorati, non trattati come 0

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cols = ['data', 'volume_totale', 'oi_totale', 'spot']
    if os.path.exists(log_path):
        storico = pd.read_csv(log_path)
        for col in cols:
            if col not in storico.columns:
                storico[col] = np.nan
    else:
        storico = pd.DataFrame(columns=cols)

    riga_precedente = storico[storico['data'] == data_str]
    if spot is None and not riga_precedente.empty:
        spot = riga_precedente.iloc[0]['spot']  # mantiene lo spot gia' noto se non ne arriva uno nuovo

    storico = storico[storico['data'] != data_str]  # rimuove eventuale riga vecchia della stessa data
    nuova_riga = pd.DataFrame([{'data': data_str, 'volume_totale': volume_totale, 'oi_totale': oi_totale, 'spot': spot}])
    storico = pd.concat([storico, nuova_riga], ignore_index=True)
    storico = storico.sort_values('data').reset_index(drop=True)
    storico.to_csv(log_path, index=False)

    return storico


def ricostruisci_storico_totali(dati_folder, log_path, percorso_prezzi=None):
    """
    Scansiona TUTTI i file YYYYMMDD.csv nella cartella dati_folder (indipendentemente
    da come sono arrivati li' - copia-incolla manuale, script di recupero, riparazione)
    e ricostruisce da zero lo storico_totali.csv con Volume/OI totali per ciascuna
    data trovata. Se percorso_prezzi e' fornito, recupera anche lo spot per ciascuna
    data dal CSV storico prezzi.

    A differenza di log_totali_giornalieri (che aggiorna una riga alla volta ad ogni
    upload), questa funzione ricostruisce l'INTERO log in un colpo solo: e' il modo
    per allinearlo con tutti i file gia' presenti sul disco, non solo quelli caricati
    manualmente nell'app.

    Returns: (n_giorni_processati, df_storico_completo)
    """
    files_by_date = _scan_dati_folder(dati_folder)
    if not files_by_date:
        return 0, pd.DataFrame(columns=['data', 'volume_totale', 'oi_totale', 'spot'])

    spot_by_date = {}
    if percorso_prezzi and os.path.exists(percorso_prezzi):
        df_prezzi = pd.read_csv(percorso_prezzi, parse_dates=['time'])
        spot_by_date = dict(zip(df_prezzi['time'].dt.date, df_prezzi['close']))

    righe = []
    for data, filepath in sorted(files_by_date.items()):
        try:
            with open(filepath, encoding='utf-8-sig') as f:
                df_raw, _ = parse_euronext_text(f.read())
        except Exception:
            continue
        righe.append({
            'data': data.isoformat(),
            'volume_totale': df_raw['Vol'].sum(),
            'oi_totale': df_raw['OI'].sum(skipna=True),
            'spot': spot_by_date.get(data, np.nan),
        })

    storico = pd.DataFrame(righe).sort_values('data').reset_index(drop=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    storico.to_csv(log_path, index=False)
    return len(storico), storico


# =============================================================================
# DIARIO NOTE LIBERE (osservazioni non legate a un singolo evento/riga)
# =============================================================================
_NOTE_COLS = ['id', 'data_ora', 'contesto', 'nota']


def aggiungi_nota_diario(log_path, contesto, testo):
    """Aggiunge una nuova nota libera al diario, con timestamp automatico."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if os.path.exists(log_path):
        note = pd.read_csv(log_path)
    else:
        note = pd.DataFrame(columns=_NOTE_COLS)

    nuovo_id = int(note['id'].max()) + 1 if not note.empty else 1
    nuova = pd.DataFrame([{
        'id': nuovo_id,
        'data_ora': dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'contesto': contesto or '',
        'nota': testo,
    }])
    note = pd.concat([note, nuova], ignore_index=True)
    note.to_csv(log_path, index=False)
    return note


def _load_spot_history(storico_totali_path, index_prices_path=None):
    """
    Costruisce {date: spot} unendo due fonti, con priorita' alla prima:
    1) dati_locali/storico_totali.csv - spot inserito/registrato in-app per quella data
       (piu' preciso quando disponibile, es. spot_preciso verificato a mano altrove).
    2) CSV storico prezzi indice (es. INDEX_FTSEMIB_1D.csv) - copre anche le date in
       cui storico_totali.csv non e' stato popolato (es. mai ricostruito, o file
       arrivato in dati/ tramite ripara_file_dati.py/recupera_storico.py).
    Ritorna dict vuoto per le fonti mancanti, mai solleva eccezioni.
    """
    spot_by_date = {}
    if storico_totali_path and os.path.exists(storico_totali_path):
        try:
            df_s = pd.read_csv(storico_totali_path)
            for _, row in df_s.iterrows():
                try:
                    d = pd.to_datetime(row['data']).date()
                    if pd.notna(row.get('spot')):
                        spot_by_date[d] = float(row['spot'])
                except Exception:
                    continue
        except Exception:
            pass
    if index_prices_path and os.path.exists(index_prices_path):
        try:
            df_p = pd.read_csv(index_prices_path, parse_dates=['time'])
            for _, row in df_p.iterrows():
                d = row['time'].date()
                if d not in spot_by_date:
                    spot_by_date[d] = float(row['close'])
        except Exception:
            pass
    return spot_by_date


def estimate_iv_multi_day_batch(oggi_date, iv_oggi_map, dati_folder, storico_totali_path,
                                 expiration_date, strikes, risk_free_rate, dividend_yield,
                                 index_prices_path=None, n_giorni=5, min_validi=3):
    """
    Versione "tabellare" della stima IV robusta: calcola la mediana su piu' giorni per
    TUTTI gli strike/tipo richiesti in un solo passaggio sui file storici (ogni file
    in dati_folder viene aperto e parsato una sola volta, non una volta per strike -
    utile per costruire una tabella di riepilogo su un'intera scadenza senza dover
    riaprire gli stessi file decine di volte).

    iv_oggi_map: dict {(strike, opt_type): iv_oggi_o_None} - IV di oggi gia' derivata
    altrove (es. da df_selected_expiry enriched), una voce per ciascuna coppia
    strike/tipo di interesse.
    strikes: iterable degli strike da considerare (serve solo a limitare il parsing
    dei file storici alle righe utili; le coppie effettive vengono da iv_oggi_map).

    Motivazione: il Settle di un singolo giorno puo' essere anomalo (fuori dai limiti
    di no-arbitraggio, quindi IV non invertibile quel giorno specifico) senza che lo
    strike sia davvero illiquido - guardare piu' giorni e prendere la MEDIANA delle IV
    valide e' piu' robusto del solo dato odierno.

    Returns: dict {(strike, opt_type): {iv_mediana, n_validi, n_esaminati, dettaglio,
    min_validi_richiesti}} - stessa struttura per ciascuna coppia presente in
    iv_oggi_map. dettaglio e' una lista di (date, iv_o_None) dal piu' recente al piu'
    vecchio.
    """
    candidati = {
        key: [(oggi_date, iv if (iv is not None and not pd.isna(iv)) else None)]
        for key, iv in iv_oggi_map.items()
    }

    files_by_date = _scan_dati_folder(dati_folder)
    spot_by_date = _load_spot_history(storico_totali_path, index_prices_path)
    prior_dates = sorted([d for d in files_by_date if d < oggi_date], reverse=True)
    strikes_set = set(strikes)

    giorni_usati = 1  # oggi e' gia' stato aggiunto sopra
    for d in prior_dates:
        if giorni_usati >= n_giorni:
            break
        try:
            with open(files_by_date[d], encoding='utf-8-sig') as f:
                df_day, _ = parse_euronext_text(f.read())
        except Exception:
            for key in candidati:
                candidati[key].append((d, None))
            giorni_usati += 1
            continue

        df_day = df_day[(df_day['Expiration Date'] == expiration_date) &
                         (df_day['Strike'].isin(strikes_set))]
        lookup_settle = {(row.Strike, row.Type): row.Settle for row in df_day.itertuples()}
        spot_d = spot_by_date.get(d)

        for key in candidati:
            strike, opt_type = key
            settle_d = lookup_settle.get((strike, opt_type))
            if settle_d is None or pd.isna(settle_d) or spot_d is None or pd.isna(spot_d):
                candidati[key].append((d, None))
                continue
            T = max((pd.Timestamp(expiration_date) - pd.Timestamp(d)).days / 365.25, MIN_T)
            iv_d = _implied_vol(settle_d, spot_d, strike, T, risk_free_rate, dividend_yield, opt_type)
            candidati[key].append((d, None if pd.isna(iv_d) else iv_d))

        giorni_usati += 1

    risultati = {}
    for key, lista in candidati.items():
        validi = [iv for _, iv in lista if iv is not None]
        iv_mediana = float(np.median(validi)) if len(validi) >= min_validi else None
        risultati[key] = {
            'iv_mediana': iv_mediana,
            'n_validi': len(validi),
            'n_esaminati': len(lista),
            'dettaglio': lista,
            'min_validi_richiesti': min_validi,
        }
    return risultati


def elimina_nota_diario(log_path, id_nota):
    """Rimuove una nota dal diario in base al suo id."""
    if not os.path.exists(log_path):
        return pd.DataFrame(columns=_NOTE_COLS)
    note = pd.read_csv(log_path)
    note = note[note['id'] != id_nota]
    note.to_csv(log_path, index=False)
    return note


def modifica_nota_diario(log_path, id_nota, nuovo_testo, nuovo_contesto=None):
    """
    Aggiorna il testo (ed eventualmente il contesto) di una nota esistente,
    aggiornando anche data_ora all'istante della modifica - cosi' se tieni
    una sola nota al giorno e la aggiorni più volte, resta chiaro quando
    e' stata toccata l'ultima volta.
    """
    if not os.path.exists(log_path):
        return pd.DataFrame(columns=_NOTE_COLS)
    note = pd.read_csv(log_path)
    note['contesto'] = note['contesto'].astype(object).fillna('')
    mask = note['id'] == id_nota
    if mask.any():
        note.loc[mask, 'nota'] = nuovo_testo
        if nuovo_contesto is not None:
            note.loc[mask, 'contesto'] = nuovo_contesto
        note.loc[mask, 'data_ora'] = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    note.to_csv(log_path, index=False)
    return note


# =============================================================================
# STORICO PERSISTENTE STATS (Max Pain, P/C Ratio, Expected Move) PER SCADENZA
# =============================================================================
_STATS_LOG_COLS = [
    'data', 'scadenza', 'spot', 'max_pain_strike', 'pc_oi_ratio', 'pc_vol_ratio',
    'call_volume_tot', 'put_volume_tot', 'expected_move', 'upper_band', 'lower_band',
    'iv_atm', 'dte_giorni', 'risk_free_rate_usato', 'dividend_yield_usato', 'fonte'
]


def _calcola_riga_stats(df_expiry_oi, spot, analysis_date, expiration_date,
                         risk_free_rate, dividend_yield, contract_multiplier=2.5):
    """
    Calcola una singola riga di storico Stats per una scadenza/data, riusando le
    stesse funzioni di calculations_module usate live nel tab Stats. Richiede
    df_expiry_oi gia' filtrato per la scadenza e per OI>0 (coerente con quanto
    fatto nel resto dell'app per Max Pain/P-C Ratio).
    """
    df_enr, _ = enrich_with_greeks(df_expiry_oi, spot, pd.Timestamp(analysis_date),
                                    risk_free_rate, dividend_yield, contract_multiplier)
    max_pain_strike, _ = calculate_max_pain(df_enr)
    pc = calculate_pc_ratios(df_enr)
    em = calculate_expected_move(df_enr, spot)
    dte_giorni = int((pd.Timestamp(expiration_date) - pd.Timestamp(analysis_date)).days)
    call_volume_tot = df_enr.loc[df_enr['Type'] == 'Call', 'Vol'].sum()
    put_volume_tot = df_enr.loc[df_enr['Type'] == 'Put', 'Vol'].sum()
    return {
        'spot': spot,
        'max_pain_strike': max_pain_strike,
        'pc_oi_ratio': pc['pc_oi_ratio'],
        'pc_vol_ratio': pc['pc_vol_ratio'],
        'call_volume_tot': call_volume_tot,
        'put_volume_tot': put_volume_tot,
        'expected_move': em['move'],
        'upper_band': em['upper_band'],
        'lower_band': em['lower_band'],
        'iv_atm': em['iv_atm'],
        'dte_giorni': dte_giorni,
    }


def _carica_log_stats(log_path):
    if os.path.exists(log_path):
        log_df = pd.read_csv(log_path)
        for col in _STATS_LOG_COLS:
            if col not in log_df.columns:
                log_df[col] = np.nan
        return log_df
    return pd.DataFrame(columns=_STATS_LOG_COLS)


def ricostruisci_storico_stats(log_path, dati_folder, storico_totali_path, expiration_date,
                                risk_free_rate, dividend_yield, contract_multiplier=2.5,
                                index_prices_path=None, force_full=False):
    """
    Scansiona dati_folder per TUTTE le date in cui la scadenza indicata e' presente
    con OI>0, e calcola/salva Max Pain, P/C Ratio ed Expected Move per ciascuna,
    usando spot storico (storico_totali.csv, con fallback su index_prices_path) e
    risk_free_rate/dividend_yield ATTUALI (approssimazione: quelli in vigore oggi,
    non quelli storici del giorno - stessa semplificazione gia' usata nel tab
    Decadimento).

    Se force_full=False (default): salta le date gia' presenti nel log per questa
    scadenza (i dati settled di un giorno passato non cambiano piu', quindi non ha
    senso ricalcolarli ogni volta). Se force_full=True: ricalcola tutto da zero per
    questa scadenza, sovrascrivendo il log esistente per queste date.

    Non tocca l'eventuale riga di "oggi": quella va aggiornata con
    aggiorna_riga_oggi_stats(), che riusa i valori gia' calcolati live nel tab
    Stats invece di ricalcolarli qui (piu' efficiente e coerente con quanto
    l'utente vede a schermo).

    Returns: (n_giorni_aggiunti, df_log_completo_per_questa_scadenza)
    """
    scadenza_str = pd.Timestamp(expiration_date).date().isoformat()
    log_df = _carica_log_stats(log_path)

    esistenti = set()
    if not force_full and not log_df.empty:
        _mask_scad = log_df['scadenza'].astype(str) == scadenza_str
        esistenti = set(log_df.loc[_mask_scad, 'data'].astype(str))

    files_by_date = _scan_dati_folder(dati_folder)
    spot_by_date = _load_spot_history(storico_totali_path, index_prices_path)

    nuove_righe = []
    for d, filepath in sorted(files_by_date.items()):
        data_str = d.isoformat()
        if data_str in esistenti:
            continue
        spot_d = spot_by_date.get(d)
        if spot_d is None or pd.isna(spot_d):
            continue
        try:
            with open(filepath, encoding='utf-8-sig') as f:
                df_day, _ = parse_euronext_text(f.read())
        except Exception:
            continue
        df_expiry_oi = df_day[(df_day['Expiration Date'] == expiration_date) & (df_day['OI'] > 0)].copy()
        if df_expiry_oi.empty:
            continue
        try:
            riga = _calcola_riga_stats(df_expiry_oi, spot_d, d, expiration_date,
                                        risk_free_rate, dividend_yield, contract_multiplier)
        except Exception:
            continue
        riga.update({
            'data': data_str, 'scadenza': scadenza_str,
            'risk_free_rate_usato': risk_free_rate, 'dividend_yield_usato': dividend_yield,
            'fonte': 'ricostruito da dati/',
        })
        nuove_righe.append(riga)

    if nuove_righe:
        if force_full and not log_df.empty:
            log_df = log_df[log_df['scadenza'].astype(str) != scadenza_str]
        log_df = pd.concat([log_df, pd.DataFrame(nuove_righe)], ignore_index=True)
        log_df = log_df.sort_values(['scadenza', 'data']).reset_index(drop=True)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_df.to_csv(log_path, index=False)

    df_scadenza = log_df[log_df['scadenza'].astype(str) == scadenza_str].sort_values('data').reset_index(drop=True)
    return len(nuove_righe), df_scadenza


def aggiorna_riga_oggi_stats(log_path, expiration_date, analysis_date, spot, max_pain_strike,
                              pc_ratios, expected_move, dte_giorni, risk_free_rate, dividend_yield,
                              call_volume_tot=None, put_volume_tot=None):
    """
    Aggiorna (o crea) la riga di "oggi" nello storico Stats per questa scadenza,
    riusando i valori GIA' calcolati live nel tab Stats (non li ricalcola) - cosi'
    lo storico riflette esattamente cio' che l'utente vede a schermo oggi, coi
    parametri di mercato (risk-free/dividend) effettivamente in vigore oggi.

    Se la riga per (scadenza, oggi) esiste gia', viene sovrascritta (non
    duplicata) - utile se ricarichi lo stesso giorno con dati piu' completi
    (es. OI arrivato dopo un caricamento intraday).

    Returns: df_log_completo_per_questa_scadenza
    """
    scadenza_str = pd.Timestamp(expiration_date).date().isoformat()
    data_str = pd.Timestamp(analysis_date).date().isoformat()
    log_df = _carica_log_stats(log_path)

    log_df = log_df[~((log_df['scadenza'].astype(str) == scadenza_str) & (log_df['data'].astype(str) == data_str))]
    nuova_riga = pd.DataFrame([{
        'data': data_str, 'scadenza': scadenza_str, 'spot': spot,
        'max_pain_strike': max_pain_strike,
        'pc_oi_ratio': pc_ratios['pc_oi_ratio'], 'pc_vol_ratio': pc_ratios['pc_vol_ratio'],
        'call_volume_tot': call_volume_tot, 'put_volume_tot': put_volume_tot,
        'expected_move': expected_move['move'], 'upper_band': expected_move['upper_band'],
        'lower_band': expected_move['lower_band'], 'iv_atm': expected_move['iv_atm'],
        'dte_giorni': dte_giorni,
        'risk_free_rate_usato': risk_free_rate, 'dividend_yield_usato': dividend_yield,
        'fonte': 'oggi (live)',
    }])
    log_df = pd.concat([log_df, nuova_riga], ignore_index=True)
    log_df = log_df.sort_values(['scadenza', 'data']).reset_index(drop=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_df.to_csv(log_path, index=False)

    df_scadenza = log_df[log_df['scadenza'].astype(str) == scadenza_str].sort_values('data').reset_index(drop=True)
    return df_scadenza

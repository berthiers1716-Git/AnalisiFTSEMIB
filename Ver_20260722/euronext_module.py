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


def log_significant_volume_events(df_raw, analysis_date, spot_price, contract_multiplier,
                                   threshold, log_path):
    """
    Filtra df_raw (TUTTE le scadenze) per Volume > soglia, calcola una stima del
    notional in euro impegnato (utile per gli strike deep ITM su scadenze lunghe, dove
    anche pochi contratti pesano molto piu' del volume grezzo suggerirebbe), ed
    appende gli eventi nuovi a un log CSV persistente su disco (evitando duplicati
    su data+scadenza+strike+tipo).

    Returns: (n_nuovi_eventi, df_log_completo)
    """
    df = df_raw[df_raw['Vol'] > threshold].copy()
    cols = ['data_riferimento', 'scadenza', 'strike', 'tipo', 'volume', 'oi',
            'settle', 'notional_stimato_eur', 'spot', 'moneyness']

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if os.path.exists(log_path):
        existing = pd.read_csv(log_path)
    else:
        existing = pd.DataFrame(columns=cols)

    if df.empty:
        return 0, existing

    df['data_riferimento'] = analysis_date.date().isoformat()
    df['scadenza'] = df['Expiration Date'].dt.date.astype(str)
    df['notional_stimato_eur'] = df['Vol'] * df['Settle'] * contract_multiplier
    df['spot'] = spot_price
    df['moneyness'] = (df['Strike'] / spot_price) if spot_price else np.nan
    new_rows = df.rename(columns={
        'Strike': 'strike', 'Type': 'tipo', 'Vol': 'volume', 'OI': 'oi', 'Settle': 'settle'
    })[cols]

    key_cols = ['data_riferimento', 'scadenza', 'strike', 'tipo']
    if not existing.empty:
        existing_keys = set(existing[key_cols].astype(str).agg('|'.join, axis=1))
    else:
        existing_keys = set()
    new_keys = new_rows[key_cols].astype(str).agg('|'.join, axis=1)
    to_add = new_rows[~new_keys.isin(existing_keys)]

    if not to_add.empty:
        combined = pd.concat([existing, to_add], ignore_index=True)
        combined = combined.sort_values(['data_riferimento', 'scadenza', 'strike']).reset_index(drop=True)
        combined.to_csv(log_path, index=False)
    else:
        combined = existing

    return len(to_add), combined

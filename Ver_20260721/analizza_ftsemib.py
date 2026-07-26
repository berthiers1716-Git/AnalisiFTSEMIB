# File: analizza_ftsemib.py
#
# Adatta un export FTSEMIB copiato da Euronext (formato a blocchi per scadenza,
# incollato nell'editor Jupyter) alle stesse metriche calcolate da calculations_module.py
# per la CBOE (GEX, DEX, VEX, Max Pain, Walls, Expected Move, Drift).
#
# Euronext NON fornisce Delta/Gamma/IV pronti (a differenza di CBOE): vengono derivati
# qui invertendo Black-Scholes dal prezzo "Settle" di ciascuna opzione.
#
# NOTA (dall'utente): il Settle usato da Euronext puo' occasionalmente essere anomalo
# su singoli strike (soprattutto poco liquidi); lo script scarta automaticamente i
# prezzi che violano i limiti no-arbitraggio (IV non calcolabile -> riga esclusa dai
# calcoli che richiedono IV/Delta/Gamma, ma resta nei calcoli basati solo su OI/Volume).
# -----------------------------------------------------------------------------

import sys
import calendar
import datetime as dt
import numpy as np
import pandas as pd
from scipy.stats import norm as _norm
from scipy.optimize import brentq

sys.path.insert(0, ".")
import calculations_module as calc
import visualization_module as viz

# =============================================================================
# PARAMETRI DI MERCATO (FTSEMIB / MIBO, non i default CBOE/SPX dell'app originale)
# =============================================================================
CONTRACT_MULTIPLIER = 2.5      # € per punto indice (MIBO), non 100 come SPX
RISK_FREE_RATE = 0.0225        # tasso BCE sui depositi in vigore dal 17/6/2026
DIVIDEND_YIELD = 0.042         # stima dividend yield FTSEMIB 2026 (~4.2%)
MIN_T = 1.0 / 365.25


# =============================================================================
# 1. PARSING DEL FILE EURONEXT (formato copia-incolla, a blocchi per scadenza)
# =============================================================================
MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}


def _third_friday(year, month):
    """Scadenza MIBO standard: terzo venerdi' del mese (da specifiche Borsa Italiana)."""
    c = calendar.Calendar()
    fridays = [d for d in c.itermonthdates(year, month)
               if d.weekday() == 4 and d.month == month]
    return pd.Timestamp(fridays[2])


def parse_euronext_file(path, wanted_months=None):
    """
    wanted_months: lista di tuple (mese_abbr, anno), es. [('Jul', 2026), ('Aug', 2026)].
    Se None, include tutti i blocchi trovati.

    Returns: (df_raw, analysis_date)
      df_raw ha colonne: Strike, Type ('Call'/'Put'), Settle, Vol, OI, Expiration Date
    """
    with open(path, encoding='utf-8-sig') as f:
        lines = f.read().split('\n')

    blocks = []  # (month_abbr, year, analysis_date, start_idx)
    for i, line in enumerate(lines):
        s = line.strip()
        m = None
        for mon in MONTH_MAP:
            if s.startswith(mon + ' '):
                m = mon
                break
        if m and 'Prices -' in s:
            # es. "Jul 2026 Prices - 9 July 2026"
            try:
                left, right = s.split('Prices -')
                mon_abbr, year_s = left.strip().split()
                analysis_date = pd.to_datetime(right.strip())
                blocks.append((mon_abbr, int(year_s), analysis_date, i))
            except Exception:
                continue

    if not blocks:
        raise ValueError("Nessun blocco scadenza trovato nel file (atteso: 'Mon YYYY Prices - ...').")

    analysis_date = blocks[0][2]  # stessa data per tutti i blocchi in un export giornaliero
    rows = []
    for idx, (mon_abbr, year, _, start_idx) in enumerate(blocks):
        if wanted_months and (mon_abbr, year) not in wanted_months:
            continue
        expiration_date = _third_friday(year, MONTH_MAP[mon_abbr])

        # La tabella del blocco inizia 2 righe dopo l'intestazione "Mon YYYY Prices - ..."
        # (riga vuota/di colonne poi dati), termina alla riga "Total" o al blocco successivo.
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
        raise ValueError("Nessuna riga dati estratta per le scadenze richieste.")

    df_raw = pd.DataFrame(rows)
    return df_raw, analysis_date


# =============================================================================
# 2. BLACK-SCHOLES: prezzo, inversione IV, Delta/Gamma/Vanna
# =============================================================================
def _bs_price(S, K, T, r, q, sigma, opt_type):
    if sigma <= 0 or T <= 0:
        intrinsic = max(S - K, 0.0) if opt_type == 'Call' else max(K - S, 0.0)
        return intrinsic
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt_type == 'Call':
        return S * np.exp(-q * T) * _norm.cdf(d1) - K * np.exp(-r * T) * _norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * _norm.cdf(-d2) - S * np.exp(-q * T) * _norm.cdf(-d1)


def _implied_vol(price, S, K, T, r, q, opt_type):
    """Inverte Black-Scholes con brentq. Ritorna np.nan se il prezzo viola i limiti
    no-arbitraggio (fuori range spiegabile con qualunque sigma valida): tipicamente
    un Settle anomalo, come segnalato dall'utente per certi strike poco liquidi."""
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


def enrich_with_greeks(df_raw, spot, analysis_date, r=RISK_FREE_RATE, q=DIVIDEND_YIELD):
    """Aggiunge DTE, IV (da Settle via inversione BS), Delta, Gamma, Vanna e le
    esposizioni nozionali (GEX/DEX/VEX), con lo stesso schema di data_module.py
    ma moltiplicatore MIBO (€2.5) al posto di 100."""
    df = df_raw.copy()
    df['DTE_Days'] = (df['Expiration Date'] - analysis_date).dt.days
    df['DTE_Years'] = df['DTE_Days'] / 365.25

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

    n_bad = df['IV'].isna().sum()
    if n_bad > 0:
        print(f"[Attenzione] {n_bad}/{len(df)} righe con Settle non invertibile (fuori limiti "
              f"no-arbitraggio) sono state escluse da IV/Delta/Gamma/Vanna.")

    df['Delta'] = df['Delta'].fillna(0)
    df['Gamma'] = df['Gamma'].fillna(0)
    df['Vanna'] = df['Vanna'].fillna(0)
    df['Moneyness'] = df['Strike'] / spot

    df['GEX_Notional'] = df['Gamma'] * df['OI'] * CONTRACT_MULTIPLIER * (spot / 100.0) * spot
    df['GEX_Signed'] = np.where(df['Type'] == 'Call', df['GEX_Notional'], -df['GEX_Notional'])
    df['DEX_Notional'] = df['Delta'] * df['OI'] * CONTRACT_MULTIPLIER * spot
    df['VEX_Notional'] = df['Vanna'] * df['OI'] * CONTRACT_MULTIPLIER * spot * 0.01

    return df


# =============================================================================
# 3. REPORT PER SCADENZA (metriche + grafici salvati come HTML)
# =============================================================================
def analizza_scadenza(df_expiry, spot, expiry_label, output_dir):
    df_oi = df_expiry[df_expiry['OI'] > 0].copy()
    if df_oi.empty:
        print(f"\n=== {expiry_label}: nessun Open Interest, scadenza saltata ===")
        return

    gex = calc.calculate_gex_metrics(df_oi, spot, RISK_FREE_RATE, DIVIDEND_YIELD)
    walls = calc.calculate_oi_walls(df_oi, spot)
    max_pain_strike, df_payouts = calc.calculate_max_pain(df_oi)
    pc = calc.calculate_pc_ratios(df_oi)
    move = calc.calculate_expected_move(df_oi, spot)
    vol_profile = calc.calculate_volume_profile(df_expiry, spot)
    activity = calc.calculate_activity_ratio(df_expiry, spot)
    dex = calc.calculate_dex_metrics(df_oi, spot)
    vex = calc.calculate_vex_metrics(df_oi, spot, RISK_FREE_RATE, DIVIDEND_YIELD)

    print(f"\n=== {expiry_label} (spot {spot:,.2f}) ===")
    print(f"  Max Pain:          {max_pain_strike:,.0f}")
    print(f"  Put Wall:          {walls['put_wall_strike']}  (OI {walls['put_wall_oi']:,.0f})")
    print(f"  Call Wall:         {walls['call_wall_strike']}  (OI {walls['call_wall_oi']:,.0f})")
    print(f"  Put/Call Ratio OI: {pc['pc_oi_ratio']:.2f}   Volume: {pc['pc_vol_ratio']:.2f}")
    print(f"  Net GEX totale:    {gex['total_net_gex']:,.0f}")
    print(f"  Gamma Flip:        {gex['gamma_switch_point']}")
    print(f"  Net DEX totale:    {dex['total_net_dex']:,.0f}")
    print(f"  Net VEX totale:    {vex['total_net_vex']:,.0f}   Vanna Flip: {vex['vanna_switch_point']}")
    if move['move'] is not None:
        print(f"  Expected Move:     +/- {move['move']:,.0f}  (IV ATM {move['iv_atm']*100:.1f}%)")
    print(f"  Drift Score:       {activity['drift_score']:,.0f}")

    slug = expiry_label.replace(' ', '_')
    viz.create_gex_profile_chart(gex['df_gex_profile'], spot, gex['gamma_switch_point'], expiry_label)\
        .write_html(f"{output_dir}/{slug}_gex.html")
    viz.create_oi_profile_chart(walls['df_oi_profile'], spot, expiry_label)\
        .write_html(f"{output_dir}/{slug}_oi.html")
    viz.create_volume_profile_chart(vol_profile['df_vol_profile'], spot, expiry_label)\
        .write_html(f"{output_dir}/{slug}_volume.html")
    viz.create_max_pain_chart(df_payouts, max_pain_strike, expiry_label)\
        .write_html(f"{output_dir}/{slug}_maxpain.html")
    viz.create_dex_profile_chart(dex['df_dex_profile'], spot, expiry_label)\
        .write_html(f"{output_dir}/{slug}_dex.html")
    viz.create_vex_profile_chart(vex['df_vex_profile'], spot, vex['vanna_switch_point'], expiry_label)\
        .write_html(f"{output_dir}/{slug}_vex.html")


# =============================================================================
# 4. MAIN
# =============================================================================
if __name__ == '__main__':
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Analizza export Euronext FTSEMIB come l'app CBOE.")
    parser.add_argument('csv_path', help="Percorso del file Euronext (copia-incolla, tab-separated)")
    parser.add_argument('spot', type=float, help="Spot FTSEMIB del giorno (es. 52381.92)")
    parser.add_argument('--mesi', nargs='+', default=['Jul-2026', 'Aug-2026', 'Sep-2026'],
                         help="Scadenze da analizzare, es. Jul-2026 Aug-2026 Sep-2026 Dec-2026")
    parser.add_argument('--out', default='output_ftsemib', help="Cartella di output per i grafici HTML")
    args = parser.parse_args()

    wanted = [(m.split('-')[0], int(m.split('-')[1])) for m in args.mesi]
    os.makedirs(args.out, exist_ok=True)

    df_raw, analysis_date = parse_euronext_file(args.csv_path, wanted_months=wanted)
    print(f"Data di riferimento: {analysis_date.date()}  |  Spot: {args.spot:,.2f}  |  Righe lette: {len(df_raw)}")

    df_full = enrich_with_greeks(df_raw, args.spot, analysis_date)

    for (mon, year) in wanted:
        exp_date = _third_friday(year, MONTH_MAP[mon])
        df_expiry = df_full[df_full['Expiration Date'] == exp_date]
        if df_expiry.empty:
            print(f"\n=== {mon} {year}: nessun dato nel file ===")
            continue
        analizza_scadenza(df_expiry, args.spot, f"{mon} {year}", args.out)

    print(f"\nGrafici salvati in ./{args.out}/ (apribili col browser).")

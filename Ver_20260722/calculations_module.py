# File: calculations_module.py
#
# [VERSIONE v3 - AUDIT KRITERION]
# - Gamma/Vanna FLIP: zero-gamma/zero-vanna rigoroso (esposizione ricalcolata al variare
#   dello spot), non lo zero-crossing per-strike (che cadeva banalmente sullo spot).
# - DRIFT (VWAS): baricentro dei volumi call+put (simmetrico), non piu' solo-call.
# - WALL: ricerca near-the-money (+/-10%) per non etichettare le coperture tail come supporti.
# - DEX/VEX: esposizioni AGGREGATE dell'open interest (nessuna convenzione dealer),
#   coerenti e onestamente etichettate; la GEX resta la metrica dealer (long-call/short-put).
# -----------------------------------------------------------------------------

import pandas as pd
import numpy as np
from scipy.stats import norm as _scipy_norm


# =============================================================================
# HELPER PRIVATO: Flip Level rigoroso (esposizione ricalcolata al variare dello spot)
# =============================================================================
_RF_RATE   = 0.045    # risk-free rate
_DIV_YIELD = 0.013    # dividend yield di default (indice azionario USA tipo SPX); drift = r - q
_MIN_DTE   = 1.0 / 365.25


def _exposure_curve_flip(df_selected_expiry, spot_price, greek, dealer_sign,
                         risk_free_rate=_RF_RATE, dividend_yield=_DIV_YIELD):
    """
    Calcola il 'flip level' nel modo corretto: ricalcola l'esposizione netta (gamma o
    vanna) su una griglia di prezzi IPOTETICI del sottostante e trova il livello dove
    l'esposizione netta attraversa lo zero (il piu' vicino allo spot).

    Questa e' la definizione standard del 'zero-gamma / gamma flip' (e analogo per la
    vanna): il PREZZO al quale il gamma netto dei dealer cambia segno. NON coincide con
    lo zero-crossing del profilo statico per-strike (che oscilla e cade banalmente sullo
    spot) ne' con la sua somma cumulata (che per un book net-short-gamma puo' non
    attraversare mai lo zero).

    Args:
        df_selected_expiry : righe di opzioni della scadenza (Strike, IV, DTE_Years, OI, Type).
        spot_price         : prezzo corrente del sottostante.
        greek              : 'gamma' oppure 'vanna'.
        dealer_sign        : True  -> convenzione dealer (call +, put -), usata per il Gamma Flip.
                             False -> esposizione aggregata dell'OI (nessun segno), per il Vanna Flip.

    Returns:
        float | None: livello interpolato del flip, o None se non trovato nel range +/-20%.
    """
    try:
        d = df_selected_expiry[
            (df_selected_expiry['IV'] > 0.001) &
            (df_selected_expiry['DTE_Years'] > 0) &
            (df_selected_expiry['Strike'] > 0) &
            (df_selected_expiry['OI'] > 0)
        ]
        if len(d) < 2 or spot_price is None or not np.isfinite(spot_price) or spot_price <= 0:
            return None

        K     = d['Strike'].to_numpy(dtype=float)
        T     = np.maximum(d['DTE_Years'].to_numpy(dtype=float), _MIN_DTE)
        sigma = d['IV'].to_numpy(dtype=float)
        OI    = d['OI'].to_numpy(dtype=float)
        sqrtT = np.sqrt(T)
        sgn   = np.where(d['Type'].to_numpy() == 'Call', 1.0, -1.0) if dealer_sign else np.ones(len(d))

        S_grid = np.linspace(spot_price * 0.80, spot_price * 1.20, 161)
        curve  = np.empty(len(S_grid))
        for j, S in enumerate(S_grid):
            d1 = (np.log(S / K) + (risk_free_rate - dividend_yield + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
            if greek == 'gamma':
                g        = _scipy_norm.pdf(d1) / (S * sigma * sqrtT)
                notional = g * OI * 100.0 * (S ** 2) * 0.01
            else:  # vanna
                d2       = d1 - sigma * sqrtT
                g        = -_scipy_norm.pdf(d1) * d2 / sigma
                notional = g * OI * 100.0 * S * 0.01
            curve[j] = np.nansum(sgn * notional)

        candidates = []
        for i in range(len(S_grid) - 1):
            y0, y1 = curve[i], curve[i + 1]
            if (y0 < 0 < y1) or (y0 > 0 > y1):
                x0, x1 = S_grid[i], S_grid[i + 1]
                candidates.append(float(x0 - (y0 * (x1 - x0) / (y1 - y0))))

        if not candidates:
            return None
        return min(candidates, key=lambda x: abs(x - spot_price))

    except Exception as e:
        print(f"[_exposure_curve_flip:{greek}]: {e}")
        return None


# =============================================================================
# 1. GAMMA EXPOSURE (GEX)
# =============================================================================
def calculate_gex_metrics(df_selected_expiry, spot_price,
                          risk_free_rate=_RF_RATE, dividend_yield=_DIV_YIELD):
    """
    Calcola le metriche GEX per una singola scadenza.
    Il Gamma Flip e' il livello zero-gamma (esposizione ricalcolata al variare dello spot).
    risk_free_rate / dividend_yield incidono solo sul calcolo del Flip.
    """
    df_gex_strike = df_selected_expiry.groupby('Strike')['GEX_Signed'].sum().reset_index()
    df_gex_strike.rename(columns={'GEX_Signed': 'Net_GEX'}, inplace=True)
    df_gex_strike = df_gex_strike.sort_values('Strike').reset_index(drop=True)

    total_net_gex      = df_gex_strike['Net_GEX'].sum()
    # Gamma Flip = livello (zero-gamma) dove il gamma netto dei dealer, ricalcolato al variare
    # dello spot, cambia segno. Convenzione dealer: call +, put -.
    gamma_switch_local = _exposure_curve_flip(df_selected_expiry, spot_price, 'gamma', True,
                                              risk_free_rate, dividend_yield)
    spot_delta         = (spot_price - gamma_switch_local) if gamma_switch_local is not None else None

    return {
        'df_gex_profile':    df_gex_strike,
        'total_net_gex':     total_net_gex,
        'gamma_switch_point': gamma_switch_local,
        'spot_switch_delta': spot_delta
    }


# =============================================================================
# 2. OPEN INTEREST WALLS
# =============================================================================
def calculate_oi_walls(df_selected_expiry, spot_price):
    """
    Calcola i Put/Call Walls per una singola scadenza.

    Il PROFILO OI viene mostrato su una fascia ampia (+/-25%), ma i WALL (max OI)
    vengono cercati SOLO vicino al prezzo (+/-10%): cosi' si evita di segnalare come
    'supporto' le put strutturali di copertura tail profondamente OTM (es. -20%),
    che non sono livelli operativi di supporto/resistenza intraday.
    """
    range_lower = spot_price * 0.75
    range_upper = spot_price * 1.25
    df_oi_relevant = df_selected_expiry[
        (df_selected_expiry['Strike'] >= range_lower) &
        (df_selected_expiry['Strike'] <= range_upper)
    ]

    # Fascia stretta near-the-money per la ricerca dei wall.
    wall_lower = spot_price * 0.90
    wall_upper = spot_price * 1.10
    df_wall_zone = df_oi_relevant[
        (df_oi_relevant['Strike'] >= wall_lower) &
        (df_oi_relevant['Strike'] <= wall_upper)
    ]

    oi_puts_support  = df_wall_zone[(df_wall_zone['Type'] == 'Put')  & (df_wall_zone['Strike'] <= spot_price)]
    put_wall_strike, max_put_oi = (None, 0)
    if not oi_puts_support.empty:
        idx_max         = oi_puts_support['OI'].idxmax()
        put_wall_strike = oi_puts_support.loc[idx_max]['Strike']
        max_put_oi      = oi_puts_support['OI'].max()

    oi_calls_res     = df_wall_zone[(df_wall_zone['Type'] == 'Call') & (df_wall_zone['Strike'] >= spot_price)]
    call_wall_strike, max_call_oi = (None, 0)
    if not oi_calls_res.empty:
        idx_max          = oi_calls_res['OI'].idxmax()
        call_wall_strike = oi_calls_res.loc[idx_max]['Strike']
        max_call_oi      = oi_calls_res['OI'].max()

    oi_calls_grouped = df_oi_relevant[df_oi_relevant['Type'] == 'Call'].groupby('Strike')['OI'].sum()
    oi_puts_grouped  = df_oi_relevant[df_oi_relevant['Type'] == 'Put'].groupby('Strike')['OI'].sum()
    df_oi_profile = pd.DataFrame({'Calls_OI': oi_calls_grouped, 'Puts_OI': oi_puts_grouped}).fillna(0).reset_index()
    df_oi_profile['Puts_OI_Neg'] = df_oi_profile['Puts_OI'] * -1.0

    return {
        'df_oi_profile':   df_oi_profile,
        'put_wall_strike': put_wall_strike, 'put_wall_oi':  max_put_oi,
        'call_wall_strike': call_wall_strike, 'call_wall_oi': max_call_oi
    }


# =============================================================================
# 3. MAX PAIN
# =============================================================================
def calculate_max_pain(df_selected_expiry):
    """Calcola lo strike Max Pain per la scadenza selezionata."""
    strikes  = sorted(df_selected_expiry['Strike'].unique())
    calls_oi = df_selected_expiry[df_selected_expiry['Type'] == 'Call'].set_index('Strike')['OI']
    puts_oi  = df_selected_expiry[df_selected_expiry['Type'] == 'Put'].set_index('Strike')['OI']
    total_payout_list = []

    for expiry_price in strikes:
        call_intrinsic = (expiry_price - calls_oi.index).to_numpy().clip(min=0)
        call_payout    = (call_intrinsic * calls_oi).sum()
        put_intrinsic  = (puts_oi.index - expiry_price).to_numpy().clip(min=0)
        put_payout     = (put_intrinsic * puts_oi).sum()
        total_payout_list.append({'Strike': expiry_price, 'Total_Payout': call_payout + put_payout})

    if not total_payout_list:
        return None, pd.DataFrame()
    df_payouts      = pd.DataFrame(total_payout_list)
    max_pain_strike = df_payouts.loc[df_payouts['Total_Payout'].idxmin()]['Strike']
    return max_pain_strike, df_payouts


# =============================================================================
# 4. PUT/CALL RATIOS
# =============================================================================
def calculate_pc_ratios(df_selected_expiry):
    """Calcola i Put/Call Ratios per OI e Volume."""
    total_put_oi   = df_selected_expiry[df_selected_expiry['Type'] == 'Put']['OI'].sum()
    total_call_oi  = df_selected_expiry[df_selected_expiry['Type'] == 'Call']['OI'].sum()
    pc_oi_ratio    = total_put_oi / total_call_oi if total_call_oi > 0 else np.nan
    total_put_vol  = df_selected_expiry[df_selected_expiry['Type'] == 'Put']['Vol'].sum()
    total_call_vol = df_selected_expiry[df_selected_expiry['Type'] == 'Call']['Vol'].sum()
    pc_vol_ratio   = total_put_vol / total_call_vol if total_call_vol > 0 else np.nan
    return {'pc_oi_ratio': pc_oi_ratio, 'pc_vol_ratio': pc_vol_ratio}


# =============================================================================
# 5. EXPECTED MOVE
# =============================================================================
def calculate_expected_move(df_selected_expiry, spot_price):
    """Calcola il movimento atteso basato sulla IV ATM."""
    try:
        atm_strike_index = (df_selected_expiry['Strike'] - spot_price).abs().idxmin()
        atm_strike_val   = df_selected_expiry.loc[atm_strike_index]['Strike']
        df_atm           = df_selected_expiry[df_selected_expiry['Strike'] == atm_strike_val]
        # Media solo delle IV valide (>0): una IV mancante (NaN) o 0 non deve dimezzare il valore.
        iv_series        = df_atm.loc[df_atm['IV'] > 0, 'IV']
        if iv_series.empty:
            return {'move': None, 'upper_band': None, 'lower_band': None, 'iv_atm': None}
        iv_atm           = iv_series.mean()
        dte_years        = df_atm['DTE_Years'].iloc[0]
        # 'not (dte_years > 0)' cattura anche NaN e lo 0DTE (floor a 1 giorno di calendario).
        if not (dte_years > 0):
            dte_years = 1 / 365.25
        move = spot_price * iv_atm * np.sqrt(dte_years)
        return {'move': move, 'upper_band': spot_price + move, 'lower_band': spot_price - move, 'iv_atm': iv_atm}
    except Exception as e:
        print(f"[Errore Calcolo Expected Move]: {e}")
        return {'move': None, 'upper_band': None, 'lower_band': None, 'iv_atm': None}


# =============================================================================
# 6. VOLUME PROFILE
# =============================================================================
def calculate_volume_profile(df_selected_expiry, spot_price):
    """Prepara il DataFrame per il grafico bidirezionale dei Volumi."""
    range_lower = spot_price * 0.75
    range_upper = spot_price * 1.25
    df_vol_relevant  = df_selected_expiry[
        (df_selected_expiry['Strike'] >= range_lower) &
        (df_selected_expiry['Strike'] <= range_upper)
    ]
    vol_calls_grouped = df_vol_relevant[df_vol_relevant['Type'] == 'Call'].groupby('Strike')['Vol'].sum()
    vol_puts_grouped  = df_vol_relevant[df_vol_relevant['Type'] == 'Put'].groupby('Strike')['Vol'].sum()
    df_vol_profile = pd.DataFrame({'Calls_Vol': vol_calls_grouped, 'Puts_Vol': vol_puts_grouped}).fillna(0).reset_index()
    df_vol_profile['Puts_Vol_Neg'] = df_vol_profile['Puts_Vol'] * -1.0
    return {'df_vol_profile': df_vol_profile}


# =============================================================================
# 7. ACTIVITY RATIO / DRIFT SCORE
# =============================================================================
def calculate_activity_ratio(df_selected_expiry, spot_price):
    """
    Calcola il rapporto Vol/OI e il 'Drift Score' (VWAS).

    Il Drift Score e' il VWAS (Volume-Weighted Average Strike) calcolato su
    TUTTO il volume di giornata (call + put) nella fascia +/-25% dallo spot.
    E' simmetrico rispetto allo spot: se il baricentro dei volumi e' sopra lo
    spot indica bias rialzista, se e' sotto indica bias ribassista.
    """
    range_lower = spot_price * 0.75
    range_upper = spot_price * 1.25
    df_relevant = df_selected_expiry[
        (df_selected_expiry['Strike'] >= range_lower) &
        (df_selected_expiry['Strike'] <= range_upper)
    ]

    df_grouped  = df_relevant.groupby(['Strike', 'Type'])[['OI', 'Vol']].sum().unstack(fill_value=0)
    df_profile  = pd.DataFrame(index=df_grouped.index)
    df_profile['Call_OI']  = df_grouped[('OI',  'Call')]
    df_profile['Call_Vol'] = df_grouped[('Vol', 'Call')]
    df_profile['Put_OI']   = df_grouped[('OI',  'Put')]
    df_profile['Put_Vol']  = df_grouped[('Vol', 'Put')]

    df_profile['Call_Activity_Ratio']     = df_profile['Call_Vol'] / (df_profile['Call_OI'] + 1)
    df_profile['Put_Activity_Ratio']      = df_profile['Put_Vol']  / (df_profile['Put_OI']  + 1)
    df_profile['Put_Activity_Ratio_Neg']  = df_profile['Put_Activity_Ratio'] * -1.0

    # Drift Score = VWAS su TUTTO il volume (call + put): baricentro simmetrico rispetto allo spot,
    # quindi capace di risultare sia sopra (rialzista) sia sotto (ribassista).
    total_vol = df_relevant['Vol'].sum()
    if total_vol > 0:
        vol_by_strike = df_relevant.groupby('Strike')['Vol'].sum()
        drift_score = (vol_by_strike.index * vol_by_strike).sum() / vol_by_strike.sum()
    else:
        drift_score = spot_price

    return {
        'df_activity_profile': df_profile.reset_index(),
        'drift_score':         drift_score
    }


# =============================================================================
# 8. DELTA EXPOSURE (DEX) — NUOVO
# =============================================================================
def calculate_dex_metrics(df_selected_expiry, spot_price):
    """
    Calcola la Delta Exposure (DEX) aggregata per Strike.

    La DEX Nozionale e' la somma di Delta * OI * 100 * Spot sull'open interest
    (call con delta positivo, put con delta negativo). Misura il POSIZIONAMENTO
    DIREZIONALE NETTO dell'open interest, NON l'esposizione dei dealer (nessuna
    ipotesi di segno dealer viene applicata, a differenza della GEX):
    - DEX netto positivo  = OI net-long delta (prevale il delta delle call);
    - DEX netto negativo  = OI net-short delta (prevale il delta delle put).

    Formula applicata in data_module.py:
        DEX_Notional = Delta * OI * 100 * Spot

    Returns:
        dict con:
        - df_dex_profile   : DataFrame [Strike, Net_DEX] ordinato per Strike
        - total_net_dex    : Somma algebrica di tutto il DEX per la scadenza
    """
    # Aggrega DEX_Notional per Strike (somma calls + puts)
    df_dex_strike = df_selected_expiry.groupby('Strike')['DEX_Notional'].sum().reset_index()
    df_dex_strike.rename(columns={'DEX_Notional': 'Net_DEX'}, inplace=True)
    df_dex_strike = df_dex_strike.sort_values('Strike').reset_index(drop=True)

    total_net_dex = df_dex_strike['Net_DEX'].sum()

    return {
        'df_dex_profile': df_dex_strike,
        'total_net_dex':  total_net_dex
    }


# =============================================================================
# 9. VANNA EXPOSURE (VEX) — NUOVO
# =============================================================================
def calculate_vex_metrics(df_selected_expiry, spot_price,
                          risk_free_rate=_RF_RATE, dividend_yield=_DIV_YIELD):
    """
    Calcola la Vanna Exposure (VEX) aggregata per Strike.

    La VEX Nozionale e' la somma di Vanna * OI * 100 * Spot * 1% sull'open interest.
    Misura come varia il delta AGGREGATO dell'open interest per una variazione di
    +1% della Volatilita' Implicita. E' un'esposizione aggregata dell'OI, NON dei
    dealer (nessuna ipotesi di segno dealer applicata, come per la DEX):
    - VEX netto positivo a uno strike: il delta aggregato dell'OI aumenta se la vol sale
      (e diminuisce se la vol scende);
    - VEX netto negativo: il delta aggregato diminuisce se la vol sale.

    Formula applicata in data_module.py:
        VEX_Notional = Vanna_BS * OI * 100 * Spot * 0.01

    Il "Vanna Flip" e' il livello di prezzo (zero-vanna, ricalcolato al variare
    dello spot) dove la vanna netta aggregata cambia segno (stessa logica del Gamma Flip).

    Returns:
        dict con:
        - df_vex_profile    : DataFrame [Strike, Net_VEX] ordinato per Strike
        - total_net_vex     : Somma algebrica del VEX per la scadenza
        - vanna_switch_point: Strike interpolato dello zero crossing (o None)
    """
    # Aggrega VEX_Notional per Strike (somma calls + puts)
    df_vex_strike = df_selected_expiry.groupby('Strike')['VEX_Notional'].sum().reset_index()
    df_vex_strike.rename(columns={'VEX_Notional': 'Net_VEX'}, inplace=True)
    df_vex_strike = df_vex_strike.sort_values('Strike').reset_index(drop=True)

    total_net_vex = df_vex_strike['Net_VEX'].sum()

    # Vanna Flip: livello dove la vanna netta aggregata dell'OI, ricalcolata al variare
    # dello spot, cambia segno (nessuna convenzione dealer, coerente con la VEX aggregata).
    vanna_switch_point = _exposure_curve_flip(df_selected_expiry, spot_price, 'vanna', False,
                                              risk_free_rate, dividend_yield)

    return {
        'df_vex_profile':    df_vex_strike,
        'total_net_vex':     total_net_vex,
        'vanna_switch_point': vanna_switch_point
    }

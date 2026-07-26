# File: data_module.py
#
# Modulo per il caricamento, parsing e preprocessing dei dati CBOE.
# [AGGIORNATO v2] Calcolo DEX_Notional e VEX_Notional (Vanna BS analitico via scipy).
# py_vollib rimosso: Vanna calcolato con formula chiusa BS + scipy.stats.norm.
# -----------------------------------------------------------------------------

import pandas as pd
import numpy as np
import io
import re
import datetime as dt
import streamlit as st
from scipy.stats import norm as _scipy_norm


def _compute_vanna_vectorized(type_series, strike_series, dte_years_series, iv_series, spot,
                              risk_free_rate=0.045, dividend_yield=0.013):
    """
    Calcola il Vanna per ogni riga del DataFrame con operazioni numpy vettorizzate.

    Formula analitica Black-Scholes:
        Vanna = dDelta/dSigma = -N_prime(d1) * d2 / sigma

    Dove:
        d1 = [ln(S/K) + (r + sigma^2/2)*T] / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)
        N_prime(x) = PDF standard normale

    Il Vanna e' identico per Call e Put: la vettorizzazione e' completa.
    """
    # risk_free_rate e dividend_yield arrivano dai parametri di modello impostabili nella
    # sidebar dell'app (default calibrati su un indice azionario USA tipo SPX). Drift = (r - q).
    MIN_DTE = 1.0 / 365.25
    MIN_IV = 0.001

    S = float(spot)
    K = strike_series.values.astype(float)
    T = np.maximum(dte_years_series.values.astype(float), MIN_DTE)
    sigma = iv_series.values.astype(float)

    valid = (sigma > MIN_IV) & (K > 0) & (S > 0)
    vanna = np.zeros(len(K), dtype=float)

    if valid.any():
        K_v = K[valid]
        T_v = T[valid]
        sigma_v = sigma[valid]

        d1 = (np.log(S / K_v) + (risk_free_rate - dividend_yield + 0.5 * sigma_v ** 2) * T_v) / (sigma_v * np.sqrt(T_v))
        d2 = d1 - sigma_v * np.sqrt(T_v)
        raw_vanna = -_scipy_norm.pdf(d1) * d2 / sigma_v
        vanna[valid] = np.where(np.isfinite(raw_vanna), raw_vanna, 0.0)

    return vanna


def _extract_underlying_symbol(lines, df_options=None):
    """
    Estrae il ticker del sottostante dal file CBOE, per non assumere che sia sempre SPX.

    1. Header: la prima riga utile e' tipicamente "SPX (S&P 500 INDEX)" o "AAPL (Apple Inc)".
    2. Fallback: radice alfabetica del simbolo del contratto (colonna Calls/Puts).

    Returns:
        str | None: il ticker in maiuscolo, o None se non identificabile.
    """
    try:
        for line in (lines or [])[:6]:
            s = line.strip().strip('"').strip()
            if not s:
                continue
            m = re.match(r'\^?([A-Za-z][A-Za-z0-9\.\-]{0,11})\s*\(', s)
            if m:
                return m.group(1).upper()
    except Exception:
        pass

    try:
        if df_options is not None and 'Symbol' in df_options.columns:
            symbols = df_options['Symbol'].dropna().astype(str)
            if not symbols.empty:
                m = re.match(r'\s*\^?([A-Za-z]{1,6})', symbols.iloc[0])
                if m:
                    return m.group(1).upper()
    except Exception:
        pass

    return None


def parse_cboe_csv(uploaded_file, risk_free_rate=0.045, dividend_yield=0.013):
    """
    Esegue il parsing del file CSV CBOE caricato.
    [v2] Aggiunge DEX_Notional (Delta) e VEX_Notional (Vanna) al DataFrame.
    [v3] Estrae anche il ticker del sottostante (non piu' assunto SPX).
    [v4] risk_free_rate e dividend_yield sono parametrici (impostabili dalla sidebar):
         incidono solo su Vanna/VEX. Default calibrati su un indice azionario USA.

    Returns:
        (df_processed, spot_price, data_timestamp, underlying_symbol)
    """
    step = "Inizio"
    try:
        # --- 1. Lettura Raw ---
        step = "Lettura File"
        raw_data = uploaded_file.getvalue()
        try:
            # 'utf-8-sig' rimuove l'eventuale BOM, che altrimenti sporcherebbe la prima riga
            # (da cui estraiamo il ticker del sottostante).
            data_str = raw_data.decode('utf-8-sig')
        except UnicodeDecodeError:
            data_str = raw_data.decode('latin-1')

        lines = data_str.split('\n')
        header_block = " ".join([line.strip() for line in lines[:15]])

        # Ticker del sottostante (es. SPX, SPY, AAPL...): non assumiamo mai SPX.
        underlying_symbol = _extract_underlying_symbol(lines)

        # --- 2. Estrazione Spot Price ---
        step = "Estrazione Spot Price"
        spot_price_extracted = None

        last_match = re.search(r'Last:\s*([\d,]+\.?\d*)', header_block)
        if last_match:
            try:
                spot_price_extracted = float(last_match.group(1).replace(',', ''))
            except Exception:
                pass

        if spot_price_extracted is None or spot_price_extracted == 0:
            bid_match = re.search(r'Bid:\s*([\d,]+\.?\d*)', header_block)
            ask_match = re.search(r'Ask:\s*([\d,]+\.?\d*)', header_block)
            if bid_match and ask_match:
                try:
                    bid = float(bid_match.group(1).replace(',', ''))
                    ask = float(ask_match.group(1).replace(',', ''))
                    if ask > 0:
                        spot_price_extracted = (bid + ask) / 2
                except Exception:
                    pass

        # --- 3. Estrazione Timestamp ---
        step = "Estrazione Data"
        data_timestamp_extracted = "Data non disponibile"
        analysis_date = pd.Timestamp.now().normalize()

        try:
            date_match = re.search(r'Date:\s*(.*?)(?:,Bid|,Ask|GMT)', header_block)
            if date_match:
                # Rimuove eventuali virgolette residue (es. '...EDT"') e spazi
                data_timestamp_extracted = date_match.group(1).strip().strip('"').strip()
            else:
                st.warning(
                    "Attenzione: timestamp non trovato nell'header del file. "
                    "Uso la data odierna per il calcolo del DTE."
                )

            if data_timestamp_extracted != "Data non disponibile":
                italian_to_english_months = {
                    'gennaio': 'January', 'febbraio': 'February', 'marzo': 'March',
                    'aprile': 'April', 'maggio': 'May', 'giugno': 'June', 'luglio': 'July',
                    'agosto': 'August', 'settembre': 'September', 'ottobre': 'October',
                    'novembre': 'November', 'dicembre': 'December'
                }
                # Normalizza: minuscolo + traduzione mesi IT -> EN
                date_low = data_timestamp_extracted.lower()
                for it, en in italian_to_english_months.items():
                    date_low = date_low.replace(it, en.lower())
                # Toglie la parte oraria: gestisce sia ' at ' (EN CBOE) sia ' alle ' (IT)
                date_low = re.split(r'\s+(?:at|alle)\s+', date_low)[0].strip().rstrip(',').strip()

                # Estrazione tollerante a entrambi gli ordini:
                #   "july 17, 2026"  (CBOE inglese, mese-giorno)   /   "17 july 2026"  (italiano, giorno-mese)
                m = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(\d{4})', date_low)      # mese giorno anno
                if m:
                    analysis_date = pd.to_datetime(
                        f"{m.group(1)} {m.group(2)} {m.group(3)}", format='%B %d %Y'
                    ).normalize()
                else:
                    m = re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})', date_low)    # giorno mese anno
                    if m:
                        analysis_date = pd.to_datetime(
                            f"{m.group(2)} {m.group(1)} {m.group(3)}", format='%B %d %Y'
                        ).normalize()
                    else:
                        raise ValueError(f"Formato data non riconosciuto: '{data_timestamp_extracted}'")

        except Exception as e:
            st.warning(
                f"Attenzione: Impossibile leggere la data ('{data_timestamp_extracted}'). "
                f"Uso data odierna per DTE. Errore: {e}"
            )
            analysis_date = pd.Timestamp.now().normalize()

        # --- 4. Caricamento CSV ---
        step = "Ricerca Header CSV"
        header_row_index = None
        for i, line in enumerate(lines):
            if line.strip().startswith("Expiration Date"):
                header_row_index = i
                break

        if header_row_index is None:
            st.error("Errore: Impossibile trovare la riga 'Expiration Date' nel file.")
            return None, None, None, None

        step = "Parsing CSV Pandas"
        data_io_csv = io.StringIO(data_str)
        df_options_raw = pd.read_csv(data_io_csv, skiprows=header_row_index, thousands=',')
        df_options_raw.columns = df_options_raw.columns.str.strip()
        df_options_raw.dropna(how='all', inplace=True)
        df_options_raw.reset_index(drop=True, inplace=True)

        if spot_price_extracted is None or spot_price_extracted == 0:
            if 'Strike' in df_options_raw.columns:
                median_strike = pd.to_numeric(df_options_raw['Strike'], errors='coerce').median()
                spot_price_extracted = median_strike
                st.warning(
                    f"Spot Price non trovato nell'header: stimato dalla mediana degli strike "
                    f"({spot_price_extracted}). NB: e' il centro della catena, non il prezzo reale; "
                    f"tutte le metriche in dollari sono APPROSSIMATE."
                )

        # Spot non utilizzabile (None/NaN/<=0) -> stop esplicito, evita una dashboard piena di 'nan'.
        if (spot_price_extracted is None or not np.isfinite(spot_price_extracted)
                or spot_price_extracted <= 0):
            st.error(
                "Errore: impossibile determinare uno Spot Price valido dal file. "
                "Verifica l'header del CSV CBOE (righe 'Last:'/'Bid:'/'Ask:')."
            )
            return None, None, None, None

        # --- 5. Separazione Calls/Puts ---
        step = "Separazione Call/Put"
        strike_cols = [i for i, c in enumerate(df_options_raw.columns) if c == 'Strike']
        if not strike_cols:
            st.error("Errore: Colonna 'Strike' non trovata nel CSV.")
            return None, None, None, None
        strike_col_index = strike_cols[0]

        call_cols = list(df_options_raw.columns[:strike_col_index])
        put_cols = list(df_options_raw.columns[strike_col_index + 1:])

        call_rename_map = {
            'Expiration Date': 'Expiration Date', 'Calls': 'Symbol', 'Last Sale': 'Last',
            'Net': 'Net', 'Bid': 'Bid', 'Ask': 'Ask', 'Volume': 'Vol', 'IV': 'IV',
            'Delta': 'Delta', 'Gamma': 'Gamma', 'Open Interest': 'OI', 'Strike': 'Strike'
        }
        put_rename_map = {
            'Strike': 'Strike', 'Expiration Date': 'Expiration Date', 'Puts': 'Symbol',
            'Last Sale': 'Last', 'Net': 'Net', 'Bid': 'Bid', 'Ask': 'Ask', 'Volume': 'Vol',
            'IV': 'IV', 'Delta': 'Delta', 'Gamma': 'Gamma', 'Open Interest': 'OI'
        }

        df_calls = df_options_raw[call_cols + ["Strike"]].copy()
        df_calls.columns = [call_rename_map.get(c.strip(), c.strip()) for c in df_calls.columns]
        df_calls['Type'] = 'Call'

        df_puts = df_options_raw[["Strike", "Expiration Date"] + put_cols].copy()
        clean_put_cols = [re.sub(r'\.\d+$', '', c).strip() for c in df_puts.columns]
        df_puts.columns = [put_rename_map.get(c, c) for c in clean_put_cols]
        df_puts['Type'] = 'Put'

        df_options_clean = pd.concat([df_calls, df_puts], ignore_index=True)

        # Verifica che le colonne canoniche essenziali esistano (header CBOE variato -> errore chiaro).
        required_cols = ['Strike', 'OI', 'Delta', 'Gamma']
        missing_cols = [c for c in required_cols if c not in df_options_clean.columns]
        if missing_cols:
            st.error(
                f"Errore: colonne attese mancanti dopo il parsing ({missing_cols}). "
                f"Verifica che il file sia un export standard della catena opzioni CBOE."
            )
            return None, None, None, None

        # --- 6. Conversione Numerica ---
        step = "Conversione Numerica"
        # Colonne dove uno 0 e' semanticamente valido (nessun prezzo/size/OI): riempi a 0.
        fill_zero_cols = ['Last', 'Bid', 'Ask', 'Vol', 'OI']
        for col in fill_zero_cols:
            if col in df_options_clean.columns:
                df_options_clean[col] = pd.to_numeric(df_options_clean[col], errors='coerce').fillna(0)

        # Strike e Greche/IV: NON riempire con 0 (uno 0 fittizio falserebbe le metriche). Tieni NaN.
        keep_nan_cols = ['Strike', 'IV', 'Delta', 'Gamma']
        for col in keep_nan_cols:
            if col in df_options_clean.columns:
                df_options_clean[col] = pd.to_numeric(df_options_clean[col], errors='coerce')

        # Uno Strike non numerico non e' utilizzabile: rimuovi la riga (niente strike-fantasma a 0).
        before_strike = len(df_options_clean)
        df_options_clean = df_options_clean[
            df_options_clean['Strike'].notna() & (df_options_clean['Strike'] > 0)
        ].copy()
        dropped_strike = before_strike - len(df_options_clean)
        if dropped_strike > 0:
            st.warning(f"Attenzione: {dropped_strike} righe con Strike non valido sono state rimosse.")

        df_processed = df_options_clean.copy()

        # --- Parsing scadenze robusto: prova il formato CBOE, poi fallback tollerante (dateutil) ---
        step = "Parsing Scadenze"
        exp_parsed = pd.to_datetime(df_processed['Expiration Date'], format='%a %b %d %Y', errors='coerce')
        if exp_parsed.isna().mean() > 0.5:
            # Il formato non e' quello atteso: tenta un'inferenza generica (ISO, US, abbreviato...).
            exp_parsed = pd.to_datetime(df_processed['Expiration Date'], errors='coerce')
        df_processed['Expiration Date'] = exp_parsed

        if df_processed['Expiration Date'].isna().all():
            st.error(
                "Errore: impossibile interpretare le date di scadenza ('Expiration Date'). "
                "Il formato del file potrebbe essere cambiato."
            )
            return None, None, None, None
        n_bad_exp = int(df_processed['Expiration Date'].isna().sum())
        if n_bad_exp > 0:
            st.warning(f"Attenzione: {n_bad_exp} righe con data di scadenza non valida sono state rimosse.")
            df_processed = df_processed[df_processed['Expiration Date'].notna()].copy()

        df_processed['DTE_Days'] = (df_processed['Expiration Date'] - analysis_date).dt.days
        df_processed['DTE_Years'] = df_processed['DTE_Days'] / 365.25

        # Greche mancanti su strike con OI: segnala (trasparenza) e azzera SOLO per l'esposizione.
        greek_missing = df_processed[
            (df_processed['OI'] > 0) &
            (df_processed['Delta'].isna() | df_processed['Gamma'].isna())
        ]
        if not greek_missing.empty:
            st.warning(
                f"Attenzione: {len(greek_missing)} strike con OI>0 hanno Greche mancanti "
                f"(OI totale {greek_missing['OI'].sum():,.0f}); contano 0 nelle esposizioni GEX/DEX."
            )
        df_processed['Delta'] = df_processed['Delta'].fillna(0)
        df_processed['Gamma'] = df_processed['Gamma'].fillna(0)
        # NB: 'IV' resta NaN se mancante -> gestita a valle (Expected Move, vol surface, vanna).

        if spot_price_extracted and spot_price_extracted > 0 and np.isfinite(spot_price_extracted):
            df_processed['Moneyness'] = df_processed['Strike'] / spot_price_extracted
        else:
            df_processed['Moneyness'] = np.nan

        # --- 7. Calcolo GEX ---
        step = "Calcolo GEX"
        CONTRACT_MULTIPLIER = 100.0
        SPOT = spot_price_extracted

        if SPOT and SPOT > 0:
            df_processed['GEX_Notional'] = (
                df_processed['Gamma'] * df_processed['OI'] *
                CONTRACT_MULTIPLIER * (SPOT / 100.0) * SPOT
            )
            df_processed['GEX_Signed'] = np.where(
                df_processed['Type'] == 'Call',
                df_processed['GEX_Notional'],
                df_processed['GEX_Notional'] * -1.0
            )
        else:
            df_processed['GEX_Notional'] = 0.0
            df_processed['GEX_Signed'] = 0.0

        # --- 8. Calcolo DEX (Delta Exposure Nozionale) ---
        # DEX_Notional = Delta * OI * 100 * Spot
        # Delta CBOE: positivo per Call, negativo per Put (gia' con segno corretto)
        step = "Calcolo DEX"
        if SPOT and SPOT > 0:
            df_processed['DEX_Notional'] = (
                df_processed['Delta'] * df_processed['OI'] * CONTRACT_MULTIPLIER * SPOT
            )
        else:
            df_processed['DEX_Notional'] = 0.0

        # --- 9. Calcolo Vanna e VEX (Vanna Exposure Nozionale) ---
        # VEX_Notional = Vanna_BS * OI * 100 * Spot * 0.01
        # Moltiplicatore 0.01 = sensitività a una variazione dell'1% di IV
        step = "Calcolo VEX (Vanna BS)"
        if SPOT and SPOT > 0:
            try:
                vanna_values = _compute_vanna_vectorized(
                    df_processed['Type'],
                    df_processed['Strike'],
                    df_processed['DTE_Years'],
                    df_processed['IV'],
                    SPOT,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=dividend_yield
                )
                df_processed['Vanna'] = vanna_values
                df_processed['VEX_Notional'] = (
                    df_processed['Vanna'] * df_processed['OI'] *
                    CONTRACT_MULTIPLIER * SPOT * 0.01
                )
            except Exception as e:
                st.warning(f"Calcolo VEX fallito: {e}. VEX impostato a 0.")
                df_processed['Vanna'] = 0.0
                df_processed['VEX_Notional'] = 0.0
        else:
            df_processed['Vanna'] = 0.0
            df_processed['VEX_Notional'] = 0.0

        # --- 10. Filtri Finali ---
        original_len = len(df_processed)
        df_processed = df_processed[df_processed['OI'] > 0].copy()

        if df_processed.empty and original_len > 0:
            st.warning("Attenzione: Il filtraggio 'OI > 0' ha rimosso tutte le righe.")

        # Se l'header non conteneva il ticker, prova a ricavarlo dal simbolo dei contratti.
        if not underlying_symbol:
            underlying_symbol = _extract_underlying_symbol(None, df_processed)
        if not underlying_symbol:
            underlying_symbol = "UNDERLYING"
            st.info("Ticker del sottostante non riconosciuto dal file: uso un'etichetta generica.")

        print(
            f"[data_module] Parsing OK. Sottostante: {underlying_symbol}, "
            f"Spot: {spot_price_extracted}, Data: {analysis_date}, "
            f"Righe post-filtro: {len(df_processed)}"
        )
        return df_processed, spot_price_extracted, data_timestamp_extracted, underlying_symbol

    except Exception as e:
        st.error(
            f"Impossibile elaborare il file (fase: {step}). "
            f"Verifica che sia un CSV non modificato della catena opzioni CBOE."
        )
        # Traccia completa solo lato server (log), non nell'interfaccia pubblica.
        import traceback
        print("[data_module] ERRORE parsing:\n" + traceback.format_exc())
        return None, None, None, None

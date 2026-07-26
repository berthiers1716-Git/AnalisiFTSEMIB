# File: app_euronext.py
#
# Versione FTSEMIB/Euronext dell'Options Chain Analyzer di Kriterion Quant.
# Stessa interfaccia e stessi grafici dell'app originale (CBOE), ma il caricamento
# dati e' adattato al formato Euronext (testo incollato dall'editor Jupyter) e i
# parametri di mercato di default sono quelli del FTSEMIB, non dello SPX.
#
# DIFFERENZA METODOLOGICA IMPORTANTE rispetto all'app CBOE originale:
# Euronext non fornisce Delta/Gamma/IV pronti. Vengono derivati qui invertendo
# Black-Scholes dal prezzo "Settle" di ciascuna opzione (euronext_module.py).
# Sono quindi stime di modello, non dati di mercato osservati.
# -----------------------------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt

from euronext_module import parse_euronext_text, enrich_with_greeks
from calculations_module import (
    calculate_gex_metrics, calculate_oi_walls, calculate_max_pain,
    calculate_pc_ratios, calculate_expected_move, calculate_volume_profile,
    calculate_activity_ratio, calculate_dex_metrics, calculate_vex_metrics
)
from visualization_module import (
    create_gex_profile_chart, create_oi_profile_chart, create_volatility_surface_3d,
    create_volume_profile_chart, create_max_pain_chart, create_activity_ratio_chart,
    create_drift_arrow_chart, create_dex_profile_chart, create_vex_profile_chart
)

st.set_page_config(
    page_title="FTSEMIB Options Analyzer (Euronext)",
    page_icon="📊", layout="wide", initial_sidebar_state="expanded"
)
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    body, .stApp, .stTextArea > div > div > textarea, .stNumberInput > div > div > input {
        font-family: 'Inter', sans-serif; color: #e5e7eb;
    }
    div[data-testid="stMetric"] {
        background-color: #111827; border: 1px solid #1f2937;
        border-radius: 8px; padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 FTSEMIB Options Analyzer (Euronext)")
st.caption(
    "⚠️ **Solo a scopo informativo/educativo — NON è consulenza finanziaria.** "
    "Delta, Gamma, IV e Vanna non sono forniti da Euronext: sono stimati qui invertendo "
    "Black-Scholes dal prezzo *Settle* di ciascuna opzione — sono ipotesi di modello sopra "
    "un modello, non dati di mercato osservati. Il *Settle* Euronext può occasionalmente "
    "essere anomalo su strike poco liquidi: le righe che violano i limiti no-arbitraggio "
    "vengono scartate automaticamente e segnalate."
)

# -----------------------------------------------------------------------------
# SIDEBAR: parametri di mercato (default FTSEMIB, non SPX)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Parametri di mercato")
    spot_price = st.number_input(
        "Spot FTSEMIB del giorno",
        min_value=0.0, value=52381.92, step=1.0, format="%.2f",
        help="Euronext non lo include nel testo incollato: inseriscilo tu (es. chiusura del giorno)."
    )
    st.divider()
    risk_free_rate = st.number_input(
        "Risk-free rate (% annuo)",
        min_value=-5.0, max_value=25.0, value=2.25, step=0.05, format="%.2f",
        help="Default: tasso BCE sui depositi in vigore dal 17/6/2026."
    ) / 100.0
    dividend_yield = st.number_input(
        "Dividend yield (% annuo)",
        min_value=0.0, max_value=25.0, value=4.20, step=0.10, format="%.2f",
        help="Default: stima dividend yield FTSEMIB 2026 (~4.2%, contro l'1.3% USA dell'app CBOE)."
    ) / 100.0
    contract_multiplier = st.number_input(
        "Moltiplicatore contratto (€/punto)",
        min_value=0.1, value=2.5, step=0.1, format="%.1f",
        help="MIBO (FTSEMIB, Borsa Italiana/Euronext): €2.5 per punto indice, non 100 come SPX."
    )
    st.divider()
    st.caption(
        "Questi valori incidono su tutte le esposizioni nozionali (GEX/DEX/VEX) e sui "
        "livelli di Flip. Il risk-free e il dividend yield incidono anche sulla IV derivata."
    )


# -----------------------------------------------------------------------------
# CARICAMENTO DATI: upload del file CSV Euronext (a blocchi per scadenza)
# -----------------------------------------------------------------------------
st.subheader("1. Carica il file CSV Euronext")
st.caption(
    "Il file che già usi (copiato dall'editor Jupyter dalla pagina opzioni FTSEMIB, con "
    "più scadenze incluse). Usa un export con Open Interest già disponibile (di solito il "
    "giorno successivo alla data di riferimento)."
)
uploaded_file = st.file_uploader("File CSV", type=["csv", "txt"])

df_raw, analysis_date = None, None
if uploaded_file is not None:
    try:
        text = uploaded_file.getvalue().decode("utf-8-sig")
        df_raw, analysis_date = parse_euronext_text(text)
        n_expiries = df_raw['Expiration Date'].nunique()
        st.success(f"Letto: {len(df_raw)} righe, {n_expiries} scadenze, data di riferimento {analysis_date.date()}.")
    except Exception as e:
        st.error(f"Errore nel parsing del file: {e}")
else:
    st.info("In attesa del caricamento del file CSV...")

# -----------------------------------------------------------------------------
# CORPO PRINCIPALE
# -----------------------------------------------------------------------------
if df_raw is not None and spot_price > 0:

    unique_expirations = sorted(df_raw['Expiration Date'].dropna().unique())
    _WEEKDAYS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def _expiry_label(d):
        ts = pd.Timestamp(d)
        return f"{ts.strftime('%Y-%m-%d')} ({_WEEKDAYS_EN[ts.weekday()]})"

    expiry_options_map = {_expiry_label(d): d for d in unique_expirations}
    df_expiry_oi = df_raw.dropna(subset=['Expiration Date']).groupby('Expiration Date')['OI'].sum()
    default_expiry_label = _expiry_label(df_expiry_oi.idxmax()) if not df_expiry_oi.empty else list(expiry_options_map.keys())[0]

    st.subheader("2. Seleziona la scadenza")
    selected_expiry_label = st.selectbox(
        'Scadenza:', options=list(expiry_options_map.keys()),
        index=list(expiry_options_map.keys()).index(default_expiry_label)
    )
    selected_expiry_date = expiry_options_map[selected_expiry_label]

    # Deriva Greche SOLO per la scadenza selezionata (rapido); il resto del file
    # resta grezzo finche' non serve (es. Vol Surface, on demand piu' sotto).
    @st.cache_data
    def _enrich(df_expiry_raw, spot, analysis_date, r, q, mult):
        return enrich_with_greeks(df_expiry_raw, spot, analysis_date, r, q, mult)

    df_selected_raw = df_raw[df_raw['Expiration Date'] == selected_expiry_date].copy()
    df_selected_expiry, n_discarded = _enrich(
        df_selected_raw, spot_price, analysis_date, risk_free_rate, dividend_yield, contract_multiplier
    )
    if n_discarded > 0:
        st.warning(
            f"{n_discarded}/{len(df_selected_expiry)} righe di questa scadenza avevano un Settle "
            f"non invertibile (fuori limiti no-arbitraggio) e sono state escluse da IV/Delta/Gamma/Vanna "
            f"(restano incluse nei calcoli basati solo su OI/Volume, come Max Pain e i Wall)."
        )

    df_selected_expiry_oi = df_selected_expiry[df_selected_expiry['OI'] > 0].copy()
    if df_selected_expiry_oi.empty:
        st.error("Nessun Open Interest per questa scadenza: impossibile calcolare le metriche.")
        st.stop()

    with st.spinner("Calcolo metriche per la scadenza..."):
        gex_metrics      = calculate_gex_metrics(df_selected_expiry_oi, spot_price, risk_free_rate, dividend_yield)
        oi_metrics       = calculate_oi_walls(df_selected_expiry_oi, spot_price)
        vol_metrics      = calculate_volume_profile(df_selected_expiry, spot_price)
        activity_metrics = calculate_activity_ratio(df_selected_expiry, spot_price)
        max_pain_strike, df_payouts = calculate_max_pain(df_selected_expiry_oi)
        pc_ratios        = calculate_pc_ratios(df_selected_expiry_oi)
        expected_move    = calculate_expected_move(df_selected_expiry_oi, spot_price)
        dex_metrics      = calculate_dex_metrics(df_selected_expiry_oi, spot_price)
        vex_metrics      = calculate_vex_metrics(df_selected_expiry_oi, spot_price, risk_free_rate, dividend_yield)

    tab_summary, tab_gex, tab_vex_dex, tab_oi_vol, tab_stats, tab_vol_surf = st.tabs([
        '📋 Summary', '📊 Gamma (GEX)', '🧩 Vanna & Delta (VEX/DEX)',
        '🎯 Support/Res (OI & Vol)', '📉 Stats', '📈 Vol Surface'
    ])

    # ========================= TAB SUMMARY =========================
    with tab_summary:
        st.header(f"Executive Summary per {selected_expiry_label}")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Spot Price", f"{spot_price:.2f}")
        _net_gex_m = gex_metrics['total_net_gex'] / 1_000_000
        col2.metric(
            "Net GEX (Scadenza)", f"€{_net_gex_m:.2f} M",
            delta=f"{_net_gex_m:+.2f} M ({'SHORT γ' if _net_gex_m < 0 else 'LONG γ'})",
            delta_color="inverse"
        )
        col3.metric("Net VEX (Scadenza)", f"€{vex_metrics['total_net_vex'] / 1_000:.2f} K")
        col4.metric("🛡️ Put Wall", f"{oi_metrics['put_wall_strike']:.0f}" if oi_metrics['put_wall_strike'] else "N/A")
        col5.metric("🛑 Call Wall", f"{oi_metrics['call_wall_strike']:.0f}" if oi_metrics['call_wall_strike'] else "N/A")
        col6.metric("📍 Max Pain", f"{max_pain_strike:.0f}" if max_pain_strike else "N/A")

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### Profilo GEX")
            st.plotly_chart(create_gex_profile_chart(
                gex_metrics['df_gex_profile'], spot_price, gex_metrics['gamma_switch_point'], selected_expiry_label
            ), width="stretch", key="summary_gex")
        with col2:
            st.markdown("#### Distribuzione OI")
            st.plotly_chart(create_oi_profile_chart(
                oi_metrics['df_oi_profile'], spot_price, selected_expiry_label
            ), width="stretch", key="summary_oi")
        with col3:
            st.markdown("#### Distribuzione Volumi")
            st.plotly_chart(create_volume_profile_chart(
                vol_metrics['df_vol_profile'], spot_price, selected_expiry_label
            ), width="stretch", key="summary_vol")

    # ========================= TAB GEX =========================
    with tab_gex:
        st.header(f"Analisi Gamma (GEX) per {selected_expiry_label}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Net GEX", f"€{gex_metrics['total_net_gex'] / 1_000_000:.2f} M")
        col2.metric("Gamma Flip (γ=0)", f"{gex_metrics['gamma_switch_point']:.2f}" if gex_metrics['gamma_switch_point'] is not None else "N/A")
        col3.metric("Spot − Gamma Flip", f"{gex_metrics['spot_switch_delta']:+.2f}" if gex_metrics['spot_switch_delta'] is not None else "N/A")
        st.plotly_chart(create_gex_profile_chart(
            gex_metrics['df_gex_profile'], spot_price, gex_metrics['gamma_switch_point'], selected_expiry_label
        ), width="stretch", key="gex_tab")

    # ========================= TAB VEX/DEX =========================
    with tab_vex_dex:
        st.header(f"Analisi Vanna & Delta (VEX/DEX) per {selected_expiry_label}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Net DEX", f"€{dex_metrics['total_net_dex'] / 1_000_000:.2f} M")
        col2.metric("Total Net VEX", f"€{vex_metrics['total_net_vex'] / 1_000:.2f} K")
        col3.metric("Vanna Flip", f"{vex_metrics['vanna_switch_point']:.2f}" if vex_metrics['vanna_switch_point'] is not None else "N/A")
        col4.metric("Spot − Vanna Flip", f"{spot_price - vex_metrics['vanna_switch_point']:+.2f}" if vex_metrics['vanna_switch_point'] is not None else "N/A")
        st.divider()
        col_dex, col_vex = st.columns(2)
        with col_dex:
            st.markdown("#### Profilo DEX")
            st.plotly_chart(create_dex_profile_chart(
                dex_metrics['df_dex_profile'], spot_price, selected_expiry_label
            ), width="stretch", key="dex_tab")
        with col_vex:
            st.markdown("#### Profilo VEX")
            st.plotly_chart(create_vex_profile_chart(
                vex_metrics['df_vex_profile'], spot_price, vex_metrics['vanna_switch_point'], selected_expiry_label
            ), width="stretch", key="vex_tab")

    # ========================= TAB OI/VOL =========================
    with tab_oi_vol:
        st.header(f"Supporti e Resistenze (OI & Volumi) per {selected_expiry_label}")
        col1, col2 = st.columns(2)
        col1.metric("🛡️ Put Wall", f"{oi_metrics['put_wall_strike']:.0f}" if oi_metrics['put_wall_strike'] else "N/A", help=f"OI: {oi_metrics['put_wall_oi']:,.0f}")
        col2.metric("🛑 Call Wall", f"{oi_metrics['call_wall_strike']:.0f}" if oi_metrics['call_wall_strike'] else "N/A", help=f"OI: {oi_metrics['call_wall_oi']:,.0f}")
        st.plotly_chart(create_oi_profile_chart(oi_metrics['df_oi_profile'], spot_price, selected_expiry_label), width="stretch", key="oi_tab")
        st.divider()
        st.plotly_chart(create_volume_profile_chart(vol_metrics['df_vol_profile'], spot_price, selected_expiry_label), width="stretch", key="vol_tab")
        st.divider()
        st.plotly_chart(create_drift_arrow_chart(activity_metrics['drift_score'], spot_price, selected_expiry_label), width="stretch", key="drift_arrow")
        st.plotly_chart(create_activity_ratio_chart(activity_metrics['df_activity_profile'], spot_price, selected_expiry_label), width="stretch", key="drift_detail")

    # ========================= TAB STATS =========================
    with tab_stats:
        st.header(f"Modelli Statistici per {selected_expiry_label}")
        col1, col2, col3 = st.columns(3)
        col1.metric("📍 Max Pain Strike", f"{max_pain_strike:.0f}" if max_pain_strike else "N/A")
        col2.metric("P/C Ratio (OI)", f"{pc_ratios['pc_oi_ratio']:.3f}" if pd.notna(pc_ratios['pc_oi_ratio']) else "N/A")
        col3.metric("P/C Ratio (Volume)", f"{pc_ratios['pc_vol_ratio']:.3f}" if pd.notna(pc_ratios['pc_vol_ratio']) else "N/A")
        em = expected_move
        if em['move'] is not None:
            col1, col2, col3 = st.columns(3)
            col1.metric("Banda Superiore Attesa", f"{em['upper_band']:.2f}")
            col2.metric("Banda Inferiore Attesa", f"{em['lower_band']:.2f}")
            col3.metric("Movimento Atteso (+/-)", f"{em['move']:.2f}", help=f"IV ATM: {em['iv_atm']:.2%}")
        else:
            st.warning("Impossibile calcolare l'Expected Move (IV ATM mancante).")
        st.divider()
        st.plotly_chart(create_max_pain_chart(df_payouts, max_pain_strike, selected_expiry_label), width="stretch", key="max_pain")

    # ========================= TAB VOL SURFACE =========================
    with tab_vol_surf:
        st.header("Superficie di Volatilità (tutte le scadenze)")
        st.caption(
            "Calcolata su richiesta: deriva la IV per TUTTE le scadenze presenti nel testo "
            "incollato (può richiedere qualche secondo in più della singola scadenza)."
        )
        if st.button("Calcola superficie 3D"):
            with st.spinner("Derivazione IV su tutte le scadenze e interpolazione..."):
                df_all_enriched, n_disc_all = enrich_with_greeks(
                    df_raw, spot_price, analysis_date, risk_free_rate, dividend_yield, contract_multiplier
                )
                if n_disc_all > 0:
                    st.warning(f"{n_disc_all} righe totali escluse per Settle non invertibile.")
                min_delta = st.slider("Profondità OTM: |Δ| minimo mostrato", 0.01, 0.40, 0.05, 0.01)
                st.plotly_chart(create_volatility_surface_3d(df_all_enriched, min_delta=min_delta), width="stretch", key="vol_surf")
        else:
            st.info("Premi il bottone per calcolare (elabora tutte le scadenze del testo incollato).")

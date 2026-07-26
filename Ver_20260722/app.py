# File: app.py
#
# [VERSIONE v2 - CON ANALISI VEX/DEX]
# - Include tutte le funzionalità originali (GEX, OI, Stats, Drift, Volatility Surface).
# - NUOVO: Analisi Delta Exposure (DEX) e Vanna Exposure (VEX) con tab dedicato.
# - AGGIORNATO: Export JSON con nodi 'delta_analysis' e 'vanna_analysis'.
# - AGGIORNATA: Architettura a 6 tab.
# -----------------------------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import datetime as dt
import json
import math

# --- Importa i nostri moduli custom ---
from data_module import parse_cboe_csv
from calculations_module import (
    calculate_gex_metrics,
    calculate_oi_walls,
    calculate_max_pain,
    calculate_pc_ratios,
    calculate_expected_move,
    calculate_volume_profile,
    calculate_activity_ratio,
    calculate_dex_metrics,        # NUOVO
    calculate_vex_metrics         # NUOVO
)
from visualization_module import (
    create_gex_profile_chart,
    create_oi_profile_chart,
    create_volatility_surface_3d,
    create_volume_profile_chart,
    create_max_pain_chart,
    create_activity_ratio_chart,
    create_drift_arrow_chart,
    create_dex_profile_chart,     # NUOVO
    create_vex_profile_chart      # NUOVO
)

# -----------------------------------------------------------------------------
# HELPER: SERIALIZZAZIONE JSON
# -----------------------------------------------------------------------------
class NumpyEncoder(json.JSONEncoder):
    """
    Encoder personalizzato per gestire tipi NumPy e Pandas durante
    la conversione in JSON. Fondamentale per evitare errori di tipo.
    """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        elif isinstance(obj, (pd.Timestamp, dt.date, dt.datetime)):
            return obj.isoformat()
        return super(NumpyEncoder, self).default(obj)


def _sanitize_nan(obj):
    """
    Sostituisce NaN/Inf con None (JSON 'null') in modo ricorsivo.
    Lo standard JSON non ammette NaN: senza questo, l'export 'LLM Ready'
    conterrebbe token `NaN` e verrebbe rifiutato da JSON.parse / jq / ecc.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    if isinstance(obj, float):  # np.float64 e' sottoclasse di float -> coperto
        return obj if math.isfinite(obj) else None
    return obj


# -----------------------------------------------------------------------------
# 1. IMPOSTAZIONE PAGINA E TEMA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Kriterion Quant - Options Chain Analyzer",
    page_icon="📊",
    layout="wide",
    # Sidebar aperta all'avvio: contiene i Parametri di modello (risk-free, dividend yield)
    # e il download del JSON. Se restasse chiusa, molti utenti non troverebbero la linguetta.
    initial_sidebar_state="expanded"
)
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    body, .stApp, .stTextInput > div > div > input, .stSelectbox > div > div {
        font-family: 'Inter', sans-serif; color: #e5e7eb;
    }
    div[data-testid="stMetric"] {
        background-color: #111827; border: 1px solid #1f2937;
        border-radius: 8px; padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Il titolo viene aggiornato col ticker del sottostante una volta caricato il file.
_title_slot = st.empty()
_title_slot.title("📊 Options Chain Analyzer")
st.markdown("Powered by **[Kriterion Quant](https://kriterionquant.it/?utm_source=app&utm_medium=streamlit&utm_campaign=chain_analyzer)** — ricerca quantitativa, formazione e segnali operativi · [📄 Guida completa al tool](https://kriterionquant.it/blog/spx-options-chain-analyzer.html?utm_source=app&utm_medium=streamlit) · [🎥 Video demo](https://www.youtube.com/watch?v=ycQm_y4JZTw)")
st.caption(
    "⚠️ **Solo a scopo informativo/educativo — NON è consulenza finanziaria.** "
    "Spot, timestamp e scadenze sono estratti dal CSV caricato e possono essere non aggiornati "
    "o errati: verificali sempre in autonomia. Nessuna garanzia sui risultati. "
    "Le letture su posizionamento (GEX/DEX/VEX, Gamma/Vanna Flip, Walls) si basano su "
    "ipotesi di modello e non rappresentano posizioni realmente osservate."
)

with st.expander("📖 Glossario dei termini (parti da qui se sei alle prime armi)", expanded=False):
    st.markdown(
        """
**Le basi**
- **Opzione** — contratto che dà il diritto (non l'obbligo) di comprare o vendere il sottostante a un prezzo fissato entro una data.
- **Call / Put** — opzione che guadagna se il prezzo *sale* (call) o *scende* (put).
- **Sottostante / Spot** — lo strumento su cui è scritta l'opzione (indice, ETF o azione) e il suo prezzo attuale.
- **Strike** — il prezzo prefissato dell'opzione.
- **Scadenza / DTE** — la data di scadenza; *DTE* = giorni che mancano ad essa (*Days To Expiry*).
- **ITM / ATM / OTM** — opzione *dentro* i soldi (ha valore), *alla pari* (strike ≈ spot), *fuori* dai soldi (senza valore intrinseco).
- **Moneyness** — quanto lo strike è lontano dallo spot (Strike ÷ Spot).

**Chi muove il mercato**
- **Dealer / Market maker** — chi fa i prezzi delle opzioni. Vende e compra opzioni al pubblico e, per non rischiare, copre ("hedgia") comprando/vendendo il sottostante. Questa copertura influenza i prezzi.
- **Hedging** — l'operazione di copertura del rischio.

**Attività e posizionamento**
- **Open Interest (OI)** — numero di contratti *aperti* su uno strike: il posizionamento *accumulato*.
- **Volume** — quanti contratti sono stati scambiati *oggi*.
- **P/C Ratio** — rapporto put/call (di OI o volume): >1 = più put (difensivo), <1 = più call (ottimista).

**Le "greche" (sensibilità dell'opzione)**
- **Delta** — quanto si muove il prezzo dell'opzione se il sottostante si muove di 1 (≈ probabilità di finire ITM). Call: 0→+1; Put: −1→0.
- **Gamma** — quanto cambia il *delta* quando il sottostante si muove: misura la "reattività" della copertura.
- **Vanna** — quanto cambia il *delta* quando cambia la *volatilità*.

**Le metriche di questa dashboard**
- **GEX (Gamma Exposure)** — copertura gamma aggregata dei dealer. Dice se il mercato viene *frenato* (GEX positivo, "long gamma") o *amplificato* (GEX negativo, "short gamma").
- **Gamma Flip / zero-gamma** — il prezzo che separa i due regimi: sopra = più stabile, sotto = più volatile. Fa spesso da **attrattore**.
- **DEX / VEX** — esposizione aggregata di *delta* e *vanna* dell'open interest (posizionamento del mercato, non dei dealer). **Vanna Flip** = livello dove la VEX netta cambia segno.
- **Put Wall / Call Wall** — strike con più OI vicino al prezzo: possibili **supporto** e **resistenza**, e calamite per il prezzo.
- **Max Pain** — strike dove scadrebbero senza valore più opzioni: teorico punto di gravitazione a scadenza.
- **Expected Move** — ampiezza di movimento attesa entro la scadenza (~68% di probabilità di restare nella banda).

**Volatilità**
- **Volatilità Implicita (IV)** — quanto movimento il mercato *si aspetta*, in % annualizzata. Non indica la direzione. Alta = opzioni care; bassa = opzioni economiche.
- **Skew** — differenza di IV tra strike: di solito le put OTM costano di più (protezione al ribasso).
- **Term structure** — come cambia la IV tra scadenze brevi e lunghe.
- **Pinning** — tendenza del prezzo a "incollarsi" agli strike molto carichi verso la scadenza.
        """
    )

# -----------------------------------------------------------------------------
# 2. LOGICA DI CARICAMENTO E CACHING DEI DATI
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# PARAMETRI DI MODELLO (sidebar) — devono esistere PRIMA del caricamento dati,
# perche' entrano nel calcolo di Vanna/VEX e dei livelli di Flip.
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Parametri di modello")
    st.caption(
        "Questi due valori incidono **solo** su Vanna/VEX e sui livelli di Flip "
        "(GEX, DEX, OI, Max Pain, Expected Move e i Wall non ne risentono).\n\n"
        "I default sono calibrati su un **indice azionario USA (tipo SPX)**: "
        "**modificali in base allo strumento che stai analizzando.** Inserisci il "
        "*dividend yield* effettivo del sottostante — **0 se non paga dividendi** — "
        "e il *tasso risk-free* corrente coerente con la valuta e con l'orizzonte "
        "della scadenza analizzata."
    )
    risk_free_rate = st.number_input(
        "Risk-free rate (% annuo)",
        min_value=-5.0, max_value=25.0, value=4.5, step=0.10, format="%.2f",
        help="Tasso privo di rischio annualizzato. Default 4.5% (USD)."
    ) / 100.0
    dividend_yield = st.number_input(
        "Dividend yield (% annuo)",
        min_value=0.0, max_value=25.0, value=1.3, step=0.10, format="%.2f",
        help="Rendimento da dividendi annuo del sottostante. Default 1.3% (SPX). Metti 0 se non paga dividendi."
    ) / 100.0
    st.divider()
    st.markdown("**📈 Kriterion Quant** — questo tool è gratuito e open source. Sul sito trovi la guida completa al tool, la ricerca quantitativa e il servizio di segnali operativi: **[kriterionquant.it](https://kriterionquant.it/?utm_source=app&utm_medium=streamlit&utm_campaign=chain_analyzer_sidebar)**")


@st.cache_data
def load_data(uploaded_file, risk_free_rate, dividend_yield):
    try:
        df_processed, spot_price, data_timestamp, underlying = parse_cboe_csv(
            uploaded_file, risk_free_rate=risk_free_rate, dividend_yield=dividend_yield
        )
        if df_processed is None:
            return None, None, None, None
        return df_processed, spot_price, data_timestamp, underlying
    except Exception as e:
        st.error("Errore irreversibile durante il parsing del file. Verifica che sia un CSV CBOE valido.")
        print(f"[app.load_data] {e}")
        return None, None, None, None


uploaded_file = st.file_uploader("Carica il file CSV della CBOE Options Chain", type=["csv"])
df_processed, spot_price, data_timestamp, underlying = (None, None, None, None)
if uploaded_file is not None:
    df_processed, spot_price, data_timestamp, underlying = load_data(
        uploaded_file, risk_free_rate, dividend_yield
    )
    if underlying:
        _title_slot.title(f"📊 {underlying} Options Chain Analyzer")
else:
    st.info("In attesa del caricamento del file CSV...")

# -----------------------------------------------------------------------------
# 3. CORPO PRINCIPALE DELL'APP
# -----------------------------------------------------------------------------
if df_processed is not None and spot_price is not None and np.isfinite(spot_price) and spot_price > 0:

    # --- 3.1. Barra dei Controlli (Selettore Scadenza) ---
    # Etichetta scadenza deterministica (weekday inglese, indipendente dal locale del server).
    _WEEKDAYS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    def _expiry_label(d):
        ts = pd.Timestamp(d)
        return f"{ts.strftime('%Y-%m-%d')} ({_WEEKDAYS_EN[ts.weekday()]})"

    unique_expirations = sorted(df_processed['Expiration Date'].dropna().unique())
    expiry_options_map = {_expiry_label(date): date for date in unique_expirations}

    if not expiry_options_map:
        st.error("Nessuna scadenza valida trovata nel file.")
        st.stop()

    df_expiry_oi = df_processed.dropna(subset=['Expiration Date']).groupby('Expiration Date')['OI'].sum()
    if df_expiry_oi.empty:
        st.error("Impossibile interpretare le date di scadenza dal file.")
        st.stop()
    default_expiry_label = _expiry_label(df_expiry_oi.idxmax())

    selected_expiry_label = st.selectbox(
        'Seleziona la Scadenza:', options=expiry_options_map.keys(),
        index=list(expiry_options_map.keys()).index(default_expiry_label)
    )
    selected_expiry_date = expiry_options_map[selected_expiry_label]

    # --- 3.2. Filtra Dati per Scadenza ---
    df_selected_expiry = df_processed[df_processed['Expiration Date'] == selected_expiry_date].copy()

    # --- 3.3. Calcola TUTTI i KPI (una sola volta) ---
    with st.spinner("Calcolo metriche per la scadenza..."):
        gex_metrics      = calculate_gex_metrics(df_selected_expiry, spot_price,
                                                 risk_free_rate, dividend_yield)
        oi_metrics       = calculate_oi_walls(df_selected_expiry, spot_price)
        vol_metrics      = calculate_volume_profile(df_selected_expiry, spot_price)
        activity_metrics = calculate_activity_ratio(df_selected_expiry, spot_price)
        max_pain_strike, df_payouts = calculate_max_pain(df_selected_expiry)
        pc_ratios        = calculate_pc_ratios(df_selected_expiry)
        expected_move    = calculate_expected_move(df_selected_expiry, spot_price)
        # --- NUOVI CALCOLI ---
        dex_metrics      = calculate_dex_metrics(df_selected_expiry, spot_price)
        vex_metrics      = calculate_vex_metrics(df_selected_expiry, spot_price,
                                                 risk_free_rate, dividend_yield)

    # =========================================================================
    # PREPARAZIONE EXPORT JSON
    # =========================================================================
    export_data = {
        "metadata": {
            "application":         "Kriterion Quant - Options Chain Analyzer",
            "underlying":          underlying,
            "export_date":         dt.datetime.now().isoformat(),
            "analyzed_expiry":     selected_expiry_label,
            "spot_price":          spot_price,
            "data_timestamp_file": str(data_timestamp),
            "model_params": {
                "risk_free_rate": risk_free_rate,
                "dividend_yield": dividend_yield,
                "note": "Usati solo per Vanna/VEX e per i livelli di Gamma/Vanna Flip."
            },
            "disclaimer": (
                "Solo a scopo informativo/educativo, non consulenza finanziaria. "
                "GEX usa la convenzione dealer long-call/short-put (segno put invertito). "
                "DEX e VEX sono esposizioni aggregate dell'open interest (delta/vanna per OI), "
                "NON esposizioni dei dealer: misurano il posizionamento direzionale/di vanna "
                "dell'OI, non 'cosa devono fare i dealer'. 'Gamma Flip' e 'Vanna Flip' sono i livelli "
                "di prezzo dove l'esposizione netta gamma/vanna, ricalcolata al variare dello spot, "
                "cambia segno (zero-gamma level). I 'Wall' sono le "
                "massime concentrazioni di OI entro +/-10% dallo spot (possibili, non garantiti, "
                "livelli di supporto/resistenza)."
            )
        },
        "market_summary": {
            "max_pain":               max_pain_strike,
            "put_call_ratio_oi":      pc_ratios['pc_oi_ratio'],
            "put_call_ratio_vol":     pc_ratios['pc_vol_ratio'],
            "expected_move_value":    expected_move['move'],
            "expected_move_range":    [expected_move['lower_band'], expected_move['upper_band']],
            "implied_vol_atm":        expected_move['iv_atm']
        },
        "gamma_analysis": {
            "total_net_gex":         gex_metrics['total_net_gex'],
            "gamma_switch_point":    gex_metrics['gamma_switch_point'],
            "spot_switch_delta":     gex_metrics['spot_switch_delta'],
            "gex_profile_data":      gex_metrics['df_gex_profile'].to_dict(orient='records')
        },
        "delta_analysis": {
            # DEX totale per la scadenza selezionata (somma algebrica di tutte le opzioni)
            "total_net_dex":         dex_metrics['total_net_dex'],
            # Profilo completo per strike: utile all'LLM per identificare i nodi chiave
            "dex_profile_data":      dex_metrics['df_dex_profile'].to_dict(orient='records')
        },
        "vanna_analysis": {
            # VEX totale: esposizione vanna aggregata dell'OI a una variazione +1% di vol
            "total_net_vex":         vex_metrics['total_net_vex'],
            # Vanna Flip: livello (zero-vanna, ricalcolato al variare dello spot) dove la vanna netta cambia segno
            "vanna_switch_point":    vex_metrics.get('vanna_switch_point', None),
            # Profilo completo per strike
            "vex_profile_data":      vex_metrics['df_vex_profile'].to_dict(orient='records')
        },
        "levels_support_resistance": {
            "put_wall_strike":       oi_metrics['put_wall_strike'],
            "put_wall_oi":           oi_metrics['put_wall_oi'],
            "call_wall_strike":      oi_metrics['call_wall_strike'],
            "call_wall_oi":          oi_metrics['call_wall_oi'],
            "oi_structure":          oi_metrics['df_oi_profile'].to_dict(orient='records')
        },
        "drift_analysis": {
            "vwas_drift_score":      activity_metrics['drift_score'],
            "drift_bias":            "BULLISH" if activity_metrics['drift_score'] > spot_price else "BEARISH",
            "volume_structure":      vol_metrics['df_vol_profile'].to_dict(orient='records'),
            "activity_ratios":       activity_metrics['df_activity_profile'].to_dict(orient='records')
        }
    }

    json_string = json.dumps(_sanitize_nan(export_data), cls=NumpyEncoder, indent=4)

    # --- 3.4. Architettura Tab (6 tab) ---
    tab_summary, tab_gex, tab_vex_dex, tab_oi_vol, tab_stats, tab_vol_surf = st.tabs([
        '📋 Summary',
        '📊 Gamma (GEX)',
        '🧩 Vanna & Delta (VEX/DEX)',
        '🎯 Support/Res (OI & Vol)',
        '📉 Stats',
        '📈 Vol Surface'
    ])

    # -----------------------------------------------------------------
    # SIDEBAR: Download Button
    # -----------------------------------------------------------------
    with st.sidebar:
        st.divider()
        st.header("📥 Export Dati")
        st.download_button(
            label="Scarica JSON Analisi (LLM Ready)",
            data=json_string,
            file_name=(
                f"kriterion_{str(underlying).lower()}_analysis_"
                f"{selected_expiry_label.split()[0]}.json"
            ),
            mime="application/json",
            help="Scarica un file JSON strutturato con tutti i calcoli (GEX, DEX, VEX, OI, Drift, Max Pain) per la scadenza selezionata."
        )

    # =================================================================
    # TAB 0: SUMMARY DASHBOARD
    # =================================================================
    with tab_summary:
        st.header(f"Executive Summary per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Un'opzione è un contratto che dà il diritto di comprare (*call*) o vendere (*put*) il sottostante a un prezzo prefissato (lo *strike*) entro una data (la *scadenza*). Chi vende molte opzioni — di solito i *market maker*, qui chiamati "dealer" — per non rischiare deve continuamente comprare e vendere il sottostante man mano che il prezzo si muove. Questo aggiustamento lascia tracce sul mercato: le metriche qui provano a stimarle. Questa è la schermata di riepilogo.

**Le caselle in alto.**
- **Spot Price** — il prezzo attuale del sottostante, il riferimento per tutto il resto.
- **Net GEX** — il "clima" atteso: **negativo (SHORT γ)** = movimenti più *amplificati*, giornate nervose e direzionali; **positivo (LONG γ)** = movimenti *smorzati*, mercato più tranquillo e laterale.
- **Net VEX** — quanto il posizionamento reagisce se la volatilità cambia dell'1%.
- **Put Wall / Call Wall** — gli strike con più contratti aperti *vicino al prezzo*: possibili zone di **supporto** (sotto) e **resistenza** (sopra).
- **Max Pain** — lo strike verso cui la scadenza tende teoricamente a "gravitare".

**Come usarla.** Guarda prima il **Net GEX**: se è positivo aspettati oscillazioni contenute e rimbalzi sui livelli; se è negativo aspettati movimenti più ampi e possibili accelerazioni. Poi osserva dove sono i **Wall** e il **Max Pain**: spesso il prezzo tende a restare "catturato" tra questi livelli, soprattutto avvicinandosi alla scadenza. Le altre tab spiegano ogni pezzo in dettaglio.

**⚠️ Attenzione.** Sono stime basate su ipotesi di modello, non certezze né consigli operativi: usale come *contesto* insieme alla tua analisi.
                """
            )

        st.subheader("Key Metrics Grid (per la scadenza selezionata)")
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        col1.metric(label="Spot Price", value=f"{spot_price:.2f}")
        _net_gex_b = gex_metrics['total_net_gex'] / 1_000_000_000
        col2.metric(
            label="Net GEX (Scadenza)",
            value=f"${_net_gex_b:.2f} B",
            # Delta numerico con segno: cosi' colore e freccia seguono il segno (SHORT vs LONG gamma)
            delta=f"{_net_gex_b:+.2f} B ({'SHORT γ' if _net_gex_b < 0 else 'LONG γ'})",
            delta_color="inverse",
            help="Negativo = dealers SHORT gamma (regime destabilizzante); positivo = LONG gamma (stabilizzante)."
        )
        col3.metric(
            label="Net VEX (Scadenza)",
            value=f"${vex_metrics['total_net_vex'] / 1_000_000:.2f} M",
            help="Esposizione aggregata dell'open interest a una variazione +1% della Volatilità Implicita (non è esposizione dei dealer)."
        )
        col4.metric(
            label="🛡️ Put Wall",
            value=f"{oi_metrics['put_wall_strike']:.0f}" if oi_metrics['put_wall_strike'] else "N/A",
            help="Strike con max OI put entro ±10% dallo spot: possibile (non garantito) supporto."
        )
        col5.metric(
            label="🛑 Call Wall",
            value=f"{oi_metrics['call_wall_strike']:.0f}" if oi_metrics['call_wall_strike'] else "N/A",
            help="Strike con max OI call entro ±10% dallo spot: possibile (non garantita) resistenza."
        )
        col6.metric(
            label="📍 Max Pain",
            value=f"{max_pain_strike:.0f}" if max_pain_strike else "N/A"
        )

        st.divider()
        st.subheader("Charts Dashboard (GEX, OI, Volume)")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### Profilo GEX")
            fig_gex = create_gex_profile_chart(
                gex_metrics['df_gex_profile'], spot_price,
                gex_metrics['gamma_switch_point'], selected_expiry_label
            )
            st.plotly_chart(fig_gex, width="stretch", key="summary_gex_chart")
        with col2:
            st.markdown("#### Distribuzione OI")
            fig_oi = create_oi_profile_chart(
                oi_metrics['df_oi_profile'], spot_price, selected_expiry_label
            )
            st.plotly_chart(fig_oi, width="stretch", key="summary_oi_chart")
        with col3:
            st.markdown("#### Distribuzione Volumi")
            fig_vol = create_volume_profile_chart(
                vol_metrics['df_vol_profile'], spot_price, selected_expiry_label
            )
            st.plotly_chart(fig_vol, width="stretch", key="summary_vol_chart")

    # =================================================================
    # TAB 1: GAMMA ANALYSIS
    # =================================================================
    with tab_gex:
        st.header(f"Analisi Gamma (GEX) per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Il *gamma* misura quanto rapidamente cambia la copertura che i dealer devono avere quando il prezzo si muove. Immagina che i dealer abbiano venduto molte opzioni: per restare neutrali ricomprano o rivendono il sottostante in continuazione. La **GEX** somma questa "spinta di copertura" su tutta la catena e ci dice se, nel complesso, i dealer **frenano** o **amplificano** i movimenti.

**I due regimi.**
- **LONG gamma (Net GEX positivo, prezzo SOPRA il Flip):** i dealer comprano quando il mercato scende e vendono quando sale → **frenano** il prezzo. Risultato: oscillazioni contenute, il mercato tende a tornare verso i livelli, i grandi cluster di gamma fanno da **supporto/resistenza** e da **calamita** (il prezzo viene "pinnato" lì, soprattutto verso scadenza).
- **SHORT gamma (Net GEX negativo, prezzo SOTTO il Flip):** i dealer fanno il contrario, vendono sui ribassi e comprano sui rialzi → **amplificano**. Risultato: movimenti più ampi, trend che si autoalimentano, volatilità più alta.

**Insight operativi.**
- **Gamma Flip = spartiacque e attrattore.** È la soglia tra i due regimi: sopra, mercato "calmo"; sotto, mercato "esplosivo". Il prezzo tende a **gravitare** verso il Flip e verso i livelli molto carichi di gamma.
- **Livelli ad alta GEX = supporti/resistenze *e* magneti.** Le barre più lunghe segnalano dove la copertura dei dealer è più intensa: lì il prezzo trova spesso freno e viene attratto.
- **Rotture decise (breakout).** Se il prezzo *rompe con forza* un grande livello di gamma o scende **sotto il Flip**, l'effetto stabilizzante svanisce e si può passare a un "gamma unwind": i dealer, prima freno, ora inseguono il movimento → accelerazione rapida e volatilità in aumento. Le rotture al ribasso sotto il Flip sono le più violente.

**Cosa guardare nel grafico.** Barre per strike (verde = gamma positivo, rosso = negativo), linea **blu** = spot, linea **gialla tratteggiata** = Gamma Flip. Conta soprattutto *da che parte del Flip* sei e *dove* sono le barre più grandi.

**⚠️ Attenzione.** Sono tendenze statistiche, non regole: i livelli possono essere attraversati. Le singole barre vicino allo spot oscillano molto; il segnale affidabile è il **segno del Net GEX** e la posizione dello **spot rispetto al Flip**. Convenzione dealer: long call / short put.
                """
            )

        col1, col2, col3 = st.columns(3)
        col1.metric(
            label="Net GEX",
            value=f"${gex_metrics['total_net_gex'] / 1_000_000_000:.2f} B",
            help="Somma dell'esposizione gamma dei dealer (convenzione long-call/short-put)."
        )
        col2.metric(
            label="Gamma Flip (γ=0)",
            value=f"{gex_metrics['gamma_switch_point']:.2f}" if gex_metrics['gamma_switch_point'] is not None else "N/A",
            help="Zero-gamma: livello dove il gamma netto dei dealer (ricalcolato al variare dello spot) cambia segno."
        )
        col3.metric(
            label="Spot − Gamma Flip",
            value=f"{gex_metrics['spot_switch_delta']:+.2f}" if gex_metrics['spot_switch_delta'] is not None else "N/A",
            help="Distanza dello spot dal Gamma Flip. >0 = spot sopra il flip (tipicamente regime long-gamma)."
        )
        # Riusa la figura GEX già costruita nel tab Summary
        fig_gex_tab = create_gex_profile_chart(
            gex_metrics['df_gex_profile'], spot_price,
            gex_metrics['gamma_switch_point'], selected_expiry_label
        )
        st.plotly_chart(fig_gex_tab, width="stretch", key="gex_tab_chart")

    # =================================================================
    # TAB 2: VANNA & DELTA (VEX/DEX) — NUOVO
    # =================================================================
    with tab_vex_dex:
        st.header(f"Analisi Vanna & Delta (VEX/DEX) per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Ogni opzione ha un *delta* (quanto guadagna/perde se il sottostante si muove di 1 punto) e una *vanna* (quanto cambia quel delta se la volatilità sale o scende). Qui li sommiamo su tutti i contratti aperti (*open interest*) per fotografare **come è posizionato il mercato**.

- **DEX (Delta) — il posizionamento direzionale.** **DEX > 0** = tra i contratti aperti prevale il delta delle call → posizionamento con tono più **rialzista**; **DEX < 0** = prevale il delta delle put → tono più **ribassista/difensivo**.
- **VEX (Vanna) — la sensibilità alla volatilità.** Ti dice come cambierebbe l'esposizione se la volatilità si muovesse. Il **Vanna Flip** è il prezzo che separa i due regimi.

**Insight operativi.**
- **La vanna è il motore dei "melt-up" a bassa volatilità.** Quando i mercati salgono lenti e la volatilità *scende*, la vanna tende a spingere altri acquisti di copertura → il rialzo si autoalimenta con poca volatilità. Al contrario, quando la volatilità *sale* (paura), lo stesso meccanismo si inverte e alimenta la discesa.
- **Il Vanna Flip fa da spartiacque:** sopra e sotto, l'effetto della volatilità sul posizionamento cambia segno. Utile leggerlo *insieme* al Gamma Flip per capire il regime.
- **DEX come conferma di contesto:** un DEX molto negativo con volatilità in aumento segnala un mercato coperto/difensivo; un DEX positivo con volatilità che scende accompagna spesso le fasi di risalita tranquilla.

**Cosa guardare nei grafici.** Barre per strike; linea **blu** = spot; linea **gialla tratteggiata** (VEX) = Vanna Flip. Osserva dove si concentrano le barre più lunghe rispetto allo spot.

**⚠️ Attenzione — importante.** A differenza della GEX, **DEX e VEX qui NON applicano una convenzione di segno "dealer"**: sono somme dell'esposizione dell'open interest. Non vanno letti come "i dealer devono comprare/vendere", ma come **posizionamento aggregato del mercato**. I segni non sono direttamente confrontabili con quelli della tab GEX.
                """
            )

        # --- KPI Row ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            label="Total Net DEX",
            value=f"${dex_metrics['total_net_dex'] / 1_000_000_000:.3f} B",
            help="Delta aggregato dell'OI (call +, put −) × 100 × Spot. >0 = OI net-long delta."
        )
        col2.metric(
            label="Total Net VEX",
            value=f"${vex_metrics['total_net_vex'] / 1_000_000:.2f} M",
            help="Esposizione vanna aggregata dell'OI a una variazione +1% della IV."
        )
        col3.metric(
            label="Vanna Flip",
            value=(
                f"{vex_metrics['vanna_switch_point']:.2f}"
                if vex_metrics['vanna_switch_point'] is not None else "N/A"
            ),
            help="Zero-vanna: livello dove l'esposizione vanna netta (ricalcolata al variare dello spot) cambia segno."
        )
        col4.metric(
            label="Spot − Vanna Flip",
            value=(
                f"{spot_price - vex_metrics['vanna_switch_point']:+.2f}"
                if vex_metrics['vanna_switch_point'] is not None else "N/A"
            ),
            help="Differenza tra Spot e Vanna Flip. Positivo = spot sopra il livello di flip."
        )

        st.divider()

        # --- Grafici DEX e VEX affiancati ---
        col_dex, col_vex = st.columns(2)

        with col_dex:
            st.markdown("#### Profilo DEX (Delta Exposure per Strike)")
            st.caption(
                "Verde = DEX positivo (OI net-long delta) | "
                "Rosso = DEX negativo (OI net-short delta)"
            )
            fig_dex = create_dex_profile_chart(
                dex_metrics['df_dex_profile'], spot_price, selected_expiry_label
            )
            st.plotly_chart(fig_dex, width="stretch", key="dex_tab_chart")

        with col_vex:
            st.markdown("#### Profilo VEX (Vanna Exposure per Strike)")
            st.caption(
                "Viola = VEX positivo | Arancione = VEX negativo "
                "(esposizione vanna aggregata dell'OI, non dei dealer)"
            )
            fig_vex = create_vex_profile_chart(
                vex_metrics['df_vex_profile'], spot_price,
                vex_metrics['vanna_switch_point'], selected_expiry_label
            )
            st.plotly_chart(fig_vex, width="stretch", key="vex_tab_chart")

        st.divider()
        st.markdown("##### Nota Metodologica")
        st.markdown(
            "Il **Vanna** è calcolato analiticamente con la formula chiusa di Black-Scholes "
            "(via `scipy.stats.norm`) usando: IV da CBOE (colonna IV), Strike dal CSV, DTE in anni, "
            f"risk-free rate **{risk_free_rate:.2%}** e dividend yield **{dividend_yield:.2%}** "
            f"(drift r−q), impostabili nella **sidebar → Parametri di modello**. "
            f"⚠️ I default sono calibrati su un indice azionario USA (tipo SPX): "
            f"**adattali allo strumento analizzato** (dividend yield reale, 0 se non paga dividendi, "
            f"e tasso risk-free corretto per valuta e scadenza). "
            "Strike con IV ≤ 0.1% o DTE=0 sono esclusi dal calcolo (Vanna = 0). "
            "Il moltiplicatore **0.01** normalizza la sensitività a una variazione dell'1% di IV. "
            "**Nota:** DEX e VEX sono esposizioni aggregate dell'open interest, non dei dealer."
        )

    # =================================================================
    # TAB 3: SUPPORT/RESISTANCE (OI & Vol)
    # =================================================================
    with tab_oi_vol:
        st.header(f"Supporti e Resistenze (OI & Volumi) per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** L'**Open Interest (OI)** è il numero di contratti *aperti* su ogni strike: è il posizionamento *accumulato* nel tempo. Il **Volume** è invece quanto si è scambiato *oggi*. Dove l'OI è enorme, i dealer hanno molta copertura da gestire proprio lì, e questo tende a influenzare il prezzo.

**Come si legge.**
- **Put Wall** — lo strike con più OI put *vicino al prezzo*: possibile zona di **supporto**.
- **Call Wall** — lo strike con più OI call vicino al prezzo: possibile zona di **resistenza**.
- **Grafici OI e Volumi** — call verso destra (positivo), put verso sinistra (negativo): le barre più lunghe sono i "muri".
- **Sintesi Drift** — il baricentro dei volumi di oggi (call **e** put) rispetto allo spot: a destra = tono rialzista, a sinistra = ribassista.
- **Rapporto Vol/OI** — dove il volume di oggi ha superato l'OI esistente (>1.0): posizionamento *nuovo*, non solo copertura di posizioni vecchie.

**Insight operativi.**
- **I Wall agiscono da supporto/resistenza *e* da calamita.** Un grande muro di OI genera copertura che tende a frenare il prezzo lì, e verso la scadenza lo **attrae** (il classico "pinning" attorno agli strike più carichi).
- **Rottura decisa di un Wall.** Quando il prezzo attraversa con forza un grande muro, spesso **accelera**: la copertura che prima frenava si inverte e i trader riposizionano stop e hedge. Un supporto rotto diventa spesso resistenza (e viceversa).
- **Vol/OI alto = attenzione.** Segnala che qualcuno sta aprendo *nuove* posizioni su quello strike proprio oggi: può anticipare l'importanza futura di quel livello.

**⚠️ Attenzione.** I Wall sono concentrazioni di OI, non muri garantiti: il prezzo può attraversarli. La ricerca è limitata a ±10% dallo spot per non scambiare le coperture profondamente OTM per "supporti" operativi.
                """
            )

        st.subheader("Metriche Open Interest (Posizionamento)")
        col1, col2 = st.columns(2)
        col1.metric(
            label="🛡️ Put Wall",
            value=f"{oi_metrics['put_wall_strike']:.0f}" if oi_metrics['put_wall_strike'] else "N/A",
            help=f"OI: {oi_metrics['put_wall_oi']:,.0f}"
        )
        col2.metric(
            label="🛑 Call Wall",
            value=f"{oi_metrics['call_wall_strike']:.0f}" if oi_metrics['call_wall_strike'] else "N/A",
            help=f"OI: {oi_metrics['call_wall_oi']:,.0f}"
        )
        fig_oi_tab = create_oi_profile_chart(oi_metrics['df_oi_profile'], spot_price, selected_expiry_label)
        st.plotly_chart(fig_oi_tab, width="stretch", key="oi_tab_chart")

        st.divider()
        st.subheader("Metriche Volumi (Attività di Giornata)")
        fig_vol_tab = create_volume_profile_chart(vol_metrics['df_vol_profile'], spot_price, selected_expiry_label)
        st.plotly_chart(fig_vol_tab, width="stretch", key="vol_tab_chart")

        st.divider()
        st.subheader("Analisi Drift (Sintesi e Dettaglio)")
        st.info(
            "La 'Sintesi Drift Volumi' calcola il VWAS (Volume-Weighted Average Strike) su "
            "TUTTO il volume di giornata (call + put) e lo confronta con lo Spot. Freccia a destra "
            "= baricentro dei volumi sopra lo spot (bias rialzista); a sinistra = sotto (bias ribassista)."
        )
        fig_drift_arrow = create_drift_arrow_chart(
            activity_metrics['drift_score'], spot_price, selected_expiry_label
        )
        st.plotly_chart(fig_drift_arrow, width="stretch", key="drift_arrow_chart")

        st.markdown("##### Dettaglio Rapporto Vol/OI")
        st.info(
            "Un rapporto > 1.0 indica che il volume odierno ha superato l'intero Open "
            "Interest esistente, segnalando un'attività insolita."
        )
        fig_drift_detail = create_activity_ratio_chart(
            activity_metrics['df_activity_profile'], spot_price, selected_expiry_label
        )
        st.plotly_chart(fig_drift_detail, width="stretch", key="drift_detail_chart")

    # =================================================================
    # TAB 4: STATISTICAL MODELS
    # =================================================================
    with tab_stats:
        st.header(f"Modelli Statistici per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Tre indicatori di *sentiment* (come è orientato il mercato) e di *ampiezza attesa* del movimento.

**Come si legge.**
- **Max Pain** — lo strike che, a scadenza, farebbe scadere senza valore il maggior numero di opzioni. In teoria è un "punto di gravitazione": chi ha venduto le opzioni ha interesse a che il prezzo finisca lì.
- **P/C Ratio (OI e Volume)** — rapporto put/call. **> 1** = prevalenza di put (tono difensivo/ribassista); **< 1** = prevalenza di call (tono rialzista).
- **Expected Move** — quanto il mercato *si aspetta* che il sottostante si muova (in su o in giù) da qui alla scadenza: è ≈1 deviazione standard, cioè circa **68% di probabilità** di chiudere dentro le due bande. Stimato dalla volatilità implicita At-The-Money.

**Insight operativi.**
- **Max Pain come debole attrattore.** Avvicinandosi alla scadenza, il prezzo tende *statisticamente* a essere richiamato verso il Max Pain (per via dell'hedging di chi ha venduto le opzioni). È una tendenza leggera, non una regola: contano di più i Wall e il Gamma Flip.
- **P/C ratio agli estremi = spunto contrarian.** Un P/C molto alto (troppa paura) o molto basso (troppo ottimismo) spesso precede un'inversione, non una continuazione.
- **Expected Move = righello per aspettative e strike.** Le bande dicono dove il mercato "prezza" la chiusura probabile: utili per calibrare target e per scegliere strike. **Uscire dalle bande** con decisione segnala un movimento oltre l'atteso, di solito accompagnato da un aumento di volatilità.

**Cosa guardare nel grafico.** Max Pain: il payout totale per strike; il **minimo** della curva è lo strike di Max Pain.

**⚠️ Attenzione.** Max Pain è teorico, non una previsione. L'Expected Move assume distribuzione lognormale e volatilità costante fino a scadenza: è una stima, non un limite garantito. Per lo 0DTE viene usato un minimo di 1 giorno, quindi a fine giornata può risultare sovrastimato.
                """
            )

        st.subheader("Metriche Chiave di Posizionamento e Sentiment")
        col1, col2, col3 = st.columns(3)
        col1.metric(
            label="📍 Max Pain Strike",
            value=f"{max_pain_strike:.0f}" if max_pain_strike else "N/A",
            help="Lo strike che causa la massima perdita per i compratori di opzioni a scadenza."
        )
        col2.metric(
            label="P/C Ratio (Open Interest)",
            value=f"{pc_ratios['pc_oi_ratio']:.3f}" if pd.notna(pc_ratios['pc_oi_ratio']) else "N/A",
            help="Sentiment di posizionamento (Put OI / Call OI). > 1 = Bearish"
        )
        col3.metric(
            label="P/C Ratio (Volume)",
            value=f"{pc_ratios['pc_vol_ratio']:.3f}" if pd.notna(pc_ratios['pc_vol_ratio']) else "N/A",
            help="Sentiment di attività (Put Vol / Call Vol). > 1 = Bearish"
        )

        st.subheader("Movimento Atteso (Expected Move)")
        em = expected_move
        if em['move'] is not None:
            col1, col2, col3 = st.columns(3)
            col1.metric(label="Banda Superiore Attesa", value=f"{em['upper_band']:.2f}")
            col2.metric(label="Banda Inferiore Attesa", value=f"{em['lower_band']:.2f}")
            col3.metric(
                label="Movimento Atteso (+/-)",
                value=f"{em['move']:.2f}",
                help=f"Calcolato con IV ATM: {em['iv_atm']:.2%}"
            )
        else:
            st.warning("Impossibile calcolare l'Expected Move (dati IV ATM mancanti).")

        st.divider()
        st.subheader("Grafico Max Pain (Payout Totale a Scadenza)")
        fig_max_pain = create_max_pain_chart(df_payouts, max_pain_strike, selected_expiry_label)
        st.plotly_chart(fig_max_pain, width="stretch", key="max_pain_chart")

    # =================================================================
    # TAB 5: VOLATILITY SURFACE
    # =================================================================
    with tab_vol_surf:
        st.header("Superficie di Volatilità (Tutte le Scadenze)")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** La **Volatilità Implicita (IV)** è quanto movimento il mercato *si aspetta*, ricavato dal prezzo delle opzioni. Non indica la direzione, solo l'ampiezza attesa: IV alta = opzioni care e attese di grandi oscillazioni; IV bassa = opzioni economiche e attese di calma.

**Come è misurata (importante).** La IV è una **volatilità annualizzata**, espressa in **percentuale**. Qui l'asse verticale è in %: **14%** significa che il mercato prezza una deviazione standard annua del ~14%. Valori estremi (100%+) compaiono solo sulle ali molto fuori-the-money, dove le opzioni sono illiquide e la IV è in gran parte *rumore*.

**Filtro sul delta (lo slider sopra il grafico).** Per questo la superficie è filtrata per **delta**: lo slider **|Δ| minimo** esclude le opzioni troppo OTM (delta ~0, intradabili). Alza lo slider per una superficie più **vicina all'ATM e affidabile**; abbassalo (fino a 0.01) per vedere più ali. Il delta misura "quanto OTM" meglio della distanza in strike, perché tiene conto di tempo e volatilità.

**Il grafico.** Asse X = giorni alla scadenza (DTE), asse Y = strike, **altezza/colore = IV in %**. Usa solo opzioni OTM (put sotto lo spot, call sopra).

**Insight operativi.**
- **Skew (lungo gli strike):** di solito le put OTM hanno IV più alta delle call → il mercato paga la protezione al ribasso. Uno **skew ripido** indica nervosismo/domanda di copertura; uno skew piatto indica compiacenza.
- **Term structure (lungo il DTE):** se le scadenze **brevi** hanno IV più alta delle lunghe (*backwardation*) c'è stress o un evento imminente; se le lunghe sono più alte (*contango*, situazione normale) il mercato è calmo.
- **Uso pratico:** IV alta favorisce le strategie che *vendono* premio (con prudenza); IV bassa favorisce quelle che lo *comprano*. Confronta sempre con l'Expected Move nella tab Stats.

**⚠️ Attenzione.** È una superficie **interpolata**: le zone senza dati vengono riempite per continuità e i bordi sono meno affidabili. La IV misura l'*ampiezza* attesa, non la direzione.
                """
            )

        min_delta = st.slider(
            "Profondità OTM: |Δ| minimo mostrato",
            min_value=0.01, max_value=0.40, value=0.05, step=0.01,
            help="Filtra le opzioni per delta. 0.01 = mostra anche le ali profonde (più rumore); "
                 "valori più alti = superficie più vicina all'ATM e più 'tradeable'. "
                 "Le opzioni molto OTM (delta ~0) sono illiquide e con IV inaffidabile."
        )
        with st.spinner("Calcolo e interpolazione superficie 3D in corso..."):
            fig_vol_surf = create_volatility_surface_3d(df_processed, min_delta=min_delta)
            st.plotly_chart(fig_vol_surf, width="stretch", key="vol_surface_chart")

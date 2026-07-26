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
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from euronext_module import (
    parse_euronext_text, enrich_with_greeks, log_significant_volume_events,
    reconcile_log, update_log_fields, log_totali_giornalieri, ricostruisci_storico_totali
)
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

with st.expander("📖 Glossario dei termini (parti da qui se sei alle prime armi)", expanded=False):
    st.markdown(
        """
**Le basi**
- **Opzione** — contratto che dà il diritto (non l'obbligo) di comprare o vendere il sottostante a un prezzo fissato entro una data.
- **Call / Put** — opzione che guadagna se il prezzo *sale* (call) o *scende* (put).
- **Sottostante / Spot** — qui il FTSEMIB, e il suo livello attuale (da inserire tu in sidebar).
- **Strike** — il prezzo prefissato dell'opzione.
- **Scadenza / DTE** — la data di scadenza; *DTE* = giorni che mancano ad essa (*Days To Expiry*). Le opzioni MIBO scadono il terzo venerdì del mese.
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

⚠️ **Specifico di questa app**: Euronext non fornisce Delta/Gamma/Vanna/IV pronti come CBOE. Qui sono **stimati** invertendo Black-Scholes dal prezzo *Settle* di ciascuna opzione: sono ipotesi di modello sopra un modello, non dati di mercato osservati. Usali per farti un'idea, non come dato definitivo.

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
# CARICAMENTO DATI: upload del file CSV Euronext (a blocchi per scadenza)
# -----------------------------------------------------------------------------
st.subheader("1. Carica il file CSV Euronext (opzioni)")
st.caption(
    "Il file che già usi (copiato dall'editor Jupyter dalla pagina opzioni FTSEMIB, con "
    "più scadenze incluse). Usa un export con Open Interest già disponibile (di solito il "
    "giorno successivo alla data di riferimento)."
)
uploaded_file = st.file_uploader("File CSV opzioni", type=["csv", "txt"], key="options_csv")

df_raw, analysis_date = None, None
TOTALI_LOG_PATH = "dati_locali/storico_totali.csv"

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

st.subheader("2. Storico prezzi FTSEMIB (opzionale, per lo spot)")
st.caption(
    "CSV con colonne time,open,high,low,close (una riga per giorno), letto direttamente dal disco: "
    "indica il percorso una volta sola, resta impostato anche cambiando il file opzioni al punto 1 "
    "(non serve più ricaricarlo ogni volta). L'app cerca da sola la chiusura corrispondente alla "
    "data del file opzioni sopra, così non devi ricordarla a memoria per dati passati. Resta comunque "
    "modificabile in sidebar."
)
percorso_prezzi = st.text_input(
    "Percorso file storico prezzi", value=st.session_state.get('percorso_prezzi_default', "INDEX_FTSEMIB_1D.csv"),
    key="percorso_prezzi", help="Percorso relativo alla cartella dell'app, o assoluto."
)
st.session_state['percorso_prezzi_default'] = percorso_prezzi

suggested_spot = None
if percorso_prezzi and analysis_date is not None:
    if os.path.exists(percorso_prezzi):
        try:
            df_prices = pd.read_csv(percorso_prezzi, parse_dates=['time'])
            match = df_prices[df_prices['time'].dt.date == analysis_date.date()]
            if not match.empty:
                suggested_spot = float(match.iloc[0]['close'])
                st.success(f"Spot trovato per {analysis_date.date()}: chiusura {suggested_spot:,.2f} (precompilato in sidebar).")
            else:
                st.warning(f"Nessuna riga per {analysis_date.date()} nello storico: inserisci lo spot a mano in sidebar.")
        except Exception as e:
            st.error(f"Errore nella lettura dello storico prezzi: {e}")
    else:
        st.warning(f"File non trovato: `{percorso_prezzi}` (verifica il percorso, relativo alla cartella da cui hai lanciato l'app).")
elif percorso_prezzi and analysis_date is None:
    st.info("Carica prima il file opzioni: serve la sua data per cercare lo spot corrispondente.")

# -----------------------------------------------------------------------------
# SIDEBAR: parametri di mercato (default FTSEMIB, non SPX)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Parametri di mercato")
    # Se lo storico prezzi ha trovato una corrispondenza, la propone come default;
    # altrimenti resta libero (nessun valore precompilato "fisso" da dimenticare di cambiare).
    # NOTA: si applica solo la PRIMA volta che vediamo QUESTO specifico suggested_spot per
    # questa data (non solo se la chiave non esiste ancora) - cosi' funziona indipendentemente
    # dall'ordine in cui carichi i due file, e non sovrascrive una correzione manuale successiva.
    _spot_key = f"spot_{analysis_date.date() if analysis_date is not None else 'none'}"
    _applied_key = f"_applied_{_spot_key}"
    if suggested_spot is not None and st.session_state.get(_applied_key) != suggested_spot:
        st.session_state[_spot_key] = suggested_spot
        st.session_state[_applied_key] = suggested_spot
    spot_price = st.number_input(
        "Spot FTSEMIB del giorno",
        min_value=0.0, step=1.0, format="%.2f", key=_spot_key,
        help="Precompilato automaticamente se carichi lo storico prezzi (punto 2 sopra), in "
             "qualunque ordine carichi i due file; altrimenti va inserito a mano."
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
    volume_threshold = st.number_input(
        "Soglia volume significativo (contratti)",
        min_value=1, value=100, step=10,
        help="Sopra questa soglia (per singolo strike/scadenza) l'evento viene proposto per il log. "
             "Il notional stimato in € nel log aiuta a giudicare la rilevanza reale anche per strike "
             "deep ITM lontani dallo spot, dove pochi contratti pesano molto di più."
    )
    st.divider()
    st.caption(
        "Questi valori incidono su tutte le esposizioni nozionali (GEX/DEX/VEX) e sui "
        "livelli di Flip. Il risk-free e il dividend yield incidono anche sulla IV derivata."
    )

VOLUME_LOG_PATH = "dati_locali/eventi_volume.csv"
DATI_FOLDER_DEFAULT = "dati"
TOTALI_LOG_PATH = "dati_locali/storico_totali.csv"

if df_raw is not None and spot_price > 0:
    log_totali_giornalieri(df_raw, analysis_date, TOTALI_LOG_PATH, spot=spot_price)

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

    st.subheader("3. Seleziona la scadenza")
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

    tab_summary, tab_gex, tab_vex_dex, tab_oi_vol, tab_stats, tab_vol_surf, tab_eventi, tab_storico = st.tabs([
        '📋 Summary', '📊 Gamma (GEX)', '🧩 Vanna & Delta (VEX/DEX)',
        '🎯 Support/Res (OI & Vol)', '📉 Stats', '📈 Vol Surface', '📋 Eventi Volume', '📈 Andamento Storico'
    ])

    # ========================= TAB SUMMARY =========================
    with tab_summary:
        st.header(f"Executive Summary per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Un'opzione è un contratto che dà il diritto di comprare (*call*) o vendere (*put*) il sottostante a un prezzo prefissato (lo *strike*) entro una data (la *scadenza*). Chi vende molte opzioni — di solito i *market maker*, qui chiamati "dealer" — per non rischiare deve continuamente comprare e vendere il sottostante man mano che il prezzo si muove. Questo aggiustamento lascia tracce sul mercato: le metriche qui provano a stimarle. Questa è la schermata di riepilogo.

**Le caselle in alto.**
- **Spot Price** — il livello FTSEMIB che hai inserito in sidebar, il riferimento per tutto il resto.
- **Net GEX** — il "clima" atteso: **negativo (SHORT γ)** = movimenti più *amplificati*, giornate nervose e direzionali; **positivo (LONG γ)** = movimenti *smorzati*, mercato più tranquillo e laterale.
- **Net VEX** — quanto il posizionamento reagisce se la volatilità cambia dell'1%.
- **Put Wall / Call Wall** — gli strike con più contratti aperti *vicino al prezzo*: possibili zone di **supporto** (sotto) e **resistenza** (sopra).
- **Max Pain** — lo strike verso cui la scadenza tende teoricamente a "gravitare".

**Come usarla.** Guarda prima il **Net GEX**: se è positivo aspettati oscillazioni contenute e rimbalzi sui livelli; se è negativo aspettati movimenti più ampi e possibili accelerazioni. Poi osserva dove sono i **Wall** e il **Max Pain**: spesso il prezzo tende a restare "catturato" tra questi livelli, soprattutto avvicinandosi alla scadenza. Le altre tab spiegano ogni pezzo in dettaglio.

**⚠️ Attenzione.** Qui Delta/Gamma/Vanna sono stimati da Black-Scholes (Euronext non li fornisce), quindi ipotesi di modello sopra un modello. Sono stime, non certezze né consigli operativi: usale come *contesto* insieme alla tua analisi.
                """
            )

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
        st.subheader("Livelli chiave vs Spot (colpo d'occhio)")
        _levels = [
            ("Gamma Flip", gex_metrics['gamma_switch_point']),
            ("Vanna Flip", vex_metrics['vanna_switch_point']),
            ("Put Wall", oi_metrics['put_wall_strike']),
            ("Call Wall", oi_metrics['call_wall_strike']),
            ("Max Pain", max_pain_strike),
        ]
        if expected_move['move'] is not None:
            _levels.append(("Expected Move (banda sup.)", expected_move['upper_band']))
            _levels.append(("Expected Move (banda inf.)", expected_move['lower_band']))

        _rows = []
        for label, level in _levels:
            if level is None:
                _rows.append({"Livello": label, "Prezzo": "N/A", "Distanza (punti)": "N/A", "Distanza (%)": "N/A", "Posizione": "N/A"})
                continue
            dist = spot_price - level
            pct = dist / spot_price * 100
            _rows.append({
                "Livello": label,
                "Prezzo": f"{level:,.0f}",
                "Distanza (punti)": f"{-dist:+,.0f}",
                "Distanza (%)": f"{-pct:+.2f}%",
                "Posizione": "Sopra spot" if level > spot_price else ("Sotto spot" if level < spot_price else "= Spot")
            })
        st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True)
        st.caption(
            "Distanza (%) positiva = il livello è sopra lo spot attuale; negativa = è sotto. "
            "Utile per un confronto rapido tra tutti i livelli chiave senza dover leggere ogni grafico singolarmente."
        )

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

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Il *gamma* misura quanto rapidamente cambia la copertura che i dealer devono avere quando il prezzo si muove. Immagina che i dealer abbiano venduto molte opzioni: per restare neutrali ricomprano o rivendono il sottostante in continuazione. La **GEX** somma questa "spinta di copertura" su tutta la catena e ci dice se, nel complesso, i dealer **frenano** o **amplificano** i movimenti.

**I due regimi.**
- **LONG gamma (Net GEX positivo, prezzo SOPRA il Flip):** i dealer comprano quando il mercato scende e vendono quando sale → **frenano** il prezzo. Oscillazioni contenute, i grandi cluster di gamma fanno da **supporto/resistenza** e da **calamita**.
- **SHORT gamma (Net GEX negativo, prezzo SOTTO il Flip):** i dealer fanno il contrario, vendono sui ribassi e comprano sui rialzi → **amplificano**. Movimenti più ampi, volatilità più alta.

**Insight operativi.**
- **Gamma Flip = spartiacque e attrattore.** Sopra, mercato "calmo"; sotto, mercato "esplosivo". Il prezzo tende a **gravitare** verso il Flip e verso i livelli molto carichi di gamma.
- **Rotture decise (breakout).** Se il prezzo rompe un grande livello di gamma o scende sotto il Flip, l'effetto stabilizzante svanisce → accelerazione rapida e volatilità in aumento.

**Cosa guardare nel grafico.** Barre per strike (verde = gamma positivo, rosso = negativo), linea blu = spot, linea gialla tratteggiata = Gamma Flip.

**⚠️ Attenzione — specifico FTSEMIB.** Il Gamma qui è stimato via Black-Scholes dal *Settle* (Euronext non lo fornisce), col moltiplicatore MIBO €2.5/punto impostato in sidebar (non 100 come SPX). Il **livello** del Gamma Flip non dipende dal moltiplicatore (resta corretto anche se lo cambi), ma la **magnitudine** in € del Net GEX sì.
                """
            )

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

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Ogni opzione ha un *delta* (quanto guadagna/perde se il sottostante si muove di 1 punto) e una *vanna* (quanto cambia quel delta se la volatilità sale o scende). Qui li sommiamo su tutti i contratti aperti (*open interest*) per fotografare **come è posizionato il mercato**.

- **DEX (Delta) — il posizionamento direzionale.** DEX > 0 = tra i contratti aperti prevale il delta delle call → tono più **rialzista**; DEX < 0 = prevale il delta delle put → tono più **ribassista/difensivo**.
- **VEX (Vanna) — la sensibilità alla volatilità.** Come cambierebbe l'esposizione se la volatilità si muovesse. Il **Vanna Flip** è il prezzo che separa i due regimi.

**Insight operativi.**
- **La vanna è il motore dei "melt-up" a bassa volatilità.** Quando i mercati salgono lenti e la volatilità scende, la vanna tende a spingere altri acquisti di copertura. Il meccanismo si inverte quando la volatilità sale (paura).
- **Il Vanna Flip fa da spartiacque:** leggilo insieme al Gamma Flip per capire il regime.

**Cosa guardare nei grafici.** Barre per strike; linea blu = spot; linea gialla tratteggiata (VEX) = Vanna Flip.

**⚠️ Attenzione — doppiamente importante qui.**
1. Come nell'app originale, **DEX e VEX non applicano una convenzione di segno "dealer"**: sono somme dell'esposizione dell'open interest, non "cosa devono fare i dealer".
2. **Specifico FTSEMIB**: Delta e Vanna sono stimati via Black-Scholes dal *Settle* (Euronext non li fornisce), quindi sono un'ipotesi di modello sopra un'altra ipotesi di modello — trattali come indicazione di massima, non come dato di mercato osservato.
                """
            )

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

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** L'**Open Interest (OI)** è il numero di contratti *aperti* su ogni strike: è il posizionamento *accumulato* nel tempo. Il **Volume** è invece quanto si è scambiato *oggi*. Dove l'OI è enorme, i dealer hanno molta copertura da gestire proprio lì, e questo tende a influenzare il prezzo.

**Come si legge.**
- **Put Wall** — lo strike con più OI put vicino al prezzo: possibile zona di **supporto**.
- **Call Wall** — lo strike con più OI call vicino al prezzo: possibile zona di **resistenza**.
- **Grafici OI e Volumi** — call verso destra (positivo), put verso sinistra (negativo): le barre più lunghe sono i "muri".
- **Sintesi Drift** — il baricentro dei volumi di oggi (call e put) rispetto allo spot: a destra = tono rialzista, a sinistra = ribassista.

**Insight operativi.**
- **I Wall agiscono da supporto/resistenza e da calamita.** Un grande muro di OI genera copertura che tende a frenare il prezzo lì, e verso la scadenza lo attrae ("pinning").
- **Rottura decisa di un Wall.** Spesso accelera il movimento: un supporto rotto diventa spesso resistenza (e viceversa).

**⚠️ Attenzione.** Questa tab si basa **solo su OI e Volume**, dati reali forniti direttamente da Euronext (non stimati) — a differenza delle tab GEX/VEX/DEX, qui non c'è alcuna derivazione Black-Scholes di mezzo. I Wall restano comunque concentrazioni di OI, non muri garantiti.
                """
            )

        col1, col2 = st.columns(2)
        col1.metric("🛡️ Put Wall", f"{oi_metrics['put_wall_strike']:.0f}" if oi_metrics['put_wall_strike'] else "N/A", help=f"OI: {oi_metrics['put_wall_oi']:,.0f}")
        col2.metric("🛑 Call Wall", f"{oi_metrics['call_wall_strike']:.0f}" if oi_metrics['call_wall_strike'] else "N/A", help=f"OI: {oi_metrics['call_wall_oi']:,.0f}")
        st.plotly_chart(create_oi_profile_chart(oi_metrics['df_oi_profile'], spot_price, selected_expiry_label), width="stretch", key="oi_tab")
        st.divider()
        _total_call_vol = df_selected_expiry.loc[df_selected_expiry['Type'] == 'Call', 'Vol'].sum()
        _total_put_vol = df_selected_expiry.loc[df_selected_expiry['Type'] == 'Put', 'Vol'].sum()
        st.markdown("#### Volumi daily della scadenza (valori assoluti)")
        colv1, colv2, colv3 = st.columns(3)
        colv1.metric("Volume Call (daily)", f"{_total_call_vol:,.0f}")
        colv2.metric("Volume Put (daily)", f"{_total_put_vol:,.0f}")
        colv3.metric("Volume Totale (daily, Call+Put)", f"{_total_call_vol + _total_put_vol:,.0f}")
        st.caption(
            f"Volume scambiato il {analysis_date.date()} (data del file caricato), non un cumulato "
            "da inizio vita del contratto. Somma di TUTTA la catena per questa scadenza (non solo "
            "la fascia ±25% intorno allo spot mostrata nel grafico sotto)."
        )
        st.plotly_chart(create_volume_profile_chart(vol_metrics['df_vol_profile'], spot_price, selected_expiry_label), width="stretch", key="vol_tab")
        st.divider()
        st.plotly_chart(create_drift_arrow_chart(activity_metrics['drift_score'], spot_price, selected_expiry_label), width="stretch", key="drift_arrow")
        st.plotly_chart(create_activity_ratio_chart(activity_metrics['df_activity_profile'], spot_price, selected_expiry_label), width="stretch", key="drift_detail")

    # ========================= TAB STATS =========================
    with tab_stats:
        st.header(f"Modelli Statistici per {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Tre indicatori di *sentiment* e di *ampiezza attesa* del movimento.

**Come si legge.**
- **Max Pain** — lo strike che, a scadenza, farebbe scadere senza valore il maggior numero di opzioni. Un teorico "punto di gravitazione". Si basa solo su OI, dato reale Euronext.
- **P/C Ratio (OI e Volume)** — rapporto put/call. >1 = prevalenza di put (difensivo); <1 = prevalenza di call (rialzista). Anche questi da OI/Volume reali.
- **Expected Move** — quanto il mercato si aspetta che il sottostante si muova (su o giù) da qui alla scadenza: ≈68% di probabilità di chiudere dentro le due bande. Stimato dalla volatilità implicita ATM.

**Insight operativi.**
- **Max Pain come debole attrattore**, non una regola: contano di più i Wall e il Gamma Flip.
- **P/C ratio agli estremi = spunto contrarian.** Un P/C molto alto o molto basso spesso precede un'inversione.
- **Expected Move = righello per aspettative.** Uscire dalle bande con decisione segnala un movimento oltre l'atteso.

**⚠️ Attenzione.** L'Expected Move dipende dalla IV ATM, qui **stimata** via Black-Scholes dal Settle (non fornita da Euronext) — un'ipotesi in più rispetto a Max Pain/P-C Ratio, che restano invece calcolati su dati OI/Volume reali.
                """
            )

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

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** La **Volatilità Implicita (IV)** è quanto movimento il mercato si aspetta. Non indica la direzione, solo l'ampiezza attesa: IV alta = attese di grandi oscillazioni; IV bassa = attese di calma.

**Il grafico.** Asse X = giorni alla scadenza (DTE), asse Y = strike, altezza/colore = IV in %. Usa solo opzioni OTM (put sotto lo spot, call sopra).

**Insight operativi.**
- **Skew:** di solito le put OTM hanno IV più alta delle call → il mercato paga la protezione al ribasso.
- **Term structure:** scadenze brevi con IV più alta delle lunghe (*backwardation*) segnala stress; il contrario (*contango*) è la situazione normale.

**⚠️ Attenzione — specifico FTSEMIB.** A differenza di CBOE, qui la IV per **ogni** strike/scadenza è stimata invertendo Black-Scholes dal *Settle* — quindi l'intera superficie è una ricostruzione di modello, non un dato di mercato osservato punto per punto. Trattala come indicazione di massima su skew e term structure, non come quotazioni reali.
                """
            )

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

    # ========================= TAB EVENTI VOLUME =========================
    with tab_eventi:
        st.header("Eventi Volume Significativi")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**Cosa registra.** Ogni volta che premi "Registra eventi", l'app scansiona **tutte** le scadenze
del file opzioni caricato sopra (non solo quella selezionata) e salva su disco ogni riga con
Volume oltre la soglia impostata in sidebar — indipendentemente da quale tab stai guardando.

**Perché il notional in €.** Su scadenze lunghe (es. dicembre 2027) capita di vedere pochi
contratti deep-in-the-money che valgono comunque un impegno di capitale enorme: la colonna
`notional_stimato_eur` (volume × settle × moltiplicatore) lo rende confrontabile con eventi
apparentemente "più grandi" ma su strike lontani dai soldi.

**La riconciliazione.** Il bottone "Riconcilia" legge i file `YYYYMMDD.csv` che tieni nella
cartella indicata sotto (es. `dati/`) per due scopi:
1. completare l'OI di un evento che, al momento della registrazione, non lo aveva ancora
   (file caricato la sera prima che l'OI fosse disponibile);
2. confrontare l'OI del giorno dell'evento con quella del giorno precedente disponibile in
   cartella, per capire se quel volume ha davvero aperto posizione nuova.

**Come leggere lo stato di conferma:**
- **Confermato (OI in aumento)** — l'OI è cresciuta in modo coerente con il volume: posizione
  nuova aperta, il movimento si è "concluso".
- **Non confermato (OI stabile)** — tanto volume ma l'OI non si è mosso: il tuo caso
  "comunicato ma non effettivamente concluso".
- **Chiusura posizioni (OI in calo)** — il volume ha chiuso posizioni esistenti, non ne ha
  aperte di nuove.
- **in attesa** — nella cartella non c'è (ancora) un file datato prima dell'evento per fare il confronto.

**⚠️ Attenzione.** La soglia del 30% (di quanto l'OI deve muoversi rispetto al volume per
contare come "confermato") è un punto di partenza arbitrario, regolabile se lo trovi
troppo stretto o troppo largo osservando i risultati reali.

**Il flag "Significativo".** Ogni riga ha una casella modificabile: puoi deselezionarla in
qualunque momento (anche dopo settimane) per marcarla come non rilevante, senza cancellarla
dal CSV — utile per esempio quando il notional è alto ma dopo la riconciliazione capisci che
era solo un aggiustamento tecnico. Il filtro "Nascondi scadenze già scadute" toglie dalla
vista le scadenze il cui giorno è già passato rispetto a oggi (non rispetto alla data del
file caricato), così non restano in mezzo scadenze ormai concluse.
                """
            )

        st.subheader("Registra gli eventi del file caricato sopra")
        st.caption(
            f"Scansiona TUTTE le scadenze del file opzioni caricato al punto 1 (non solo quella "
            f"selezionata) per righe con Volume > {volume_threshold:.0f} contratti, e le aggiunge "
            f"al log `{VOLUME_LOG_PATH}` (se una riga esisteva già senza OI, la completa)."
        )
        if st.button("Registra eventi di questo file nel log"):
            n_new, n_oi_fixed, log_df = log_significant_volume_events(
                df_raw, analysis_date, spot_price, contract_multiplier, volume_threshold, VOLUME_LOG_PATH
            )
            msg_parts = []
            if n_new > 0:
                msg_parts.append(f"{n_new} nuovi eventi aggiunti")
            if n_oi_fixed > 0:
                msg_parts.append(f"{n_oi_fixed} righe esistenti completate con l'OI ora disponibile")
            if msg_parts:
                st.success(f"{'; '.join(msg_parts)} (totale eventi nel log: {len(log_df)}).")
            else:
                st.info("Nessun nuovo evento o completamento da fare (o già tutto presente nel log).")
            st.session_state['_last_log_df'] = log_df

        st.divider()
        st.subheader("Riconcilia con i file storici su disco")
        dati_folder = st.text_input(
            "Cartella con i file storici opzioni (nome YYYYMMDD.csv)",
            value=DATI_FOLDER_DEFAULT,
            help="Es. 'dati' se la cartella è dentro quella dell'app. L'app la legge direttamente "
                 "dal disco: non serve ricaricare i file nel browser."
        )
        if st.button("Riconcilia log (completa OI e verifica conferme)"):
            n_oi_filled, n_confirmed, log_df = reconcile_log(VOLUME_LOG_PATH, dati_folder)
            st.success(
                f"OI completati: {n_oi_filled}. Righe con nuovo stato di conferma calcolato: {n_confirmed}."
            )
            st.session_state['_last_log_df'] = log_df

        st.divider()
        st.subheader("Log eventi")

        _log_df = st.session_state.get('_last_log_df')
        if _log_df is None and os.path.exists(VOLUME_LOG_PATH):
            _log_df = pd.read_csv(VOLUME_LOG_PATH)
            for _col, _default in [('significativo', True), ('ora', ''), ('spot_preciso', np.nan)]:
                if _col not in _log_df.columns:
                    _log_df[_col] = _default
            _log_df['significativo'] = _log_df['significativo'].astype(object).where(_log_df['significativo'].notna(), True)
            _log_df['ora'] = _log_df['ora'].astype(object).fillna('')

        if _log_df is None or _log_df.empty:
            st.info("Nessun log ancora creato: premi 'Registra eventi di questo file nel log' qui sopra.")
        else:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                nascondi_scadute = st.checkbox("Nascondi scadenze già scadute", value=True)
            with col_f2:
                solo_significativi = st.checkbox("Mostra solo eventi marcati come significativi", value=False)

            _view = _log_df.copy()
            _view['significativo'] = _view['significativo'].astype(bool)
            if nascondi_scadute:
                _oggi = dt.date.today()
                _view = _view[pd.to_datetime(_view['scadenza']).dt.date >= _oggi]
            if solo_significativi:
                _view = _view[_view['significativo']]

            if _view.empty:
                st.info("Nessuna riga da mostrare con i filtri attuali.")
            else:
                _view = _view.sort_values(['data_riferimento', 'notional_stimato_eur'], ascending=[False, False]).reset_index(drop=True)
                _key_cols = ['data_riferimento', 'scadenza', 'strike', 'tipo']
                _editable_cols = ['significativo', 'ora', 'spot_preciso']
                _other_cols = [c for c in _view.columns if c not in _key_cols + _editable_cols]
                _edited = st.data_editor(
                    _view[_key_cols + _editable_cols + _other_cols],
                    column_config={
                        "significativo": st.column_config.CheckboxColumn(
                            "Significativo", help="Deseleziona per marcare la riga come non rilevante", width="small"
                        ),
                        "ora": st.column_config.TextColumn(
                            "Ora", help="Da compilare a mano solo per i movimenti da indagare (es. notional 10-20M+)",
                            width="small"
                        ),
                        "spot_preciso": st.column_config.NumberColumn(
                            "Spot preciso", help="Spot più preciso all'ora indicata, se lo hai verificato a mano",
                            format="%.2f", width="small"
                        ),
                        **{c: st.column_config.Column(disabled=True, width="small") for c in _key_cols + _other_cols}
                    },
                    hide_index=True, width="stretch", key="log_editor"
                )
                if st.button("Salva modifiche (flag, ora, spot preciso)"):
                    n_changed, updated_log = update_log_fields(
                        VOLUME_LOG_PATH, _edited[_key_cols + _editable_cols], editable_cols=_editable_cols
                    )
                    if n_changed > 0:
                        st.success(f"{n_changed} righe aggiornate nel log.")
                        st.session_state['_last_log_df'] = updated_log
                    else:
                        st.info("Nessuna modifica da salvare.")
            st.caption(
                "'Significativo', 'Ora' e 'Spot preciso' restano salvati nel CSV anche filtrando "
                "la vista: puoi modificarli in qualunque momento, anche dopo settimane. Le altre "
                "colonne sono di sola lettura."
            )

    # ========================= TAB ANDAMENTO STORICO =========================
    with tab_storico:
        st.header("Andamento Storico: Spot / Volume / Open Interest")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**Cosa mostra.** Volume e Open Interest **totali** (somma su tutte le scadenze, non
solo quella selezionata altrove nell'app), giorno per giorno, affiancati allo Spot
per verificare se i movimenti di posizionamento coincidono con movimenti di prezzo.

**Perché serve ricostruire da cartella.** I file che finiscono in `dati/` possono
arrivare in tre modi diversi: copia-incolla manuale nell'app, `ripara_file_dati.py`,
o `recupera_storico.py`. Solo il primo modo aggiorna questo storico automaticamente;
gli altri due scrivono direttamente su disco, senza passare dall'app. Il bottone
qui sotto legge **tutti** i file `dati/YYYYMMDD.csv` presenti, indipendentemente da
come sono arrivati lì, e ricostruisce lo storico da zero — così non ne manca nessuno.

**Tre pannelli, tre scale.** OI e Volume vengono mostrati separati perché l'OI è di
ordini di grandezza più alto: sullo stesso asse il Volume sparirebbe schiacciato.
                """
            )

        col_rb1, col_rb2 = st.columns(2)
        with col_rb1:
            cartella_dati_storico = st.text_input(
                "Cartella file dati (YYYYMMDD.csv)", value=DATI_FOLDER_DEFAULT, key="cartella_storico_totali"
            )
        with col_rb2:
            percorso_prezzi_storico = st.text_input(
                "Percorso storico prezzi (per lo spot)",
                value=st.session_state.get('percorso_prezzi_default', "INDEX_FTSEMIB_1D.csv"),
                key="percorso_prezzi_storico"
            )

        if st.button("🔄 Ricostruisci storico da cartella dati/"):
            n_giorni, storico_totali = ricostruisci_storico_totali(
                cartella_dati_storico, TOTALI_LOG_PATH, percorso_prezzi=percorso_prezzi_storico
            )
            if n_giorni > 0:
                st.success(f"Ricostruito: {n_giorni} giorni trovati e processati.")
            else:
                st.warning(f"Nessun file YYYYMMDD.csv trovato in `{cartella_dati_storico}`.")
            st.session_state['_storico_totali_df'] = storico_totali

        st.divider()

        _storico_totali = st.session_state.get('_storico_totali_df')
        if _storico_totali is None and os.path.exists(TOTALI_LOG_PATH):
            _storico_totali = pd.read_csv(TOTALI_LOG_PATH)

        if _storico_totali is None or _storico_totali.empty:
            st.info("Nessuno storico ancora disponibile: premi 'Ricostruisci storico da cartella dati/' qui sopra, "
                     "oppure carica almeno un file opzioni al punto 1 sopra la sidebar.")
        else:
            if len(_storico_totali) >= 2:
                _fig = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                    row_heights=[0.34, 0.33, 0.33],
                    subplot_titles=("Spot FTSEMIB", "Open Interest totale", "Volume totale")
                )
                _fig.add_trace(go.Scatter(x=_storico_totali['data'], y=_storico_totali['spot'],
                                           mode='lines+markers', name='Spot', line=dict(color='#60a5fa')), row=1, col=1)
                _fig.add_trace(go.Scatter(x=_storico_totali['data'], y=_storico_totali['oi_totale'],
                                           mode='lines+markers', name='OI totale', line=dict(color='#34d399')), row=2, col=1)
                _fig.add_trace(go.Scatter(x=_storico_totali['data'], y=_storico_totali['volume_totale'],
                                           mode='lines+markers', name='Volume totale', line=dict(color='#f97316')), row=3, col=1)
                _fig.update_layout(height=650, template='plotly_dark', margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
                st.plotly_chart(_fig, width="stretch", key="storico_totali_chart")
                st.caption(
                    "Tre pannelli allineati sulla stessa data, ciascuno con la propria scala. Confronta se un "
                    "salto di OI o Volume coincide con un movimento marcato dello spot in alto."
                )
            else:
                st.info("Serve almeno un secondo giorno per mostrare il grafico.")
            st.dataframe(_storico_totali.sort_values('data', ascending=False), width="stretch", hide_index=True)



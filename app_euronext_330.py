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
#
# Ultima modifica: 2026-09-20 - v3.3
# - Tab Cicli: le etichette sui pivot mostrano ora anche le barre trascorse
#   dal precedente pivot DELLO STESSO TIPO (diretto con diretto, inverso con
#   inverso), in cima all'etichetta, sopra data e valore - utile per
#   confrontare a colpo d'occhio la durata reale di un ciclo con il nominale
#   T+2 (32 barre)/T+3 (64 barre) del metodo di Elico.
# - Nuovo expander "➕ Aggiungi uno start di ciclo a mano": per marcare un
#   punto di partenza alternativo (es. testare sia il 9 che il 15 settembre
#   come possibile inizio di un nuovo T+2 diretto), salvato su file
#   persistente e disegnato con una stella dorata distinta dai pivot
#   automatici. Tabella eliminabile riga per riga (num_rows="dynamic").
#
# Ultima modifica: 2026-09-20 - v3.2
# - Tab Cicli: aggiunte etichette data/valore direttamente sui pivot rilevati
#   (non solo hover), con interruttore per disattivarle se il grafico diventa
#   affollato su "Tutto" lo storico. Primo passo verso un confronto più
#   leggibile con la nomenclatura T+2 (mensile, 32 barre)/T+3 (trimestrale
#   grosso modo, 64 barre) usata nel metodo ciclico di Elico - rilevamento
#   automatico "a grana grossa" e mappatura manuale di T/T-1 restano da fare.
# - Applicata preventivamente anche qui la correzione hovermode='closest'
#   (stessa causa già risolta nel tab Treno: marker sparsi + candele dense
#   con 'x unified' possono far "saltare" l'hover su alcune barre).
#
# Ultima modifica: 2026-09-17 - v3.1.1
# - Corretto il salto di 1-2 barre nell'hover del grafico Treno, segnalato con
#   settlement o pornociclo attivi: hovermode='x unified' con trace sparse
#   (settlement, pivot pornociclo) mescolate a una densa (una candela a
#   settimana) puo' "catturare" l'hover sul punto sparso piu' vicino invece
#   che sulla candela sotto il cursore. Cambiato a 'closest', solo per questo
#   grafico. Uniformato anche il dtype delle date dei pivot pornociclo
#   (Timestamp invece di date "nudi") e il rombo di conferma ora usa
#   l'High/Low reale della barra di conferma, non piu' il valore del pivot
#   originale.
#
# Ultima modifica: 2026-09-17 - v3.1
# - Aggiunto il rilevatore oggettivo del "Metodo Treno" (pornociclo/69) nel tab
#   Treno, timeframe Weekly: identifica automaticamente i pivot A/B/C
#   masculo/fimmina (nuovo modulo pornociclo_lab.py), con tabella persistente
#   correggibile a mano per i rari casi ambigui, e overlay sul grafico
#   esistente (marker pieno = confermato, cerchio vuoto = candidato ancora
#   aperto, rombo giallo = barra di conferma). Validato contro un grafico
#   reale annotato a mano: entrambi i punti verificabili (27/03 e 10/07/2026,
#   incluse le date di conferma) combaciano esattamente. La regola
#   dell'eccezione delle 4 barre esiste nel modulo ma resta disattivata
#   (usa_eccezione=False di default): una prima verifica ha mostrato che la
#   lettura del trigger sballa una conferma già validata - da ricalibrare
#   quando si presenterà un altro caso reale da confrontare.
#
# Ultima modifica: 2026-09-16 - v3.0
# Versione "punto di fork": da qui AnalisiOpzioniFTSEMIB prosegue con piccoli
# miglioramenti mirati alle opzioni, mentre AnalisiFTSEMIB (nuovo repository,
# stessa cronologia fino a qui) diventa il ramo di sviluppo più sofisticato
# (altre analisi oltre le opzioni, es. OI future).
#
# Riepilogo cumulativo dei cambiamenti dalla v2.9x:
# - Sidebar riorganizzata e più stretta: solo Spot sempre visibile, il resto
#   (Risk-free/Dividend yield/Moltiplicatore/Soglia volume) in un expander
#   "Parametri (Vol., Risk Free...)" con etichette di rilevanza (🔴🟡🟢) e
#   nota su quando ha senso rivederli.
# - Aggiunta sezione "🔗 Link utili" (Euronext opzioni/future) e tre bottoni
#   "Vai a" (Help/Glossario, Istruzioni di scarico, Teoria) che saltano
#   davvero al contenuto — sfruttando key/on_change su st.tabs (rilasciato da
#   Streamlit a marzo 2026) per il salto al tab Teoria, e un flag "usa e
#   getta" in session_state per aprire gli expander Glossario/Istruzioni
#   (necessario perché quegli expander sono definiti PRIMA del bottone nel
#   codice: mutare session_state di un widget già istanziato nello stesso
#   giro fallisce, il flag letto al momento della creazione invece no).
# - Verificato con un giro di test funzionali headless (streamlit.testing.v1.
#   AppTest): tutti i 15 tab, sia con Spot impostato sia senza, più i tre
#   bottoni "Vai a" - nessuna eccezione.
#
# Ultima modifica: 2026-09-16 - v2.99.2
# - Rinominato l'expander "Altri parametri" -> "Parametri (Vol., Risk Free...)"
#   per anticiparne il contenuto anche da chiuso.
# - Nota "Link utili" in sidebar trasformata in elenco puntato (Help/Glossario,
#   Istruzioni di scarico, Teoria). Nessun vero link cliccabile verso il tab
#   Teoria: st.tabs non supporta un'ancora stabile per aprire un tab specifico
#   da un altro punto della pagina, resta quindi testo informativo.
#
# Ultima modifica: 2026-09-16 - v2.99.1
# - Aggiornato il default di Risk-free al nuovo tasso BCE sui depositi (2,25% ->
#   2,50%), dopo il rialzo di 0,25 punti deciso il 10/9/2026, in vigore dal
#   16/9/2026 - esempio pratico del perché in sidebar è segnalato come "🟡
#   aggiornamento periodico, non giornaliero, segue le decisioni BCE".
#
# Ultima modifica: 2026-09-15 - v2.99
# - Nell'expander "Altri parametri": riordinati per rilevanza ed etichettati con
#   un colore/nota su quanto spesso ha senso rivederli - 🔴 Soglia volume (il
#   più rilevante, in cima), 🟡 Risk-free/Dividend yield (periodico, non
#   giornaliero: risk-free segue le decisioni BCE, dividend yield si muove
#   lentamente nell'anno), 🟢 Moltiplicatore contratto (invariato da anni).
#
# Ultima modifica: 2026-09-15 - v2.98
# - Sidebar riorganizzata: solo lo Spot (l'unico valore che cambia ogni giorno)
#   resta sempre visibile; Risk-free/Dividend yield/Moltiplicatore/Soglia volume
#   spostati in un expander compatto "Altri parametri" (due colonne per i primi
#   due). Larghezza di base della sidebar ridotta via CSS (resta ridimensionabile
#   a mano trascinando il bordo).
# - Aggiunta sezione "🔗 Link utili" in sidebar: collegamenti diretti alle pagine
#   Euronext (opzioni MIBO, future FIB) e rimando al Glossario/Help in cima alla
#   pagina principale.
#
# Ultima modifica: 2026-09-15 - v2.97
# - Corretta la scadenza di novembre mancante nello scarico live (SCADENZE_NOTE
#   statica -> fetch_scadenze_disponibili(), letta dinamicamente da Euronext).
# - Il corpo principale (tab) ora si apre col solo df_raw, non serve più anche
#   lo spot: aggiunto il tab "Dati" (sempre disponibile) e differenziato il
#   messaggio nei tab che richiedono Black-Scholes (spot mancante vs OI
#   mancante), riusando il meccanismo _oi_disponibile già esistente.
# - Numero di versione ora incorporato direttamente qui (APP_VERSION sotto),
#   non solo in VERSION.txt esterno: così viaggia sempre insieme al codice,
#   anche se VERSION.txt venisse dimenticato copiando solo questo file tra
#   cartelle o macchine (stessa idea già applicata a gestore_git.py). Da
#   aggiornare ad ogni release, insieme a questo changelog.
# -----------------------------------------------------------------------------

APP_VERSION = "3.3"

import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from euronext_module import (
    parse_euronext_text, enrich_with_greeks, log_significant_volume_events,
    reconcile_log, update_log_fields, log_totali_giornalieri, ricostruisci_storico_totali,
    aggiungi_nota_diario, elimina_nota_diario, modifica_nota_diario, _bs_price,
    estimate_iv_multi_day_batch, ricostruisci_storico_stats, aggiorna_riga_oggi_stats,
    third_friday, rileva_pivot_alternati, classifica_durata_cicli, aggrega_barre_n,
    scrivi_file_dati
)
from euronext_live_module import (
    crea_sessione, fetch_live_html_batched, parse_live_html, fetch_scadenze_disponibili
)
from pornociclo_lab import (
    resample_weekly as pc_resample_weekly, rileva_pivot_pornociclo, genera_etichette
)
from documentazione_module import (
    impacchetta_html, elenca_markdown, elenca_pdf, elenca_html_pronti, elenca_html_sorgenti
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
    /* v2.98: colonna sinistra più stretta di base (default Streamlit ~21rem) -
       pochi parametri, non serve tutto quello spazio; resta comunque
       ridimensionabile a mano trascinando il bordo. */
    section[data-testid="stSidebar"] {
        width: 260px !important;
    }
</style>
""", unsafe_allow_html=True)

def _leggi_versione():
    try:
        with open("VERSION.txt") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

_app_version = APP_VERSION or _leggi_versione()
_titolo = "📊 FTSEMIB Options Analyzer (Euronext)"
if _app_version:
    _titolo += f"  `v{_app_version}`"
st.title(_titolo)
st.caption(
    "⚠️ **Solo a scopo informativo/educativo — NON è consulenza finanziaria.** "
    "Delta, Gamma, IV e Vanna non sono forniti da Euronext: sono stimati qui invertendo "
    "Black-Scholes dal prezzo *Settle* di ciascuna opzione — sono ipotesi di modello sopra "
    "un modello, non dati di mercato osservati. Il *Settle* Euronext può occasionalmente "
    "essere anomalo su strike poco liquidi: le righe che violano i limiti no-arbitraggio "
    "vengono scartate automaticamente e segnalate."
)

with st.expander("📖 Glossario dei termini (parti da qui se sei alle prime armi)",
                  expanded=st.session_state.pop("_apri_glossario", False)):
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

with st.expander("🖥️ Scaricare dati da terminale (opzioni e future, anche storico)",
                  expanded=st.session_state.pop("_apri_istruzioni_scarico", False)):
    st.markdown(
        """
Questa pagina scarica un giorno alla volta (quello scelto qui sopra). Per scaricare
**più giorni insieme** (es. ricostruire uno storico), o l'Open Interest del
**future FIB** (non le opzioni), si usano due script a parte da terminale — vanno
lanciati dalla stessa cartella di questa app (importano direttamente
`euronext_live_module.py`/`euronext_module.py`).

**Opzioni — backfill storico (`scarica_backfill_opzioni.py`)**

Scrive un file `dati/YYYYMMDD.csv` per ciascun giorno, nello stesso formato che
questa pagina legge già con "Scegli dalla cartella dati/" qui sopra.

```
python3 scarica_backfill_opzioni.py --data 2026-09-14                        # un solo giorno
python3 scarica_backfill_opzioni.py --da 2026-06-19 --a 2026-09-14           # intervallo (backfill)
python3 scarica_backfill_opzioni.py --da 2026-06-19 --a 2026-09-14 --forza   # riscrive anche i giorni già presenti
python3 scarica_backfill_opzioni.py --da 2026-06-19 --a 2026-09-14 --pausa 30   # più prudente verso il server
```

Salta automaticamente sabato/domenica; un giorno che dà errore (es. festivo di
borsa) non blocca gli altri - viene segnalato e si passa al successivo.

**Future FIB — Open Interest (`scarica_futures_euronext.py`)**

A differenza delle opzioni (un file per giorno, tante scadenze/strike), qui c'è
una sola riga per scadenza al giorno: tutto finisce in un unico storico CSV
(`dati_locali/storico_oi_future.csv`) — pensato soprattutto per non perdere l'OI
di una scadenza quando esce dalla pagina live di Euronext dopo il settlement
(tipico durante le settimane della "strega").

```
python3 scarica_futures_euronext.py                                          # solo oggi
python3 scarica_futures_euronext.py --data 2026-06-19                        # un giorno storico
python3 scarica_futures_euronext.py --da 2026-06-19 --a 2026-09-14 --pausa 30    # intervallo
```

⚠️ Entrambi gli script vanno lanciati da terminale (non da questa pagina): sono
pensati per scarichi lunghi/batch, con pause configurabili per non sovraccaricare
il server Euronext.
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

_sorgente_file = st.radio(
    "Sorgente del file",
    ["Carica dal dispositivo", "Scegli dalla cartella dati/ (sul server)", "Scarica da Euronext (una data)"],
    horizontal=True,
    help="Se accedi da un altro dispositivo in rete (es. un tablet), 'Carica dal dispositivo' "
         "cerca il file nello storage di QUEL dispositivo, non su questo computer. Se il file "
         "è già salvato nella cartella dati/ di questo computer, usa la seconda opzione. La terza "
         "opzione scarica un giorno direttamente da Euronext e lo salva in dati/ — equivalente a "
         "lanciare rigenera_file_dati.py da terminale, ma dalla UI."
)

df_raw, analysis_date = None, None
TOTALI_LOG_PATH = "dati_locali/storico_totali.csv"

if _sorgente_file == "Carica dal dispositivo":
    uploaded_file = st.file_uploader("File CSV opzioni", type=["csv", "txt"], key="options_csv")
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
elif _sorgente_file == "Scegli dalla cartella dati/ (sul server)":
    _cartella_dati_step1 = st.text_input(
        "Cartella file dati (sul server)", value="dati", key="cartella_dati_step1"
    )
    if os.path.isdir(_cartella_dati_step1):
        _file_disponibili = sorted(
            [f for f in os.listdir(_cartella_dati_step1) if f.lower().endswith(('.csv', '.txt'))],
            reverse=True
        )
        if _file_disponibili:
            _file_scelto = st.selectbox("File disponibili (più recente in cima)", _file_disponibili)
            try:
                with open(os.path.join(_cartella_dati_step1, _file_scelto), encoding="utf-8-sig") as f:
                    text = f.read()
                df_raw, analysis_date = parse_euronext_text(text)
                n_expiries = df_raw['Expiration Date'].nunique()
                st.success(f"Letto: {len(df_raw)} righe, {n_expiries} scadenze, data di riferimento {analysis_date.date()}.")
            except Exception as e:
                st.error(f"Errore nel parsing del file: {e}")
        else:
            st.warning(f"Nessun file .csv/.txt trovato in `{_cartella_dati_step1}`.")
    else:
        st.warning(f"Cartella non trovata: `{_cartella_dati_step1}` (percorso relativo alla cartella da cui hai lanciato l'app sul server).")
else:  # "Scarica da Euronext (una data)"
    st.caption(
        "Equivalente a `python3 rigenera_file_dati.py --data ... --file dati/YYYYMMDD.csv`, "
        "ma dalla UI. Interroga direttamente l'endpoint Euronext (stesso usato dal monitoraggio "
        "live) e salva il risultato in dati/, nel formato che l'app legge normalmente. Nota: "
        "l'Open Interest ufficiale del giorno è disponibile di solito solo il giorno successivo — "
        "se scarichi il giorno stesso, l'OI potrebbe risultare parziale."
    )
    _col_data, _col_cartella = st.columns([1, 1])
    with _col_data:
        _data_scarico = st.date_input(
            "Data da scaricare", value=dt.date.today() - dt.timedelta(days=1), key="data_scarico_euronext"
        )
    with _col_cartella:
        _cartella_dati_scarico = st.text_input(
            "Cartella di destinazione", value="dati", key="cartella_dati_scarico"
        )

    if st.button("📥 Scarica da Euronext e salva in dati/"):
        _nome_file_scarico = _data_scarico.strftime("%Y%m%d") + ".csv"
        _percorso_scarico = os.path.join(_cartella_dati_scarico, _nome_file_scarico)
        try:
            with st.spinner(f"Scaricando da Euronext per il {_data_scarico}..."):
                _session = crea_sessione()
                _scadenze_da_scaricare = fetch_scadenze_disponibili(_session)
                _html_parts = fetch_live_html_batched(
                    _session, expiries=_scadenze_da_scaricare, trade_date=_data_scarico.strftime("%m-%d-%Y"),
                    batch_size=5, verbose=False
                )
                _df_scarico = pd.concat([parse_live_html(h) for h in _html_parts], ignore_index=True)
                os.makedirs(_cartella_dati_scarico, exist_ok=True)
                scrivi_file_dati(_df_scarico, _percorso_scarico, _data_scarico)
            _n_con_oi = _df_scarico['OI'].notna().sum()
            st.success(
                f"File salvato: `{_percorso_scarico}` — {len(_df_scarico)} righe lette, "
                f"{_n_con_oi} con Open Interest presente."
            )
            # Un solo click: i dati appena scaricati vengono usati direttamente per
            # l'analisi, senza dover rileggere il file da disco con un secondo passaggio
            # (che richiederebbe un secondo click e generava confusione: lo spot/il menu
            # sembravano non aggiornarsi finche' quel secondo bottone non veniva premuto).
            df_raw = _df_scarico.copy()
            analysis_date = pd.Timestamp(_data_scarico)
            st.session_state['_ultimo_file_scaricato'] = _percorso_scarico
            st.session_state['_ultimo_df_scaricato'] = df_raw
            st.session_state['_ultima_analysis_date_scaricato'] = analysis_date
        except Exception as e:
            st.error(f"Errore nel download da Euronext: {e}")
    elif st.session_state.get('_ultimo_df_scaricato') is not None:
        # Riusa l'ultimo download di questa sessione anche nei rerun successivi
        # (es. quando cambi un parametro in sidebar), senza doverlo riscaricare.
        df_raw = st.session_state['_ultimo_df_scaricato']
        analysis_date = st.session_state['_ultima_analysis_date_scaricato']
        st.caption(
            f"Ultimo file scaricato in questa sessione: "
            f"`{st.session_state.get('_ultimo_file_scaricato', '?')}` "
            f"(data di riferimento {analysis_date.date()})."
        )

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
    st.header("⚙️ Parametri")
    # Se lo storico prezzi ha trovato una corrispondenza, la propone come default;
    # altrimenti resta libero (nessun valore precompilato "fisso" da dimenticare di cambiare).
    # NOTA (corretto 18/08/2026): Streamlit cancella automaticamente da session_state la
    # entry di un widget quando quel widget non viene ricreato in un rerun (es. cambiando
    # data, la key "spot_2026-08-05" sparisce per un giro se selezioni un'altra data).
    # Il vecchio controllo "gia' applicato" restava vero anche dopo questa cancellazione
    # silenziosa, quindi saltava la reinizializzazione e il widget ripartiva da 0 (niente
    # spot, niente menu) ogni volta che si riselezionava una data gia' vista in precedenza.
    # Ora il controllo e' "la chiave del widget e' assente" (vero sia al primo utilizzo sia
    # dopo che Streamlit l'ha cancellata), che copre correttamente entrambi i casi. Prezzo
    # da pagare: un'eventuale correzione manuale dello spot non sopravvive se cambi data e
    # poi ritorni su quella corretta a mano (viene ricalcolato da capo) - inevitabile dato
    # il comportamento di Streamlit, ma comunque meglio di ritrovarsi spot a 0 e menu assente.
    _spot_key = f"spot_{analysis_date.date() if analysis_date is not None else 'none'}"
    if suggested_spot is not None and _spot_key not in st.session_state:
        st.session_state[_spot_key] = suggested_spot
    spot_price = st.number_input(
        "Spot FTSEMIB del giorno",
        min_value=0.0, step=1.0, format="%.2f", key=_spot_key,
        help="Precompilato automaticamente se carichi lo storico prezzi (punto 2 sopra), in "
             "qualunque ordine carichi i due file; altrimenti va inserito a mano."
    )

    # v2.98: parametri secondari (cambiano raramente rispetto allo spot) raccolti
    # in un expander compatto, per non occupare spazio verticale ogni giorno.
    with st.expander("Parametri (Vol., Risk Free...)", expanded=False):
        st.caption("🔴 Il più rilevante da tenere d'occhio, sotto:")
        volume_threshold = st.number_input(
            "Soglia volume significativo (contratti)",
            min_value=1, value=100, step=10,
            help="Sopra questa soglia (per singolo strike/scadenza) l'evento viene proposto per il log. "
                 "Il notional stimato in € nel log aiuta a giudicare la rilevanza reale anche per strike "
                 "deep ITM lontani dallo spot, dove pochi contratti pesano molto di più."
        )

        st.divider()
        st.caption(
            "🟡 Aggiornamento periodico, non giornaliero: Risk-free segue le decisioni BCE (cambia "
            "solo quando la BCE muove i tassi); Dividend yield si muove lentamente nel corso dell'anno "
            "(ha senso ricontrollarlo ogni tanto, es. trimestralmente)."
        )
        col_r, col_d = st.columns(2)
        with col_r:
            risk_free_rate = st.number_input(
                "Risk-free (%)", min_value=-5.0, max_value=25.0, value=2.50, step=0.05, format="%.2f",
                help="Default: tasso BCE sui depositi in vigore dal 16/9/2026 (rialzo di 0,25 punti deciso il 10/9/2026)."
            ) / 100.0
        with col_d:
            dividend_yield = st.number_input(
                "Dividend yield (%)", min_value=0.0, max_value=25.0, value=4.20, step=0.10, format="%.2f",
                help="Default: stima dividend yield FTSEMIB 2026 (~4.2%, contro l'1.3% USA dell'app CBOE)."
            ) / 100.0

        st.divider()
        st.caption("🟢 Cambia raramente (MIBO: €2,5/punto, invariato da anni):")
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

    st.divider()
    st.markdown("**🔗 Link utili**")
    st.markdown("[📊 Euronext — Opzioni MIBO](https://live.euronext.com/en/product/index-options/MIB-DMIL/settlement-prices)")
    st.markdown("[📈 Euronext — Future FIB](https://live.euronext.com/en/product/index-futures/FIB-DMIL/settlement-prices)")
    st.caption("**Vai a (in cima o in fondo alla pagina principale):**")
    if st.button("📖 Help/Glossario", key="btn_vai_glossario", width="stretch"):
        st.session_state["_apri_glossario"] = True
        st.rerun()
    if st.button("📥 Istruzioni di scarico", key="btn_vai_istruzioni", width="stretch"):
        st.session_state["_apri_istruzioni_scarico"] = True
        st.rerun()
    if st.button("📚 Teoria", key="btn_vai_teoria", width="stretch"):
        st.session_state["tab_principale"] = "📚 Teoria"
        st.rerun()

VOLUME_LOG_PATH = "dati_locali/eventi_volume.csv"
DATI_FOLDER_DEFAULT = "dati"
TOTALI_LOG_PATH = "dati_locali/storico_totali.csv"
STATS_LOG_PATH = "dati_locali/storico_stats.csv"
TRENO_UFFICIALE_PATH = "dati_locali/treno_settlement_ufficiale.csv"
PORNOCICLO_CORREZIONI_PATH = "dati_locali/pornociclo_correzioni.csv"
DOC_MD_FOLDER = "documentazione/md"
DOC_HTML_SRC_FOLDER = "documentazione/html_sorgente"
DOC_HTML_READY_FOLDER = "documentazione/html_pronto"
DOC_PDF_FOLDER = "static/pdf"
CICLI_CONVALIDA_PATH = "dati_locali/cicli_convalida.csv"
CICLI_MANUALI_PATH = "dati_locali/cicli_manuali.csv"

if df_raw is not None and spot_price > 0:
    log_totali_giornalieri(df_raw, analysis_date, TOTALI_LOG_PATH, spot=spot_price)

# -----------------------------------------------------------------------------
# CORPO PRINCIPALE
# -----------------------------------------------------------------------------
if df_raw is not None:

    unique_expirations = sorted(df_raw['Expiration Date'].dropna().unique())
    _WEEKDAYS_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    _WEEKDAYS_IT = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']

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

    _spot_disponibile = spot_price > 0
    if _spot_disponibile:
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
    else:
        # Niente spot: niente Black-Scholes possibile (servirebbe dividere per uno spot
        # inesistente). Si resta sui dati grezzi - la tabella e i tab che non dipendono
        # dallo spot restano comunque disponibili (vedi tab Dati e messaggi sotto).
        st.warning(
            "💤 Nessuno Spot FTSEMIB impostato in sidebar: le analisi che derivano Greche/GEX/VEX/DEX/"
            "Max Pain/Vol Surface da Black-Scholes non possono essere calcolate (richiedono lo spot). "
            "Puoi comunque consultare la tabella dati grezzi (tab '🗂️ Dati'), Eventi Volume, Andamento "
            "Storico, Note, Treno, Cicli e Teoria."
        )
        df_selected_expiry = df_selected_raw.copy()
        n_discarded = 0
        df_selected_expiry_oi = df_selected_raw.iloc[0:0].copy()  # vuoto ma con le stesse colonne

    # v1.2.0: niente più st.stop() qui. L'assenza di OI (tipico intraday, prima del
    # calcolo di fine giornata) non deve bloccare TUTTA l'app: i tab che non dipendono
    # dall'OI (Eventi Volume, Andamento Storico, Note, Vol Surface, Ripartizione OI)
    # restano utilizzabili. Solo i tab che richiedono davvero l'OI mostrano un avviso
    # locale, invece del vecchio blocco totale.
    # Se manca anche/solo lo spot, si riusa lo stesso meccanismo (vedi _messaggio_dati_insufficienti
    # sotto): i tab non devono sapere QUALE dei due manca, solo che l'analisi non e' calcolabile.
    _oi_disponibile = _spot_disponibile and not df_selected_expiry_oi.empty
    if _spot_disponibile and not _oi_disponibile:
        st.warning(
            "⏳ Nessun Open Interest per questa scadenza (probabile intraday, prima del calcolo di "
            "fine giornata). Le tab basate su OI (Summary, Gamma/GEX, Vanna & Delta, Support/Res, "
            "Stats) mostreranno un avviso al loro interno. Eventi Volume, Andamento Storico, Note, "
            "Vol Surface e Ripartizione OI restano comunque disponibili."
        )

    def _messaggio_dati_insufficienti():
        """Messaggio mostrato al posto delle metriche quando _oi_disponibile e' False -
        distingue la causa (spot mancante vs OI mancante) senza che ogni tab debba saperlo."""
        if not _spot_disponibile:
            return ("💤 Serve lo Spot FTSEMIB (imposta lo nella sidebar) per calcolare questa analisi: "
                    "richiede Greche/GEX stimate via Black-Scholes, che a loro volta richiedono lo spot.")
        return ("⏳ Open Interest non ancora disponibile per questa scadenza (probabile intraday): questa "
                "sezione richiede l'OI per calcolare le metriche. Riprova più tardi o scegli una scadenza "
                "con OI disponibile.")

    if _oi_disponibile:
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

    tab_dati, tab_summary, tab_gex, tab_vex_dex, tab_oi_vol, tab_stats, tab_vol_surf, tab_eventi, tab_storico, tab_note, tab_decay, tab_ripart, tab_treno, tab_cicli, tab_teoria = st.tabs([
        '🗂️ Dati', '📋 Summary', '📊 Gamma (GEX)', '🧩 Vanna & Delta (VEX/DEX)',
        '🎯 Support/Res (OI & Vol)', '📉 Stats', '📈 Vol Surface', '📋 Eventi Volume',
        '📈 Andamento Storico', '📝 Note', '⏳ Decadimento', '⚖️ Ripartizione OI', '🚂 Treno',
        '🌀 Cicli', '📚 Teoria'
    ], key="tab_principale", on_change="rerun")

    # ========================= TAB SUMMARY =========================
    with tab_dati:
        st.header(f"Dati grezzi opzioni per {selected_expiry_label}")
        st.caption(
            "Sempre disponibile, indipendentemente da Spot e Open Interest: utile per controllare "
            "cosa è stato effettivamente caricato prima ancora di impostare lo spot, o quando "
            "un'analisi non è calcolabile (vedi eventuali avvisi sopra)."
        )
        _colonne_disponibili = [c for c in
                                 ['Strike', 'Type', 'Settle', 'Vol', 'OI', 'Delta', 'Gamma', 'IV', 'Moneyness']
                                 if c in df_selected_expiry.columns]
        _tabella_grezza = df_selected_expiry[_colonne_disponibili].copy().sort_values('Strike').reset_index(drop=True)
        _formati = {'Settle': '{:.2f}', 'Delta': '{:.3f}', 'Gamma': '{:.5f}', 'IV': '{:.2%}', 'Moneyness': '{:.3f}'}
        _formati_applicabili = {k: v for k, v in _formati.items() if k in _tabella_grezza.columns}
        st.dataframe(_tabella_grezza.style.format(_formati_applicabili), width="stretch", hide_index=True)
        if not _spot_disponibile:
            st.caption("Colonne Delta/Gamma/IV/Moneyness non mostrate: richiedono lo Spot per essere calcolate.")

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

        if not _oi_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
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

            st.divider()
            with st.expander("📄 Dati opzione in forma tabellare (questa scadenza)", expanded=False):
                _colonne_tabella = ['Strike', 'Type', 'Settle', 'Vol', 'OI', 'Delta', 'Gamma', 'IV', 'Moneyness']
                _tabella_dati = df_selected_expiry[_colonne_tabella].copy().sort_values('Strike').reset_index(drop=True)
                _tabella_dati.columns = ['Strike', 'Tipo', 'Settle', 'Volume', 'OI', 'Delta', 'Gamma', 'IV', 'Moneyness']
                st.dataframe(
                    _tabella_dati.style.format({
                        'Settle': '{:.2f}', 'Delta': '{:.3f}', 'Gamma': '{:.5f}',
                        'IV': '{:.2%}', 'Moneyness': '{:.3f}'
                    }),
                    width="stretch", hide_index=True
                )
                st.caption(
                    "Tutti gli strike di questa scadenza (anche con OI/Volume a zero). Delta/Gamma/IV sono "
                    "stime via Black-Scholes, non dati di mercato osservati."
                )

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
        if not _oi_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
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

        if not _oi_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
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

        if not _oi_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
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
        if not _oi_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
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

        st.divider()
        st.subheader("📈 Storico Stats (Max Pain / P-C Ratio / Expected Move)")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**Cosa mostra.** Come sono cambiati nel tempo, giorno per giorno, **per questa
scadenza specifica**: lo strike di Max Pain (vs lo spot), il P/C Ratio (OI e
Volume), e le bande di Expected Move (vs lo spot).

**Come si popola.** A differenza di "Andamento Storico" (che aggiorna Volume/OI
totali automaticamente a ogni caricamento), qui serve premere un bottone perché il
calcolo è più pesante (richiede ri-derivare la IV di ogni strike per ogni giorno
storico). Una volta calcolato, un giorno passato **non viene ricalcolato** alle
successive pressioni: i dati settled non cambiano più, quindi si risparmia lavoro.

**I due bottoni.**
- **Aggiorna (solo giorni mancanti)** — uso quotidiano: aggiunge solo i giorni di
  `dati/` non ancora presenti nello storico, e aggiorna la riga di oggi con i
  valori che vedi qui sopra (quindi con risk-free/dividend **di oggi**, quelli
  realmente in vigore ora).
- **Ricalcola tutto da zero** — usalo solo se sospetti un problema (es. hai
  cambiato molto risk-free/dividend/moltiplicatore e vuoi rifare tutto lo storico
  con i valori attuali): butta via e ricalcola ogni giorno per questa scadenza.

**⚠️ Approssimazione.** I giorni recuperati da `dati/` (diversi da oggi) vengono
ricalcolati con il risk-free e il dividend yield **attuali** (quelli in sidebar
ora), non quelli realmente in vigore quel giorno passato — non li conosciamo a
posteriori. Se invece premi "Aggiorna" ogni giorno mentre usi l'app, la riga di
**oggi** viene sempre salvata con i valori realmente in vigore quel giorno, quindi
con l'uso quotidiano lo storico che si costruisce diventa via via più realistico,
e questa approssimazione riguarda solo i giorni recuperati in blocco a posteriori.
                """
            )

        col_stats_btn1, col_stats_btn2 = st.columns(2)
        with col_stats_btn1:
            if st.button("🔄 Aggiorna storico Stats (solo giorni mancanti)", key="aggiorna_stats_incrementale"):
                _n_aggiunti, _ = ricostruisci_storico_stats(
                    STATS_LOG_PATH, DATI_FOLDER_DEFAULT, TOTALI_LOG_PATH, selected_expiry_date,
                    risk_free_rate, dividend_yield, contract_multiplier,
                    index_prices_path=percorso_prezzi, force_full=False
                )
                _msg = f"Aggiunti {_n_aggiunti} giorni storici mancanti."
                if _oi_disponibile:
                    aggiorna_riga_oggi_stats(
                        STATS_LOG_PATH, selected_expiry_date, analysis_date, spot_price,
                        max_pain_strike, pc_ratios, expected_move,
                        int(df_selected_expiry_oi['DTE_Days'].iloc[0]), risk_free_rate, dividend_yield,
                        call_volume_tot=df_selected_expiry_oi.loc[df_selected_expiry_oi['Type'] == 'Call', 'Vol'].sum(),
                        put_volume_tot=df_selected_expiry_oi.loc[df_selected_expiry_oi['Type'] == 'Put', 'Vol'].sum()
                    )
                    _msg += " Riga di oggi aggiornata."
                else:
                    _msg += " Riga di oggi NON aggiornata (OI non disponibile oggi)."
                st.success(_msg)
        with col_stats_btn2:
            if st.button("♻️ Ricalcola tutto da zero (questa scadenza)", key="ricalcola_stats_full"):
                _n_aggiunti, _ = ricostruisci_storico_stats(
                    STATS_LOG_PATH, DATI_FOLDER_DEFAULT, TOTALI_LOG_PATH, selected_expiry_date,
                    risk_free_rate, dividend_yield, contract_multiplier,
                    index_prices_path=percorso_prezzi, force_full=True
                )
                _msg = f"Ricalcolati da zero {_n_aggiunti} giorni storici per questa scadenza."
                if _oi_disponibile:
                    aggiorna_riga_oggi_stats(
                        STATS_LOG_PATH, selected_expiry_date, analysis_date, spot_price,
                        max_pain_strike, pc_ratios, expected_move,
                        int(df_selected_expiry_oi['DTE_Days'].iloc[0]), risk_free_rate, dividend_yield,
                        call_volume_tot=df_selected_expiry_oi.loc[df_selected_expiry_oi['Type'] == 'Call', 'Vol'].sum(),
                        put_volume_tot=df_selected_expiry_oi.loc[df_selected_expiry_oi['Type'] == 'Put', 'Vol'].sum()
                    )
                    _msg += " Riga di oggi aggiornata."
                else:
                    _msg += " Riga di oggi NON aggiornata (OI non disponibile oggi)."
                st.success(_msg)

        _scadenza_str_stats = pd.Timestamp(selected_expiry_date).date().isoformat()
        if os.path.exists(STATS_LOG_PATH):
            _log_stats_tutto = pd.read_csv(STATS_LOG_PATH)
            _storico_stats = _log_stats_tutto[_log_stats_tutto['scadenza'].astype(str) == _scadenza_str_stats].copy()
            _storico_stats = _storico_stats.sort_values('data').reset_index(drop=True)
        else:
            _storico_stats = pd.DataFrame()

        if _storico_stats.empty:
            st.info("Nessuno storico ancora salvato per questa scadenza: premi 'Aggiorna storico Stats' qui sopra.")
        elif len(_storico_stats) < 2:
            st.info("Serve almeno un secondo giorno per mostrare un grafico storico.")
        else:
            _storico_stats['_data_dt'] = pd.to_datetime(_storico_stats['data'])

            st.caption(
                "💡 Lo zoom (+) del grafico non riadatta automaticamente l'asse verticale: per restringere "
                "il periodo mostrato conviene usare il filtro qui sotto invece dello zoom."
            )
            col_fs1, col_fs2 = st.columns([1, 1.4])
            with col_fs1:
                _modalita_filtro_stats = st.radio(
                    "Periodo da visualizzare", options=["Tutto", "Ultimi N giorni", "Da una data"],
                    horizontal=True, key="storico_stats_filtro_modalita"
                )
            _storico_stats_filtrato = _storico_stats
            if _modalita_filtro_stats == "Ultimi N giorni":
                with col_fs2:
                    _n_giorni_filtro_stats = st.number_input(
                        "Quanti giorni di calendario (dall'ultimo disponibile)",
                        min_value=1, value=60, step=1, key="storico_stats_n_giorni"
                    )
                _cutoff_stats = _storico_stats['_data_dt'].max() - pd.Timedelta(days=int(_n_giorni_filtro_stats))
                _storico_stats_filtrato = _storico_stats[_storico_stats['_data_dt'] >= _cutoff_stats]
            elif _modalita_filtro_stats == "Da una data":
                with col_fs2:
                    _data_da_stats = st.date_input(
                        "Mostra a partire da",
                        value=_storico_stats['_data_dt'].min().date(),
                        min_value=_storico_stats['_data_dt'].min().date(),
                        max_value=_storico_stats['_data_dt'].max().date(),
                        key="storico_stats_data_da"
                    )
                _storico_stats_filtrato = _storico_stats[_storico_stats['_data_dt'].dt.date >= _data_da_stats]

            _storico_stats_filtrato = _storico_stats_filtrato.drop(columns=['_data_dt']).reset_index(drop=True)
            _storico_stats = _storico_stats.drop(columns=['_data_dt'])

            if len(_storico_stats_filtrato) < 2:
                st.info("Meno di due giorni nel periodo selezionato: allarga il filtro per vedere un grafico.")
            else:
                _fig_stats = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                    row_heights=[0.34, 0.33, 0.33],
                    subplot_titles=("Spot vs Max Pain", "P/C Ratio (OI e Volume)", "Spot vs Bande Expected Move")
                )
                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['spot'], mode='lines+markers', name='Spot',
                    line=dict(color='#60a5fa'), hovertemplate='%{x}<br>Spot: %{y:,.2f}<extra></extra>'
                ), row=1, col=1)
                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['max_pain_strike'], mode='lines+markers', name='Max Pain',
                    line=dict(color='#fbbf24'), hovertemplate='%{x}<br>Max Pain: %{y:,.0f}<extra></extra>'
                ), row=1, col=1)

                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['pc_oi_ratio'], mode='lines+markers', name='P/C Ratio (OI)',
                    line=dict(color='#34d399'), hovertemplate='%{x}<br>P/C OI: %{y:.3f}<extra></extra>'
                ), row=2, col=1)
                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['pc_vol_ratio'], mode='lines+markers', name='P/C Ratio (Volume)',
                    line=dict(color='#f97316'),
                    customdata=_storico_stats_filtrato[['call_volume_tot', 'put_volume_tot']].to_numpy(),
                    hovertemplate='%{x}<br>P/C Volume: %{y:.3f}<br>Call: %{customdata[0]:,.0f} · Put: %{customdata[1]:,.0f}<extra></extra>'
                ), row=2, col=1)
                _fig_stats.add_hline(y=1.0, line_dash='dot', line_color='#94a3b8', row=2, col=1)

                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['spot'], mode='lines+markers', name='Spot ',
                    line=dict(color='#60a5fa'), showlegend=False,
                    hovertemplate='%{x}<br>Spot: %{y:,.2f}<extra></extra>'
                ), row=3, col=1)
                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['upper_band'], mode='lines', name='Banda Superiore',
                    line=dict(color='#f87171', dash='dash'), hovertemplate='%{x}<br>Banda Sup.: %{y:,.2f}<extra></extra>'
                ), row=3, col=1)
                _fig_stats.add_trace(go.Scatter(
                    x=_storico_stats_filtrato['data'], y=_storico_stats_filtrato['lower_band'], mode='lines', name='Banda Inferiore',
                    line=dict(color='#f87171', dash='dash'), hovertemplate='%{x}<br>Banda Inf.: %{y:,.2f}<extra></extra>'
                ), row=3, col=1)

                _fig_stats.update_layout(
                    height=750, template='plotly_dark', margin=dict(l=10, r=10, t=40, b=10),
                    legend=dict(orientation='h', yanchor='bottom', y=1.02), hovermode='x unified'
                )
                _fig_stats.update_xaxes(showspikes=True, spikemode='across', spikesnap='cursor',
                                         spikethickness=1, spikedash='dot', spikecolor='#94a3b8')
                st.plotly_chart(_fig_stats, width="stretch", key="storico_stats_chart")
                st.caption(
                    f"Scadenza {selected_expiry_label}: {len(_storico_stats_filtrato)} giorni mostrati su "
                    f"{len(_storico_stats)} salvati in totale. I giorni con fonte 'ricostruito da dati/' usano "
                    "risk-free/dividend attuali come approssimazione; i giorni con fonte 'oggi (live)' usano i "
                    "valori realmente in vigore quel giorno."
                )

            with st.expander("📋 Vedi tabella storico Stats", expanded=False):
                st.dataframe(_storico_stats_filtrato, width="stretch", hide_index=True)


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
        if not _spot_disponibile:
            st.info(_messaggio_dati_insufficienti())
        elif st.button("Calcola superficie 3D"):
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
            for _col, _default in [('significativo', True), ('ora', ''), ('spot_preciso', np.nan), ('nota', '')]:
                if _col not in _log_df.columns:
                    _log_df[_col] = _default
            _log_df['significativo'] = _log_df['significativo'].astype(object).where(_log_df['significativo'].notna(), True)
            _log_df['ora'] = _log_df['ora'].astype(object).fillna('')
            _log_df['nota'] = _log_df['nota'].astype(object).fillna('')

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
                _editable_cols = ['significativo', 'ora', 'spot_preciso', 'nota']
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
                        "nota": st.column_config.TextColumn(
                            "Nota", help="Osservazioni libere su questo evento (es. ipotesi da verificare in seguito)",
                            width="large"
                        ),
                        **{c: st.column_config.Column(disabled=True, width="small") for c in _key_cols + _other_cols}
                    },
                    hide_index=True, width="stretch", key="log_editor"
                )
                if st.button("Salva modifiche (flag, ora, spot preciso, nota)"):
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
arrivare in due modi diversi: copia-incolla manuale nell'app, oppure `rigenera_file_dati.py`
da terminale (scarica un giorno completo direttamente da Euronext). Solo il primo modo
aggiorna questo storico automaticamente; il secondo scrive direttamente su disco, senza
passare dall'app. Il bottone qui sotto legge **tutti** i file `dati/YYYYMMDD.csv` presenti,
indipendentemente da come sono arrivati lì, e ricostruisce lo storico da zero — così non
ne manca nessuno.

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
            _storico_totali = _storico_totali.copy()
            _storico_totali['data'] = _storico_totali['data'].astype(str)
            _storico_totali['_data_dt'] = pd.to_datetime(_storico_totali['data'])

            st.caption(
                "💡 Lo zoom (+) del grafico non riadatta automaticamente l'asse verticale: per restringere "
                "il periodo mostrato conviene usare il filtro qui sotto invece dello zoom."
            )
            col_f1, col_f2 = st.columns([1, 1.4])
            with col_f1:
                _modalita_filtro_storico = st.radio(
                    "Periodo da visualizzare", options=["Tutto", "Ultimi N giorni", "Da una data"],
                    horizontal=True, key="storico_totali_filtro_modalita"
                )
            _storico_filtrato = _storico_totali
            if _modalita_filtro_storico == "Ultimi N giorni":
                with col_f2:
                    _n_giorni_filtro_storico = st.number_input(
                        "Quanti giorni di calendario (dall'ultimo disponibile)",
                        min_value=1, value=60, step=1, key="storico_totali_n_giorni"
                    )
                _cutoff_storico = _storico_totali['_data_dt'].max() - pd.Timedelta(days=int(_n_giorni_filtro_storico))
                _storico_filtrato = _storico_totali[_storico_totali['_data_dt'] >= _cutoff_storico]
            elif _modalita_filtro_storico == "Da una data":
                with col_f2:
                    _data_da_storico = st.date_input(
                        "Mostra a partire da",
                        value=_storico_totali['_data_dt'].min().date(),
                        min_value=_storico_totali['_data_dt'].min().date(),
                        max_value=_storico_totali['_data_dt'].max().date(),
                        key="storico_totali_data_da"
                    )
                _storico_filtrato = _storico_totali[_storico_totali['_data_dt'].dt.date >= _data_da_storico]

            _storico_filtrato = _storico_filtrato.drop(columns=['_data_dt']).reset_index(drop=True)

            # ---------------------------------------------------------------
            # Eventi significativi sul grafico: marker + etichette sul pannello
            # Spot, per vedere a colpo d'occhio se un movimento di posizionamento
            # coincide con un movimento di prezzo (l'obiettivo per cui e' nato
            # il log eventi). Riusa la colonna 'significativo' gia' presente e
            # modificabile nel tab Eventi Volume, con in piu' un filtro
            # opzionale sul notional: 100 pezzi non contano nulla su uno strike
            # a 2 punti dallo spot, ma possono essere enormi su uno strike
            # lontanissimo (deep ITM/OTM) - il notional in € cattura questo
            # meglio del solo numero di contratti.
            # ---------------------------------------------------------------
            _eventi_per_grafico = None
            if os.path.exists(VOLUME_LOG_PATH):
                try:
                    _log_eventi_storico = pd.read_csv(VOLUME_LOG_PATH)
                    if not _log_eventi_storico.empty:
                        _log_eventi_storico['significativo'] = (
                            _log_eventi_storico['significativo'].astype(str).str.lower().isin(['true', '1', 'vero'])
                        )
                        _eventi_per_grafico = _log_eventi_storico[_log_eventi_storico['significativo']].copy()
                except Exception:
                    _eventi_per_grafico = None

            _mostra_eventi_storico = True
            _notional_min_storico = 0
            if _eventi_per_grafico is not None and not _eventi_per_grafico.empty:
                col_ev1, col_ev2 = st.columns([1, 1.4])
                with col_ev1:
                    _mostra_eventi_storico = st.checkbox(
                        "📌 Mostra eventi significativi sul grafico Spot", value=True,
                        key="storico_mostra_eventi",
                        help="Marker ed etichette sul pannello Spot per ogni evento con flag "
                             "'Significativo' attivo nel log (tab Eventi Volume)."
                    )
                with col_ev2:
                    _notional_min_storico = st.number_input(
                        "Notional minimo da mostrare (€, 0 = nessun filtro aggiuntivo)",
                        min_value=0, value=0, step=100000, key="storico_notional_min_eventi",
                        help="Filtro aggiuntivo oltre al flag 'Significativo': utile per nascondere "
                             "eventi con volume sopra soglia ma notional contenuto, e concentrarsi "
                             "sui movimenti che pesano di più in termini di impegno di capitale."
                    )

            if len(_storico_filtrato) >= 2:
                _fig = make_subplots(
                    rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                    row_heights=[0.5, 0.25, 0.25],
                    subplot_titles=("Spot FTSEMIB", "Open Interest totale", "Volume totale")
                )
                _fig.add_trace(go.Scatter(
                    x=_storico_filtrato['data'], y=_storico_filtrato['spot'], mode='lines+markers', name='Spot',
                    line=dict(color='#60a5fa'), hovertemplate='%{x}<br>Spot: %{y:,.2f}<extra></extra>'
                ), row=1, col=1)

                if _mostra_eventi_storico and _eventi_per_grafico is not None and not _eventi_per_grafico.empty:
                    _ev_plot = _eventi_per_grafico[
                        _eventi_per_grafico['notional_stimato_eur'].fillna(0) >= _notional_min_storico
                    ].copy()
                    # Limita agli eventi nel periodo attualmente filtrato, cosi' i marker
                    # restano coerenti col resto del grafico (stesso filtro periodo).
                    _date_visibili_storico = set(_storico_filtrato['data'].astype(str))
                    _ev_plot = _ev_plot[_ev_plot['data_riferimento'].astype(str).isin(_date_visibili_storico)]

                    if not _ev_plot.empty:
                        # Piu' eventi nello stesso giorno: aggrega per data cosi' il grafico
                        # resta leggibile (un marker/etichetta per giorno, dettaglio nel hover).
                        _spot_by_date_storico = dict(zip(_storico_filtrato['data'].astype(str), _storico_filtrato['spot']))

                        def _riassumi_eventi_giorno(gruppo):
                            _righe = []
                            for _, r in gruppo.iterrows():
                                _tipo_seg = 'C' if r['tipo'] == 'Call' else 'P'
                                _righe.append(f"{_tipo_seg}{r['strike']:.0f} ({r['volume']:.0f}pz, €{r['notional_stimato_eur']:,.0f})")
                            return '<br>'.join(_righe)

                        _ev_grouped = _ev_plot.groupby('data_riferimento').apply(
                            lambda g: pd.Series({
                                'n_eventi': len(g),
                                'notional_tot': g['notional_stimato_eur'].sum(),
                                'dettaglio': _riassumi_eventi_giorno(g),
                                'prevalenza': 'Call' if (g['tipo'] == 'Call').sum() >= (g['tipo'] == 'Put').sum() else 'Put',
                            }), include_groups=False
                        ).reset_index()
                        _ev_grouped['data_riferimento'] = _ev_grouped['data_riferimento'].astype(str)
                        _ev_grouped['y_spot'] = _ev_grouped['data_riferimento'].map(_spot_by_date_storico)
                        _ev_grouped = _ev_grouped.dropna(subset=['y_spot'])

                        if not _ev_grouped.empty:
                            _colori_ev = _ev_grouped['prevalenza'].map({'Call': '#34d399', 'Put': '#f87171'})
                            _etichette_ev = _ev_grouped.apply(
                                lambda r: (f"{r['n_eventi']}× " if r['n_eventi'] > 1 else '') +
                                          ('📈' if r['prevalenza'] == 'Call' else '📉'),
                                axis=1
                            )
                            _fig.add_trace(go.Scatter(
                                x=_ev_grouped['data_riferimento'], y=_ev_grouped['y_spot'],
                                mode='markers+text', name='Evento significativo',
                                text=_etichette_ev, textposition='top center',
                                textfont=dict(size=11, color='#e5e7eb'),
                                marker=dict(color=_colori_ev, size=13, symbol='star',
                                            line=dict(color='#e5e7eb', width=1)),
                                customdata=_ev_grouped[['dettaglio', 'notional_tot']],
                                hovertemplate='%{x}<br>%{customdata[0]}<br>Notional totale: €%{customdata[1]:,.0f}<extra></extra>'
                            ), row=1, col=1)

                _fig.add_trace(go.Scatter(
                    x=_storico_filtrato['data'], y=_storico_filtrato['oi_totale'], mode='lines+markers', name='OI totale',
                    line=dict(color='#34d399'), hovertemplate='%{x}<br>OI totale: %{y:,.0f}<extra></extra>'
                ), row=2, col=1)
                _fig.add_trace(go.Scatter(
                    x=_storico_filtrato['data'], y=_storico_filtrato['volume_totale'], mode='lines+markers', name='Volume totale',
                    line=dict(color='#f97316'), hovertemplate='%{x}<br>Volume totale: %{y:,.0f}<extra></extra>'
                ), row=3, col=1)
                _fig.update_layout(
                    height=950, template='plotly_dark', margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
                    hovermode='x unified'
                )
                _fig.update_xaxes(showspikes=True, spikemode='across', spikesnap='cursor',
                                   spikethickness=1, spikedash='dot', spikecolor='#94a3b8')
                st.plotly_chart(_fig, width="stretch", key="storico_totali_chart")
                st.caption(

                    f"{len(_storico_filtrato)} giorni mostrati su {len(_storico_totali)} totali disponibili. "
                    "Tre pannelli allineati sulla stessa data, ciascuno con la propria scala. Passa il cursore "
                    "su un punto qualsiasi: la data compare in alto al tooltip, con una linea verticale che "
                    "attraversa tutti e tre i pannelli per allineare visivamente lo stesso giorno. Confronta se "
                    "un salto di OI o Volume coincide con un movimento marcato dello spot in alto."
                )
            elif len(_storico_filtrato) == 1:
                st.info("Solo un giorno nel periodo selezionato: allarga il filtro per vedere un grafico.")
            else:
                st.info("Nessun giorno nel periodo selezionato.")
            st.dataframe(_storico_filtrato.sort_values('data', ascending=False), width="stretch", hide_index=True)

    # ========================= TAB NOTE =========================
    with tab_note:
        st.header("Diario delle osservazioni")
        st.caption(
            "Un unico diario per tutta l'app, invece di un campo note separato in ogni tab: annota qui "
            "un'osservazione (es. un'ipotesi su un movimento, un'anomalia da riverificare), indicando "
            "opzionalmente il contesto (quale scadenza/tab/strike stavi guardando). Resta salvato con "
            "data e ora, consultabile in qualunque momento."
        )

        NOTE_LOG_PATH = "dati_locali/diario_note.csv"

        with st.form("nuova_nota_form", clear_on_submit=True):
            _contesto = st.text_input("Contesto (opzionale)", placeholder="es. GEX settembre, evento 24/7 strike 50500...")
            _testo_nota = st.text_area("Nota", placeholder="Scrivi qui la tua osservazione...")
            _submitted = st.form_submit_button("💾 Salva nota")
            if _submitted:
                if _testo_nota.strip():
                    aggiungi_nota_diario(NOTE_LOG_PATH, _contesto, _testo_nota.strip())
                    st.success("Nota salvata.")
                else:
                    st.warning("Scrivi qualcosa prima di salvare.")

        st.divider()
        st.subheader("Note salvate")

        if os.path.exists(NOTE_LOG_PATH):
            _diario = pd.read_csv(NOTE_LOG_PATH)
            _diario['contesto'] = _diario['contesto'].astype(object).fillna('')
            if _diario.empty:
                st.info("Nessuna nota ancora salvata.")
            else:
                for _, _riga in _diario.sort_values('id', ascending=False).iterrows():
                    _id_nota = _riga['id']
                    _chiave_editing = f"editing_nota_{_id_nota}"
                    _in_modifica = st.session_state.get(_chiave_editing, False)

                    with st.container(border=True):
                        _intestazione = f"**{_riga['data_ora']}**"
                        if _riga['contesto']:
                            _intestazione += f" — _{_riga['contesto']}_"
                        st.markdown(_intestazione)

                        if _in_modifica:
                            _testo_modificato = st.text_area(
                                "Testo", value=_riga['nota'], key=f"nota_testo_{_id_nota}",
                                label_visibility="collapsed"
                            )
                            _col_salva, _col_annulla, _col_elimina = st.columns([1, 1, 1])
                            with _col_salva:
                                if st.button("💾 Salva", key=f"salva_nota_{_id_nota}"):
                                    modifica_nota_diario(NOTE_LOG_PATH, _id_nota, _testo_modificato)
                                    st.session_state[_chiave_editing] = False
                                    st.success("Nota aggiornata.")
                                    st.rerun()
                            with _col_annulla:
                                if st.button("Annulla", key=f"annulla_nota_{_id_nota}"):
                                    st.session_state[_chiave_editing] = False
                                    st.rerun()
                            with _col_elimina:
                                if st.button("🗑️ Elimina", key=f"elimina_nota_{_id_nota}"):
                                    elimina_nota_diario(NOTE_LOG_PATH, _id_nota)
                                    st.rerun()
                        else:
                            st.write(_riga['nota'])
                            if st.button("✏️ Modifica", key=f"modifica_nota_{_id_nota}"):
                                st.session_state[_chiave_editing] = True
                                st.rerun()
        else:
            st.info("Nessuna nota ancora salvata: scrivi la prima qui sopra.")

    # ========================= TAB DECADIMENTO =========================
    with tab_decay:
        st.header(f"Decadimento Temporale (Theta) — {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In parole semplici.** Un'opzione perde valore man mano che passa il tempo, anche se
il sottostante restasse fermo — è il cosiddetto *decadimento temporale* (Theta). Questo
grafico mostra come varierebbe il prezzo teorico dello strike **scelto qui sotto** (di
default il più vicino allo spot, ATM), giorno dopo giorno, fino alla scadenza stessa.

**⚠️ È una stima "a condizioni ferme", non una previsione.** Il calcolo tiene **fissi**
lo spot e la volatilità implicita, e fa variare solo il tempo residuo. Nella realtà
spot e volatilità si muoveranno, quindi il prezzo reale seguirà una strada diversa da
questa curva — è utile per farsi un'idea della *forma* del decadimento (tipicamente si
accelera avvicinandosi alla scadenza), non per prevedere il prezzo esatto di un giorno
specifico.

**🎯 Stima IV robusta su più giorni.** Il Settle di un singolo giorno può risultare
anomalo (fuori dai limiti di no-arbitraggio) senza che lo strike sia davvero illiquido.
Per ridurlo, la IV usata qui è la **mediana** delle IV valide trovate tra oggi e gli
ultimi file disponibili in `dati/` per lo stesso strike (fino a 5 giorni, richiesti
almeno 3 validi) — Call e Put calcolate **separatamente**, perché possono avere skew
diverso. Se i giorni validi non bastano, si usa la sola IV di oggi (se disponibile).
La tabella di riepilogo qui sotto mostra questo colpo d'occhio per **tutti** gli strike
della scadenza insieme, non solo per quello selezionato per il grafico.

**⚠️ Nota.** Questo tab **non richiede l'Open Interest**: funziona anche su un
caricamento intraday, perché si basa solo su Settle (oggi e nei giorni precedenti) e
sullo spot storico.
                """
            )

        if not _spot_disponibile:
            st.info(_messaggio_dati_insufficienti())
        else:
            _strikes_disponibili = sorted(df_selected_expiry['Strike'].unique())
            if not _strikes_disponibili:
                st.warning("Nessuno strike disponibile per questa scadenza.")
            else:
                # Stima IV robusta per TUTTI gli strike/tipo in un solo passaggio sui file
                # storici (piu' efficiente che richiamarla strike per strike).
                _iv_oggi_map = {}
                for _k in _strikes_disponibili:
                    for _t in ['Call', 'Put']:
                        _row = df_selected_expiry[(df_selected_expiry['Strike'] == _k) & (df_selected_expiry['Type'] == _t)]
                        _iv_oggi_map[(_k, _t)] = _row['IV'].iloc[0] if not _row.empty else None

                _tabella_stime = estimate_iv_multi_day_batch(
                    oggi_date=analysis_date.date(), iv_oggi_map=_iv_oggi_map,
                    dati_folder=DATI_FOLDER_DEFAULT, storico_totali_path=TOTALI_LOG_PATH,
                    expiration_date=selected_expiry_date, strikes=_strikes_disponibili,
                    risk_free_rate=risk_free_rate, dividend_yield=dividend_yield,
                    index_prices_path=percorso_prezzi, n_giorni=5, min_validi=3
                )

                def _iv_finale_e_fonte(strike, tipo):
                    _stima = _tabella_stime[(strike, tipo)]
                    _iv_oggi = _iv_oggi_map[(strike, tipo)]
                    if _stima['iv_mediana'] is not None:
                        return _stima['iv_mediana'], "mediana su più giorni", _stima
                    if _iv_oggi is not None and not pd.isna(_iv_oggi) and _iv_oggi > 0:
                        return float(_iv_oggi), "solo oggi (dati storici insufficienti)", _stima
                    return None, "non disponibile", _stima

                with st.expander("📋 Colpo d'occhio: stima IV per tutti gli strike di questa scadenza", expanded=False):
                    _righe_riepilogo = []
                    for _k in _strikes_disponibili:
                        _iv_c, _fonte_c, _stima_c = _iv_finale_e_fonte(_k, 'Call')
                        _iv_p, _fonte_p, _stima_p = _iv_finale_e_fonte(_k, 'Put')
                        _righe_riepilogo.append({
                            'Strike': _k,
                            'IV Call': f"{_iv_c:.2%}" if _iv_c is not None else "N/A",
                            'Fonte Call': _fonte_c,
                            'Giorni validi Call': f"{_stima_c['n_validi']}/{_stima_c['n_esaminati']}",
                            'IV Put': f"{_iv_p:.2%}" if _iv_p is not None else "N/A",
                            'Fonte Put': _fonte_p,
                            'Giorni validi Put': f"{_stima_p['n_validi']}/{_stima_p['n_esaminati']}",
                        })
                    st.dataframe(pd.DataFrame(_righe_riepilogo), width="stretch", hide_index=True)
                    st.caption(
                        "'Giorni validi' = quante IV utilizzabili trovate sui giorni esaminati (max 5, oggi incluso). "
                        "Sotto 3 giorni validi la stima passa alla sola IV di oggi, se disponibile."
                    )

                _idx_atm_default = min(
                    range(len(_strikes_disponibili)),
                    key=lambda i: abs(_strikes_disponibili[i] - spot_price)
                )
                _strike_scelto = st.selectbox(
                    "Strike da analizzare nel grafico (default: più vicino allo spot)",
                    options=_strikes_disponibili, index=_idx_atm_default,
                    format_func=lambda k: f"{k:,.0f}", key="decay_strike_select"
                )

                _dte_max = int(df_selected_expiry.loc[df_selected_expiry['Strike'] == _strike_scelto, 'DTE_Days'].iloc[0])

                if _dte_max <= 0:
                    st.info("Questa scadenza è già a 0 giorni residui (o scaduta): nessuna curva di decadimento da mostrare.")
                else:
                    _iv_call, _fonte_call, _stima_call = _iv_finale_e_fonte(_strike_scelto, 'Call')
                    _iv_put, _fonte_put, _stima_put = _iv_finale_e_fonte(_strike_scelto, 'Put')

                    if _iv_call is None and _iv_put is None:
                        st.warning(
                            "IV non disponibile per questo strike né oggi né nei giorni precedenti in `dati/`: "
                            "impossibile calcolare il decadimento. Prova un altro strike."
                        )
                    else:
                        col_d1, col_d2, col_d3 = st.columns(3)
                        col_d1.metric("Strike", f"{_strike_scelto:,.0f}")
                        col_d2.metric("IV Call usata", f"{_iv_call:.2%}" if _iv_call else "N/A", help=_fonte_call)
                        col_d3.metric("IV Put usata", f"{_iv_put:.2%}" if _iv_put else "N/A", help=_fonte_put)
                        st.caption(
                            f"Call: {_fonte_call} ({_stima_call['n_validi']}/{_stima_call['n_esaminati']} giorni validi). "
                            f"Put: {_fonte_put} ({_stima_put['n_validi']}/{_stima_put['n_esaminati']} giorni validi)."
                        )

                        with st.expander("📋 Dettaglio giorni usati per la stima (strike selezionato)", expanded=False):
                            for _tipo, _stima in [('Call', _stima_call), ('Put', _stima_put)]:
                                st.markdown(f"**{_tipo}**")
                                _df_det = pd.DataFrame([
                                    {
                                        'Data': f"{d.strftime('%d/%m/%Y')} ({_WEEKDAYS_IT[d.weekday()]})",
                                        'IV': f"{iv:.2%}" if iv is not None else "n/d (Settle non invertibile o giorno mancante)"
                                    }
                                    for d, iv in _stima['dettaglio']
                                ])
                                st.dataframe(_df_det, width="stretch", hide_index=True)
                            st.caption(
                                "Sabati, domeniche e festivi non hanno un file in `dati/`: è normale che i giorni "
                                "esaminati non siano consecutivi sul calendario."
                            )

                        _giorni = np.linspace(_dte_max, 0, 60)
                        _fig_decay = go.Figure()
                        if _iv_call is not None:
                            _prezzi_call = [_bs_price(spot_price, _strike_scelto, max(g / 365.25, 1e-6),
                                                       risk_free_rate, dividend_yield, _iv_call, 'Call') for g in _giorni]
                            _fig_decay.add_trace(go.Scatter(
                                x=_giorni, y=_prezzi_call, mode='lines', name='Call', line=dict(color='#34d399', width=2.5),
                                hovertemplate='%{x:.1f} giorni residui<br>Call: %{y:,.2f}<extra></extra>'
                            ))
                        if _iv_put is not None:
                            _prezzi_put = [_bs_price(spot_price, _strike_scelto, max(g / 365.25, 1e-6),
                                                      risk_free_rate, dividend_yield, _iv_put, 'Put') for g in _giorni]
                            _fig_decay.add_trace(go.Scatter(
                                x=_giorni, y=_prezzi_put, mode='lines', name='Put', line=dict(color='#f87171', width=2.5),
                                hovertemplate='%{x:.1f} giorni residui<br>Put: %{y:,.2f}<extra></extra>'
                            ))
                        _fig_decay.update_xaxes(title="Giorni alla scadenza", autorange='reversed')
                        _fig_decay.update_yaxes(title="Prezzo teorico (Black-Scholes)")
                        _fig_decay.update_layout(template='plotly_dark', height=450, margin=dict(l=10, r=10, t=30, b=10),
                                                  hovermode='x unified')
                        st.plotly_chart(_fig_decay, width="stretch", key="decay_chart")
                        st.caption(
                            f"Curva calcolata con spot {spot_price:,.2f} tenuto fisso al valore odierno — solo il "
                            f"tempo residuo cambia, da {_dte_max} giorni a 0. Strike {_strike_scelto:,.0f}."
                        )

                        with st.expander("📋 Vedi in forma tabellare (giorni interi)", expanded=False):
                            _giorni_interi = list(range(_dte_max, -1, -1))
                            _tabella_decay = []
                            for g in _giorni_interi:
                                T = max(g / 365.25, 1e-6)
                                _data_g = (selected_expiry_date - pd.Timedelta(days=g)).date()
                                _riga = {'Giorni residui': g, 'Data': _data_g.strftime('%d/%m/%Y')}
                                if _iv_call is not None:
                                    _riga['Call'] = round(_bs_price(spot_price, _strike_scelto, T, risk_free_rate, dividend_yield, _iv_call, 'Call'), 2)
                                if _iv_put is not None:
                                    _riga['Put'] = round(_bs_price(spot_price, _strike_scelto, T, risk_free_rate, dividend_yield, _iv_put, 'Put'), 2)
                                _tabella_decay.append(_riga)
                            st.dataframe(pd.DataFrame(_tabella_decay), width="stretch", hide_index=True)

    # ========================= TAB RIPARTIZIONE OI =========================
    with tab_ripart:
        st.header(f"Ripartizione OI — {selected_expiry_label}")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**Cosa mostra.** Per ogni strike di questa scadenza, l'Open Interest di Put (blu) e
Call (arancio) come barre, più due linee cumulate in percentuale:

- **Ripart. Put** (grigia): quanta % dell'OI Put totale si trova a strike **minori o
  uguali** a quello indicato, salendo da sinistra verso destra (parte vicino a 0%,
  arriva al 100% allo strike più alto con OI put).
- **Ripart. Call** (gialla): quanta % dell'OI Call totale si trova a strike
  **maggiori o uguali** a quello indicato, quindi scende da sinistra verso destra
  (parte vicino al 100%, arriva verso 0% allo strike più alto).

**Il punto di Equilibrio.** È lo strike dove le due linee si incrociano: da un lato
la "massa" cumulata di Put sale, dall'altro la "massa" cumulata di Call scende — il
punto di incrocio è dove le due si bilanciano. Non ha lo stesso significato del Max
Pain o del Gamma Flip: è un indicatore distinto, utile come ulteriore riferimento.

**⚠️ Attenzione.** Qui si guarda **tutta** la catena della scadenza (non solo la
fascia vicina allo spot come nei Wall), quindi include anche OI molto lontano dai
soldi (deep ITM/OTM) — utile per la forma complessiva della distribuzione, meno per
decisioni operative di brevissimo termine.
                """
            )

        _df_rip = df_selected_expiry_oi[['Strike', 'Type', 'OI']].groupby(['Strike', 'Type'], as_index=False)['OI'].sum()
        _pivot_rip = _df_rip.pivot(index='Strike', columns='Type', values='OI').fillna(0).sort_index()
        if 'Put' not in _pivot_rip.columns:
            _pivot_rip['Put'] = 0.0
        if 'Call' not in _pivot_rip.columns:
            _pivot_rip['Call'] = 0.0

        _tot_put = _pivot_rip['Put'].sum()
        _tot_call = _pivot_rip['Call'].sum()
        _tot_oi_rip = _tot_put + _tot_call

        if _tot_oi_rip == 0:
            st.warning("Nessun Open Interest disponibile su questa scadenza: impossibile calcolare la ripartizione.")
        else:
            _pivot_rip['ripart_put'] = (_pivot_rip['Put'].cumsum() / _tot_put * 100) if _tot_put > 0 else 0.0
            _pivot_rip['ripart_call'] = (_pivot_rip['Call'][::-1].cumsum()[::-1] / _tot_call * 100) if _tot_call > 0 else 0.0

            _idx_equilibrio = None
            for _i in range(len(_pivot_rip)):
                if _pivot_rip['ripart_put'].iloc[_i] >= _pivot_rip['ripart_call'].iloc[_i]:
                    _idx_equilibrio = _i
                    break
            _strike_equilibrio = _pivot_rip.index[_idx_equilibrio] if _idx_equilibrio is not None else None
            _pct_equilibrio = _pivot_rip['ripart_put'].iloc[_idx_equilibrio] if _idx_equilibrio is not None else None

            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("OI Totale", f"{_tot_oi_rip:,.0f}")
            col_r2.metric("Put", f"{_tot_put:,.0f} ({_tot_put/_tot_oi_rip:.1%})")
            col_r3.metric("Call", f"{_tot_call:,.0f} ({_tot_call/_tot_oi_rip:.1%})")
            col_r4.metric("Equilibrio", f"{_strike_equilibrio:,.0f} ({_pct_equilibrio:.1f}%)" if _strike_equilibrio is not None else "N/A")

            _fig_rip = make_subplots(specs=[[{"secondary_y": True}]])
            _fig_rip.add_trace(go.Bar(x=_pivot_rip.index, y=_pivot_rip['Put'], name='PUT',
                                       marker_color='#60a5fa', opacity=0.75), secondary_y=False)
            _fig_rip.add_trace(go.Bar(x=_pivot_rip.index, y=_pivot_rip['Call'], name='CALL',
                                       marker_color='#f97316', opacity=0.75), secondary_y=False)
            _fig_rip.add_trace(go.Scatter(x=_pivot_rip.index, y=_pivot_rip['ripart_put'], name='Ripart. Put',
                                           mode='lines+markers', line=dict(color='#9ca3af', width=2),
                                           marker=dict(size=4)), secondary_y=True)
            _fig_rip.add_trace(go.Scatter(x=_pivot_rip.index, y=_pivot_rip['ripart_call'], name='Ripart. Call',
                                           mode='lines+markers', line=dict(color='#fde047', width=2),
                                           marker=dict(size=4)), secondary_y=True)
            if _strike_equilibrio is not None:
                _fig_rip.add_vline(x=_strike_equilibrio, line_dash='dash', line_color='#ef4444')
            _fig_rip.update_yaxes(title_text="Open Interest", secondary_y=False)
            _fig_rip.update_yaxes(title_text="Ripartizione %", secondary_y=True, range=[0, 100])
            _fig_rip.update_xaxes(title_text="Strike")
            _fig_rip.update_layout(template='plotly_dark', height=550, margin=dict(l=10, r=10, t=30, b=10),
                                    barmode='overlay', hovermode='x unified',
                                    legend=dict(orientation='h', yanchor='bottom', y=1.02))
            st.plotly_chart(_fig_rip, width="stretch", key="ripartizione_chart")

            with st.expander("📋 Vedi in forma tabellare", expanded=False):
                _tabella_rip = _pivot_rip.reset_index()[['Strike', 'Put', 'Call', 'ripart_put', 'ripart_call']]
                _tabella_rip.columns = ['Strike', 'OI Put', 'OI Call', 'Ripart. Put %', 'Ripart. Call %']
                st.dataframe(_tabella_rip.round(1), width="stretch", hide_index=True)

    # ========================= TAB TRENO =========================
    with tab_treno:
        st.header("Treno: Settlement Mensili, Trimestrali (Vero Trend) e Ciclo 69")

        with st.expander("ℹ️ Come leggere questa sezione", expanded=False):
            st.markdown(
                """
**In memoria di Treno** (trenotrading), che ha reso pubblico gratuitamente il suo
metodo di analisi ciclica.

**Cosa mostra (primo passo).** Un grafico a barre/candele del FTSEMIB — giornaliero,
settimanale o mensile — con sovrapposti i **settlement mensili** e **trimestrali**
(scadenze MIBO/fituso: terzo venerdì del mese). I settlement trimestrali — Mar/Giu/
Set/Dic — sono quello che Treno chiamava il **"Vero Trend"**.

**⚠️ Semplificazione attuale.** Come valore di settlement si usa il prezzo di
**Apertura** dell'indice nel giorno del terzo venerdì (non il prezzo ufficiale di
regolamento, non fornito in questo dataset). Se quel giorno non è di borsa aperta
(festivo), si usa l'apertura del primo giorno di borsa successivo disponibile. Nella
tabella qui sotto puoi inserire a mano il **settlement ufficiale** quando lo conosci,
per confrontarlo con questa semplificazione.

**Scostamento dal Vero Trend.** Una tabella mostra quanto ogni settlement mensile si
discosta dalla linea che unisce i due settlement trimestrali più vicini (il "Vero
Trend" stesso) — utile per vedere quanto "rumore" fa il mensile dentro l'oscillazione
trimestrale più ampia.

**Prossimi passi.** L'individuazione automatica del ciclo settimanale ("pornociclo")
secondo il metodo di Treno — oscillazione standard e oscillazione inversa (il "69")
— sarà aggiunta in un passo successivo, non ancora in questa versione.
                """
            )

        _percorso_prezzi_treno = st.text_input(
            "Percorso storico prezzi (OHLC)", value=percorso_prezzi, key="percorso_prezzi_treno"
        )
        if not os.path.exists(_percorso_prezzi_treno):
            st.warning(f"File non trovato: `{_percorso_prezzi_treno}`.")
        else:
            _df_prezzi_treno = pd.read_csv(_percorso_prezzi_treno, parse_dates=['time'])
            _df_prezzi_treno = _df_prezzi_treno.dropna(subset=['open', 'high', 'low', 'close'])
            _df_prezzi_treno = _df_prezzi_treno.sort_values('time').drop_duplicates(subset='time').reset_index(drop=True)

            if len(_df_prezzi_treno) < 2:
                st.warning("Servono almeno due giorni di dati OHLC per mostrare un grafico.")
            else:
                st.caption(
                    "💡 Lo zoom (+) del grafico non riadatta automaticamente l'asse verticale: per restringere "
                    "il periodo mostrato conviene usare il filtro qui sotto invece dello zoom."
                )
                col_fp1, col_fp2 = st.columns([1, 1.4])
                with col_fp1:
                    _modalita_filtro_treno = st.radio(
                        "Periodo da visualizzare", options=["Tutto", "Ultimi N giorni", "Da una data"],
                        horizontal=True, key="treno_filtro_modalita"
                    )
                _df_prezzi_treno_filtrato = _df_prezzi_treno
                if _modalita_filtro_treno == "Ultimi N giorni":
                    with col_fp2:
                        _n_giorni_treno = st.number_input(
                            "Quanti giorni di calendario (dall'ultimo disponibile)",
                            min_value=1, value=180, step=1, key="treno_n_giorni"
                        )
                    _cutoff_treno = _df_prezzi_treno['time'].max() - pd.Timedelta(days=int(_n_giorni_treno))
                    _df_prezzi_treno_filtrato = _df_prezzi_treno[_df_prezzi_treno['time'] >= _cutoff_treno]
                elif _modalita_filtro_treno == "Da una data":
                    with col_fp2:
                        _data_da_treno = st.date_input(
                            "Mostra a partire da",
                            value=_df_prezzi_treno['time'].min().date(),
                            min_value=_df_prezzi_treno['time'].min().date(),
                            max_value=_df_prezzi_treno['time'].max().date(),
                            key="treno_data_da"
                        )
                    _df_prezzi_treno_filtrato = _df_prezzi_treno[_df_prezzi_treno['time'].dt.date >= _data_da_treno]

                if len(_df_prezzi_treno_filtrato) < 2:
                    st.info("Meno di due giorni nel periodo selezionato: allarga il filtro per vedere un grafico.")
                else:
                    _data_min_treno = _df_prezzi_treno_filtrato['time'].min().date()
                    _data_max_treno = _df_prezzi_treno_filtrato['time'].max().date()

                    col_t1, col_t2 = st.columns(2)
                    with col_t1:
                        _tf_treno = st.radio(
                            "Timeframe barre", ["Daily", "Weekly", "Monthly"], horizontal=True, key="treno_timeframe"
                        )
                    with col_t2:
                        _tipo_grafico_treno = st.radio(
                            "Tipo grafico", ["Candele", "Barre"], horizontal=True, key="treno_tipo_grafico"
                        )
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        _mostra_mensili = st.checkbox("Settlement mensili", value=True, key="treno_mostra_mensili")
                    with col_c2:
                        _mostra_trimestrali = st.checkbox("Settlement trimestrali (Vero Trend)", value=True, key="treno_mostra_trimestrali")
                    with col_c3:
                        _linea_mensili = st.checkbox("Congiungi i settlement mensili", value=False, key="treno_linea_mensili")

                    _pivot_alti_treno = pd.DataFrame(columns=['idx', 'time', 'valore'])
                    _pivot_bassi_treno = pd.DataFrame(columns=['idx', 'time', 'valore'])
                    if _tf_treno == "Daily":
                        st.markdown("**Rilevazione cicli (metodo Treno, generalizzato) — sperimentale**")
                        st.caption(
                            "Un massimo (o minimo) si considera partenza di un ciclo quando resta 'imbattuto' per "
                            "almeno ¼ della durata del ciclo in esame — es. ~32 barre daily per un ciclo mensile → "
                            "8 barre di conferma; lo stesso rapporto vale a qualunque scala (un ciclo di 8 anni "
                            "richiede ~2 anni senza nuovo estremo). Qui conta solo il tempo (le inside bar non "
                            "vengono escluse). La ricerca **alterna** massimo e minimo (come nel metodo originale): "
                            "confermato un massimo, si cerca il minimo successivo, e viceversa — questo evita falsi "
                            "segnali ripetuti durante un trend continuo in una sola direzione. Calcolato sempre "
                            "sull'intera serie storica, non solo sul periodo filtrato, per evitare artefatti ai "
                            "bordi del filtro."
                        )
                        col_cy1, col_cy2, col_cy3 = st.columns(3)
                        with col_cy1:
                            _ciclo_barre_treno = st.number_input(
                                "Lunghezza ciclo (barre daily)", min_value=4, value=32, step=1, key="treno_ciclo_barre"
                            )
                        with col_cy2:
                            _mostra_ciclo_inverso = st.checkbox(
                                "Partenze cicli inversi (da massimi)", value=True, key="treno_ciclo_inverso"
                            )
                        with col_cy3:
                            _mostra_ciclo_standard = st.checkbox(
                                "Partenze cicli standard (da minimi)", value=False, key="treno_ciclo_standard"
                            )
                        _finestra_conferma_treno = max(1, round(_ciclo_barre_treno / 4))
                        st.caption(f"Finestra di conferma usata: **{_finestra_conferma_treno} barre** senza nuovo estremo.")

                        _df_daily_completo_treno = _df_prezzi_treno.sort_values('time').reset_index(drop=True)
                        _pivot_alti_full, _pivot_bassi_full = rileva_pivot_alternati(
                            _df_daily_completo_treno, _finestra_conferma_treno
                        )
                        if _mostra_ciclo_inverso and not _pivot_alti_full.empty:
                            _pivot_alti_treno = _pivot_alti_full[
                                (pd.to_datetime(_pivot_alti_full['time']).dt.date >= _data_min_treno) &
                                (pd.to_datetime(_pivot_alti_full['time']).dt.date <= _data_max_treno)
                            ]
                        if _mostra_ciclo_standard and not _pivot_bassi_full.empty:
                            _pivot_bassi_treno = _pivot_bassi_full[
                                (pd.to_datetime(_pivot_bassi_full['time']).dt.date >= _data_min_treno) &
                                (pd.to_datetime(_pivot_bassi_full['time']).dt.date <= _data_max_treno)
                            ]

                        # Classificazione della durata di ciascun ciclo completo (pivot dello stesso tipo
                        # consecutivi) secondo la ciclica classica: un ciclo "regolare" dura tra 3/4 e 5/4
                        # della durata nominale; sotto e' troppo corto (probabile rumore/sotto-ciclo), sopra
                        # e' una "lingua" (elongazione) - concetti distinti dal filtro di ampiezza (che valuta
                        # il prezzo, non il tempo): i due si completano a vicenda.
                        _min_barre_ciclo_treno = _ciclo_barre_treno * 3 / 4
                        _max_barre_ciclo_treno = _ciclo_barre_treno * 5 / 4

                        with st.expander("📏 Durata dei cicli rilevati (ciclica classica)", expanded=False):
                            st.caption(
                                f"Con ciclo nominale di {_ciclo_barre_treno:.0f} barre, un ciclo completo (tra due "
                                f"pivot consecutivi dello stesso tipo) si considera **regolare** tra "
                                f"**{_min_barre_ciclo_treno:.0f}** e **{_max_barre_ciclo_treno:.0f}** barre (3/4 - "
                                f"5/4 del nominale). Sotto: probabile rumore/sotto-ciclo. Sopra: lingua "
                                f"(elongazione) — non necessariamente sbagliato, ma da guardare insieme "
                                f"all'ampiezza del movimento, non solo al tempo."
                            )
                            if _mostra_ciclo_inverso:
                                st.markdown("**Cicli inversi (tra massimi consecutivi)**")
                                _tab_durata_alti = classifica_durata_cicli(
                                    _pivot_alti_full, _ciclo_barre_treno,
                                    data_min=_data_min_treno, data_max=_data_max_treno
                                )
                                if _tab_durata_alti.empty:
                                    st.caption("Nessun ciclo completo nel periodo mostrato.")
                                else:
                                    st.dataframe(_tab_durata_alti, width="stretch", hide_index=True)
                            if _mostra_ciclo_standard:
                                st.markdown("**Cicli standard (tra minimi consecutivi)**")
                                _tab_durata_bassi = classifica_durata_cicli(
                                    _pivot_bassi_full, _ciclo_barre_treno,
                                    data_min=_data_min_treno, data_max=_data_max_treno
                                )
                                if _tab_durata_bassi.empty:
                                    st.caption("Nessun ciclo completo nel periodo mostrato.")
                                else:
                                    st.dataframe(_tab_durata_bassi, width="stretch", hide_index=True)

                    _df_pivot_pc_vis = pd.DataFrame()
                    if _tf_treno == "Weekly":
                        _df_bars_treno = (
                            _df_prezzi_treno_filtrato.set_index('time')
                            .resample('W-FRI')
                            .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
                            .dropna()
                            .reset_index()
                        )

                        st.markdown("**🎯 Pornociclo (rilevamento oggettivo) — sperimentale**")
                        _mostra_pornociclo = st.checkbox(
                            "Mostra i pivot A/B/C masc./fimmina rilevati automaticamente",
                            value=False, key="treno_mostra_pornociclo"
                        )
                        if _mostra_pornociclo:
                            st.caption(
                                "Regola: un candidato (massimo o minimo) è confermato quando, dopo almeno 9 "
                                "barre settimanali dal pivot precedente, si sono manifestate 3 barre (anche non "
                                "consecutive, anche inside) con l'estremo opposto via via più spinto — minimi "
                                "decrescenti per confermare un massimo, massimi crescenti per un minimo. "
                                "Calcolato sull'intera storia disponibile (non solo sul periodo filtrato qui "
                                "sopra), per non perdere il conteggio ai bordi del filtro. Un pivot confermato "
                                "non viene mai più spostato — solo l'ultimo, se ancora aperto, può aggiornarsi. "
                                "L'eccezione delle 4 barre non è ancora attiva (vedi nota nel codice)."
                            )

                            _df_settimanale_completo = pc_resample_weekly(
                                _df_prezzi_treno[['time', 'open', 'high', 'low', 'close']]
                            )
                            if len(_df_settimanale_completo) < 10:
                                st.warning("Servono almeno una decina di barre settimanali per innescare il rilevamento.")
                                _df_pivot_pc = pd.DataFrame()
                            else:
                                _finestra_seed = _df_settimanale_completo.iloc[:10]
                                _idx_max_seed = _finestra_seed['high'].idxmax()
                                _idx_min_seed = _finestra_seed['low'].idxmin()
                                _seed_idx, _seed_tipo = (
                                    (_idx_max_seed, 'massimo') if _idx_max_seed < _idx_min_seed
                                    else (_idx_min_seed, 'minimo')
                                )
                                _pivots_pc = rileva_pivot_pornociclo(
                                    _df_settimanale_completo, primo_idx=_seed_idx, primo_tipo=_seed_tipo,
                                    usa_eccezione=False
                                )
                                _etichette_pc = genera_etichette(_pivots_pc)
                                _df_pivot_pc = pd.DataFrame([{
                                    'Data': p['time'].date(), 'Tipo': p['tipo'], 'Etichetta': et,
                                    'Valore': round(p['valore']),
                                    'Conferma': p['time_conferma'].date() if p['time_conferma'] is not None else None,
                                    'Distanza_barre': p['distanza_barre'],
                                } for p, et in zip(_pivots_pc, _etichette_pc)])
                                # Il primo pivot e' solo l'innesco arbitrario, non ha significato metodologico
                                if len(_df_pivot_pc) > 0:
                                    _df_pivot_pc.loc[0, 'Etichetta'] = '(innesco)'

                            # Correzioni manuali persistenti: per i rari casi ambigui (secondo l'utente, ~1
                            # ogni 50 sequenze) si puo' correggere qui senza perdere il resto - stesso schema
                            # gia' usato per il Settlement ufficiale in questa stessa sezione.
                            if not _df_pivot_pc.empty:
                                if os.path.exists(PORNOCICLO_CORREZIONI_PATH):
                                    _df_correzioni_pc = pd.read_csv(PORNOCICLO_CORREZIONI_PATH, parse_dates=['Data'])
                                    _df_correzioni_pc['Data'] = _df_correzioni_pc['Data'].dt.date
                                    _df_pivot_pc = _df_pivot_pc.merge(
                                        _df_correzioni_pc[['Data', 'Etichetta']].rename(columns={'Etichetta': 'Etichetta_corretta'}),
                                        on='Data', how='left'
                                    )
                                    _df_pivot_pc['Etichetta'] = _df_pivot_pc['Etichetta_corretta'].fillna(_df_pivot_pc['Etichetta'])
                                    _df_pivot_pc = _df_pivot_pc.drop(columns='Etichetta_corretta')

                                st.caption(
                                    "Per correggere un'etichetta ambigua, modifica la colonna 'Etichetta' qui "
                                    "sotto e premi 'Salva correzioni' — resta memorizzata anche ricaricando la pagina."
                                )
                                _df_pivot_pc_edit = st.data_editor(
                                    _df_pivot_pc, hide_index=True, width="stretch", key="editor_pornociclo",
                                    disabled=['Data', 'Tipo', 'Valore', 'Conferma', 'Distanza_barre']
                                )
                                if st.button("Salva correzioni", key="salva_correzioni_pornociclo"):
                                    _righe_modificate = _df_pivot_pc_edit[
                                        _df_pivot_pc_edit['Etichetta'] != _df_pivot_pc['Etichetta']
                                    ][['Data', 'Etichetta']]
                                    if not _righe_modificate.empty:
                                        os.makedirs(os.path.dirname(PORNOCICLO_CORREZIONI_PATH), exist_ok=True)
                                        _esistenti_pc = (
                                            pd.read_csv(PORNOCICLO_CORREZIONI_PATH, parse_dates=['Data'])
                                            if os.path.exists(PORNOCICLO_CORREZIONI_PATH) else pd.DataFrame(columns=['Data', 'Etichetta'])
                                        )
                                        if not _esistenti_pc.empty:
                                            _esistenti_pc['Data'] = pd.to_datetime(_esistenti_pc['Data']).dt.date
                                        _combinato_pc = pd.concat([_esistenti_pc, _righe_modificate], ignore_index=True)
                                        _combinato_pc = _combinato_pc.drop_duplicates(subset='Data', keep='last')
                                        _combinato_pc.to_csv(PORNOCICLO_CORREZIONI_PATH, index=False)
                                        st.success(f"{len(_righe_modificate)} correzione/i salvata/e.")
                                        st.rerun()
                                    else:
                                        st.info("Nessuna modifica da salvare.")
                                _df_pivot_pc = _df_pivot_pc_edit

                                # Filtro solo per la visualizzazione sul grafico (il rilevamento resta sull'intera storia)
                                _df_pivot_pc_vis = _df_pivot_pc[
                                    (_df_pivot_pc['Data'] >= _data_min_treno) & (_df_pivot_pc['Data'] <= _data_max_treno)
                                ]
                        else:
                            _df_pivot_pc_vis = pd.DataFrame()
                    elif _tf_treno == "Monthly":
                        _df_bars_treno = (
                            _df_prezzi_treno_filtrato.set_index('time')
                            .resample('ME')
                            .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
                            .dropna()
                            .reset_index()
                        )
                    else:
                        _df_bars_treno = _df_prezzi_treno_filtrato.copy()

                    _open_by_date_treno = dict(zip(_df_prezzi_treno_filtrato['time'].dt.date, _df_prezzi_treno_filtrato['open']))

                    def _calcola_settlement_treno(mesi):
                        righe = []
                        for anno in range(_data_min_treno.year, _data_max_treno.year + 1):
                            for mese in mesi:
                                _tf_data = third_friday(anno, mese).date()
                                if _tf_data < _data_min_treno or _tf_data > _data_max_treno:
                                    continue
                                _valore, _data_usata = None, _tf_data
                                for _delta in range(5):
                                    _d = _tf_data + dt.timedelta(days=_delta)
                                    if _d in _open_by_date_treno:
                                        _valore, _data_usata = _open_by_date_treno[_d], _d
                                        break
                                if _valore is not None:
                                    righe.append({
                                        'settlement_teorico': _tf_data, 'data_usata': _data_usata, 'valore': _valore
                                    })
                        return pd.DataFrame(righe).sort_values('data_usata').reset_index(drop=True)

                    _settlement_mensili_treno = _calcola_settlement_treno(range(1, 13))
                    _settlement_trimestrali_treno = _calcola_settlement_treno([3, 6, 9, 12])

                    # Carico eventuali settlement ufficiali inseriti a mano in precedenza e li unisco alle
                    # tabelle, aggiungendo anche la differenza in punti rispetto al settlement precedente.
                    _UFFICIALE_COLS = ['tipo', 'settlement_teorico', 'settlement_ufficiale']
                    if os.path.exists(TRENO_UFFICIALE_PATH):
                        _df_ufficiali_treno = pd.read_csv(TRENO_UFFICIALE_PATH, parse_dates=['settlement_teorico'])
                        _df_ufficiali_treno['settlement_teorico'] = _df_ufficiali_treno['settlement_teorico'].dt.date
                    else:
                        _df_ufficiali_treno = pd.DataFrame(columns=_UFFICIALE_COLS)

                    def _arricchisci_settlement_treno(df_sett, tipo_label):
                        df_sett = df_sett.sort_values('settlement_teorico').reset_index(drop=True)
                        _override = _df_ufficiali_treno.loc[
                            _df_ufficiali_treno['tipo'] == tipo_label, ['settlement_teorico', 'settlement_ufficiale']
                        ]
                        df_sett = df_sett.merge(_override, on='settlement_teorico', how='left')
                        if 'settlement_ufficiale' not in df_sett.columns:
                            df_sett['settlement_ufficiale'] = np.nan
                        df_sett['diff_valore'] = df_sett['valore'].diff()
                        df_sett['diff_ufficiale'] = df_sett['settlement_ufficiale'].diff()
                        return df_sett

                    _settlement_mensili_treno = _arricchisci_settlement_treno(_settlement_mensili_treno, 'mensile')
                    _settlement_trimestrali_treno = _arricchisci_settlement_treno(_settlement_trimestrali_treno, 'trimestrale')

                    # Scostamento dei settlement mensili dal "Vero Trend": interpolazione lineare tra i due
                    # settlement trimestrali piu' vicini (la stessa linea tratteggiata blu nel grafico).
                    _mens_scostamento_treno = _settlement_mensili_treno.copy()
                    if len(_settlement_trimestrali_treno) >= 2:
                        _trim_sorted_treno = _settlement_trimestrali_treno.sort_values('settlement_teorico')
                        _x_trim_treno = pd.to_datetime(_trim_sorted_treno['settlement_teorico']).map(pd.Timestamp.toordinal).to_numpy()
                        _y_trim_treno = _trim_sorted_treno['valore'].to_numpy()
                        _x_mens_treno = pd.to_datetime(_mens_scostamento_treno['settlement_teorico']).map(pd.Timestamp.toordinal).to_numpy()
                        _entro_range_treno = (_x_mens_treno >= _x_trim_treno.min()) & (_x_mens_treno <= _x_trim_treno.max())
                        _trend_interp_treno = np.interp(_x_mens_treno, _x_trim_treno, _y_trim_treno)
                        _mens_scostamento_treno['vero_trend_interpolato'] = np.where(_entro_range_treno, _trend_interp_treno, np.nan)
                        _mens_scostamento_treno['scostamento_punti'] = (
                            _mens_scostamento_treno['valore'] - _mens_scostamento_treno['vero_trend_interpolato']
                        )
                        _mens_scostamento_treno['scostamento_pct'] = (
                            _mens_scostamento_treno['scostamento_punti'] / _mens_scostamento_treno['vero_trend_interpolato'] * 100
                        )
                    else:
                        _mens_scostamento_treno['vero_trend_interpolato'] = np.nan
                        _mens_scostamento_treno['scostamento_punti'] = np.nan
                        _mens_scostamento_treno['scostamento_pct'] = np.nan

                    _fig_treno = go.Figure()
                    if _tipo_grafico_treno == "Candele":
                        _fig_treno.add_trace(go.Candlestick(
                            x=_df_bars_treno['time'], open=_df_bars_treno['open'], high=_df_bars_treno['high'],
                            low=_df_bars_treno['low'], close=_df_bars_treno['close'], name='FTSEMIB',
                            increasing_line_color='#34d399', decreasing_line_color='#f87171'
                        ))
                    else:
                        _fig_treno.add_trace(go.Ohlc(
                            x=_df_bars_treno['time'], open=_df_bars_treno['open'], high=_df_bars_treno['high'],
                            low=_df_bars_treno['low'], close=_df_bars_treno['close'], name='FTSEMIB',
                            increasing_line_color='#34d399', decreasing_line_color='#f87171'
                        ))
                    if _mostra_mensili and not _settlement_mensili_treno.empty:
                        _fig_treno.add_trace(go.Scatter(
                            x=_settlement_mensili_treno['data_usata'], y=_settlement_mensili_treno['valore'],
                            mode='lines+markers' if _linea_mensili else 'markers', name='Settlement Mensile',
                            line=dict(color='#fbbf24', width=1, dash='dot') if _linea_mensili else None,
                            marker=dict(color='#fbbf24', size=8, symbol='circle'),
                            hovertemplate='%{x}<br>Settlement mensile (Open): %{y:,.2f}<extra></extra>'
                        ))
                    if _mostra_trimestrali and not _settlement_trimestrali_treno.empty:
                        _fig_treno.add_trace(go.Scatter(
                            x=_settlement_trimestrali_treno['data_usata'], y=_settlement_trimestrali_treno['valore'],
                            mode='lines+markers', name='Vero Trend (Trimestrale)',
                            line=dict(color='#60a5fa', width=2, dash='dot'),
                            marker=dict(color='#60a5fa', size=11, symbol='diamond'),
                            hovertemplate='%{x}<br>Settlement trimestrale (Open): %{y:,.2f}<extra></extra>'
                        ))
                    if not _pivot_alti_treno.empty:
                        _fig_treno.add_trace(go.Scatter(
                            x=_pivot_alti_treno['time'], y=_pivot_alti_treno['valore'],
                            mode='markers', name='Partenza ciclo inverso (massimo)',
                            marker=dict(color='#c084fc', size=13, symbol='triangle-down'),
                            hovertemplate='%{x}<br>Massimo confermato: %{y:,.2f}<extra></extra>'
                        ))
                    if not _pivot_bassi_treno.empty:
                        _fig_treno.add_trace(go.Scatter(
                            x=_pivot_bassi_treno['time'], y=_pivot_bassi_treno['valore'],
                            mode='markers', name='Partenza ciclo standard (minimo)',
                            marker=dict(color='#38bdf8', size=13, symbol='triangle-up'),
                            hovertemplate='%{x}<br>Minimo confermato: %{y:,.2f}<extra></extra>'
                        ))
                    if not _df_pivot_pc_vis.empty:
                        # Per il plotting servono Timestamp, non oggetti date "nudi": _df_bars_treno['time']
                        # (usato dalle candele) e' datetime64, e con hovermode='x unified' un mix di dtype
                        # sullo stesso asse X puo' disallineare l'hover, facendo "saltare" alcune barre.
                        _df_pivot_pc_vis = _df_pivot_pc_vis.copy()
                        _df_pivot_pc_vis['Data'] = pd.to_datetime(_df_pivot_pc_vis['Data'])
                        _df_pivot_pc_vis['Conferma'] = pd.to_datetime(_df_pivot_pc_vis['Conferma'])
                        for _tipo_pc, _colore_pc in [('massimo', '#c084fc'), ('minimo', '#2dd4bf')]:
                            _sub_pc = _df_pivot_pc_vis[_df_pivot_pc_vis['Tipo'] == _tipo_pc]
                            if _sub_pc.empty:
                                continue
                            _confermati_pc = _sub_pc[_sub_pc['Conferma'].notna()]
                            _aperti_pc = _sub_pc[_sub_pc['Conferma'].isna()]
                            if not _confermati_pc.empty:
                                _fig_treno.add_trace(go.Scatter(
                                    x=_confermati_pc['Data'], y=_confermati_pc['Valore'],
                                    mode='markers+text', name=f'Pornociclo — {_tipo_pc} confermato',
                                    text=_confermati_pc['Etichetta'],
                                    textposition='top center' if _tipo_pc == 'massimo' else 'bottom center',
                                    textfont=dict(color=_colore_pc, size=11),
                                    marker=dict(color=_colore_pc, size=12, symbol='circle',
                                                line=dict(color='white', width=1)),
                                    hovertemplate='%{text}<br>%{x}<br>Valore: %{y:,.0f}<extra></extra>'
                                ))
                            if not _aperti_pc.empty:
                                _fig_treno.add_trace(go.Scatter(
                                    x=_aperti_pc['Data'], y=_aperti_pc['Valore'],
                                    mode='markers+text', name=f'Pornociclo — {_tipo_pc} candidato (aperto)',
                                    text=_aperti_pc['Etichetta'],
                                    textposition='top center' if _tipo_pc == 'massimo' else 'bottom center',
                                    textfont=dict(color=_colore_pc, size=11),
                                    marker=dict(color=_colore_pc, size=12, symbol='circle-open',
                                                line=dict(width=2)),
                                    hovertemplate='%{text} (ancora aperto)<br>%{x}<br>Valore: %{y:,.0f}<extra></extra>'
                                ))
                        _confermati_con_data_pc = _df_pivot_pc_vis[_df_pivot_pc_vis['Conferma'].notna()]
                        if not _confermati_con_data_pc.empty:
                            _lookup_barre_pc = _df_bars_treno.set_index('time')[['high', 'low']]
                            _confermati_con_data_pc = _confermati_con_data_pc.merge(
                                _lookup_barre_pc, left_on='Conferma', right_index=True, how='left'
                            )
                            _confermati_con_data_pc['y_conferma'] = np.where(
                                _confermati_con_data_pc['Tipo'] == 'massimo',
                                _confermati_con_data_pc['high'], _confermati_con_data_pc['low']
                            )
                            _confermati_con_data_pc['y_conferma'] = (
                                _confermati_con_data_pc['y_conferma'].fillna(_confermati_con_data_pc['Valore'])
                            )
                            _fig_treno.add_trace(go.Scatter(
                                x=_confermati_con_data_pc['Conferma'], y=_confermati_con_data_pc['y_conferma'],
                                mode='markers', name='Barra di conferma',
                                marker=dict(color='#facc15', size=9, symbol='diamond'),
                                hovertemplate='Conferma: %{x}<extra></extra>'
                            ))
                    _fig_treno.update_layout(
                        template='plotly_dark', height=650, margin=dict(l=10, r=10, t=30, b=10),
                        xaxis_rangeslider_visible=False,
                        # 'closest' invece di 'x unified': con trace sparse (settlement, pornociclo) insieme
                        # alle candele (una per settimana), 'x unified' a volte "cattura" l'hover sul punto
                        # sparso piu' vicino invece che sulla candela sotto il cursore, facendo sembrare che
                        # alcune barre settimanali siano "saltate" - segnalato dall'utente il 17/09/2026.
                        hovermode='closest',
                        legend=dict(orientation='h', yanchor='bottom', y=1.02)
                    )
                    st.plotly_chart(_fig_treno, width="stretch", key="treno_chart")
                    st.caption(
                        f"{len(_df_bars_treno)} barre {_tf_treno.lower()} mostrate, periodo "
                        f"{_data_min_treno.strftime('%d/%m/%Y')} — {_data_max_treno.strftime('%d/%m/%Y')}."
                    )

                    _COLONNE_SETT = ['settlement_teorico', 'data_usata', 'valore', 'diff_valore', 'settlement_ufficiale', 'diff_ufficiale']
                    _NOMI_SETT = {
                        'settlement_teorico': 'Scadenza teorica', 'data_usata': 'Data usata (Open)',
                        'valore': 'Valore (Open)', 'diff_valore': 'Diff. punti (Open)',
                        'settlement_ufficiale': 'Settlement ufficiale', 'diff_ufficiale': 'Diff. punti (ufficiale)'
                    }
                    _COLONNE_DISABILITATE_SETT = [
                        'Scadenza teorica', 'Data usata (Open)', 'Valore (Open)', 'Diff. punti (Open)', 'Diff. punti (ufficiale)'
                    ]

                    with st.expander("📋 Tabella settlement", expanded=False):
                        st.caption(
                            "La colonna **Settlement ufficiale** è modificabile: inserisci a mano il prezzo di "
                            "regolamento pubblicato da Borsa Italiana quando lo conosci. Premi 'Salva' per non "
                            "perdere le modifiche — restano finché non le cambi di nuovo."
                        )

                        st.markdown("**Mensili**")
                        if _settlement_mensili_treno.empty:
                            st.caption("Nessuno nel periodo disponibile.")
                            _edit_mensili_treno = _settlement_mensili_treno
                        else:
                            _tab_mensili_treno = _settlement_mensili_treno.sort_values(
                                'settlement_teorico', ascending=False
                            )[_COLONNE_SETT].rename(columns=_NOMI_SETT)
                            _edit_mensili_treno = st.data_editor(
                                _tab_mensili_treno, width="stretch", hide_index=True, key="treno_edit_mensili",
                                disabled=_COLONNE_DISABILITATE_SETT,
                                column_config={'Settlement ufficiale': st.column_config.NumberColumn(format="%.2f")}
                            )

                        st.markdown("**Trimestrali (Vero Trend)**")
                        if _settlement_trimestrali_treno.empty:
                            st.caption("Nessuno nel periodo disponibile.")
                            _edit_trimestrali_treno = _settlement_trimestrali_treno
                        else:
                            _tab_trim_treno = _settlement_trimestrali_treno.sort_values(
                                'settlement_teorico', ascending=False
                            )[_COLONNE_SETT].rename(columns=_NOMI_SETT)
                            _edit_trimestrali_treno = st.data_editor(
                                _tab_trim_treno, width="stretch", hide_index=True, key="treno_edit_trimestrali",
                                disabled=_COLONNE_DISABILITATE_SETT,
                                column_config={'Settlement ufficiale': st.column_config.NumberColumn(format="%.2f")}
                            )

                        if st.button("💾 Salva settlement ufficiali", key="treno_salva_ufficiali"):
                            _righe_editate_treno = []
                            if not _settlement_mensili_treno.empty:
                                for _, _r in _edit_mensili_treno.iterrows():
                                    _righe_editate_treno.append({
                                        'tipo': 'mensile', 'settlement_teorico': _r['Scadenza teorica'],
                                        'settlement_ufficiale': _r['Settlement ufficiale']
                                    })
                            if not _settlement_trimestrali_treno.empty:
                                for _, _r in _edit_trimestrali_treno.iterrows():
                                    _righe_editate_treno.append({
                                        'tipo': 'trimestrale', 'settlement_teorico': _r['Scadenza teorica'],
                                        'settlement_ufficiale': _r['Settlement ufficiale']
                                    })
                            _df_editate_treno = pd.DataFrame(_righe_editate_treno, columns=_UFFICIALE_COLS)
                            _chiavi_editate_treno = set(zip(_df_editate_treno['tipo'], _df_editate_treno['settlement_teorico']))
                            if not _df_ufficiali_treno.empty:
                                _df_ufficiali_rimanenti_treno = _df_ufficiali_treno[
                                    ~_df_ufficiali_treno.apply(lambda r: (r['tipo'], r['settlement_teorico']) in _chiavi_editate_treno, axis=1)
                                ]
                            else:
                                _df_ufficiali_rimanenti_treno = _df_ufficiali_treno
                            _df_finale_treno = pd.concat([
                                _df_ufficiali_rimanenti_treno, _df_editate_treno.dropna(subset=['settlement_ufficiale'])
                            ], ignore_index=True).sort_values(['tipo', 'settlement_teorico']).reset_index(drop=True)
                            os.makedirs(os.path.dirname(TRENO_UFFICIALE_PATH), exist_ok=True)
                            _df_finale_treno.to_csv(TRENO_UFFICIALE_PATH, index=False)
                            st.success(f"Salvati {len(_df_finale_treno)} settlement ufficiali in totale.")

                    with st.expander("📊 Scostamento dei settlement mensili dal Vero Trend", expanded=False):
                        st.caption(
                            "Per ogni settlement mensile, il valore del 'Vero Trend' è interpolato linearmente tra "
                            "i due settlement trimestrali più vicini (la stessa linea tratteggiata blu nel "
                            "grafico, se attivata). Uno scostamento ampio indica che quel mese si è allontanato "
                            "parecchio dal trend trimestrale sottostante — è il 'rumore' del ciclo mensile dentro "
                            "l'oscillazione più ampia."
                        )
                        if _mens_scostamento_treno.empty or _mens_scostamento_treno['vero_trend_interpolato'].isna().all():
                            st.info("Servono almeno 2 settlement trimestrali nel periodo per calcolare l'interpolazione.")
                        else:
                            _tab_scostamento_treno = _mens_scostamento_treno.sort_values(
                                'settlement_teorico', ascending=False
                            )[['settlement_teorico', 'valore', 'vero_trend_interpolato', 'scostamento_punti', 'scostamento_pct']].rename(
                                columns={
                                    'settlement_teorico': 'Scadenza', 'valore': 'Settlement mensile (Open)',
                                    'vero_trend_interpolato': 'Vero Trend (interpolato)',
                                    'scostamento_punti': 'Scostamento (punti)', 'scostamento_pct': 'Scostamento (%)'
                                }
                            )
                            st.dataframe(_tab_scostamento_treno.round(2), width="stretch", hide_index=True)

    # ========================= TAB CICLI =========================
    with tab_cicli:
        st.header("🌀 Cicli — Rilevazione e Convalida")

        with st.expander("ℹ️ Come funziona", expanded=False):
            st.markdown(
                """
**Idea di fondo.** Lo stesso principio del tab Treno (un estremo si conferma
quando resta imbattuto per ~1/4 della durata del ciclo), ma pensato per essere
seguito su più timeframe con un ciclo nominale **fisso a 32 barre** in
qualunque vista. Cambiando il timeframe di aggregazione cambia
automaticamente la finestra temporale coperta — 32 barre Daily ≈ mensile, 32
barre "2D" ≈ 64gg, 32 barre "4D" ≈ 128gg (semestrale) — senza dover
ritoccare il parametro (a differenza del Weekly/Monthly di Treno, qui
l'aggregazione è per **conteggio di barre di borsa**, non per calendario).

**SMA 20**: media mobile semplice a 20 periodi sul Close, calcolata sulle
stesse barre in vista — un pivot che tocca/attraversa la SMA20 è
generalmente più affidabile di uno che ne resta lontano.

**Cicli diritti e inversi**: la ricerca alterna massimo e minimo — i minimi
confermati sono le partenze dei cicli **diritti** (standard), i massimi
confermati sono le partenze dei cicli **inversi**.

**⚠️ Le tabelle qui sotto mostrano il rilievo matematico/statistico**, un
punto di partenza, non un verdetto: lingue (elongazioni) e troncamenti fanno
parte della realtà dei cicli e richiedono il tuo giudizio. Ogni riga è
**convalidabile a mano** (Confermato / Scartato / Dubbio + nota libera), e la
valutazione resta salvata anche cambiando filtro periodo.
                """
            )

        _percorso_prezzi_cicli = st.text_input(
            "Percorso storico prezzi (OHLC)", value=percorso_prezzi, key="percorso_prezzi_cicli"
        )
        if not os.path.exists(_percorso_prezzi_cicli):
            st.warning(f"File non trovato: `{_percorso_prezzi_cicli}`.")
        else:
            _df_prezzi_cicli = pd.read_csv(_percorso_prezzi_cicli, parse_dates=['time'])
            _df_prezzi_cicli = _df_prezzi_cicli.dropna(subset=['open', 'high', 'low', 'close'])
            _df_prezzi_cicli = _df_prezzi_cicli.sort_values('time').drop_duplicates(subset='time').reset_index(drop=True)

            if len(_df_prezzi_cicli) < 2:
                st.warning("Servono almeno due giorni di dati OHLC per mostrare un grafico.")
            else:
                st.caption(
                    "💡 Lo zoom (+) del grafico non riadatta automaticamente l'asse verticale: per "
                    "restringere il periodo mostrato conviene usare il filtro qui sotto invece dello zoom."
                )
                col_fc1, col_fc2 = st.columns([1, 1.4])
                with col_fc1:
                    _modalita_filtro_cicli = st.radio(
                        "Periodo da visualizzare", options=["Tutto", "Ultimi N giorni", "Da una data"],
                        horizontal=True, key="cicli_filtro_modalita"
                    )
                _df_prezzi_cicli_filtrato = _df_prezzi_cicli
                if _modalita_filtro_cicli == "Ultimi N giorni":
                    with col_fc2:
                        _n_giorni_cicli = st.number_input(
                            "Quanti giorni di calendario (dall'ultimo disponibile)",
                            min_value=1, value=180, step=1, key="cicli_n_giorni"
                        )
                    _cutoff_cicli = _df_prezzi_cicli['time'].max() - pd.Timedelta(days=int(_n_giorni_cicli))
                    _df_prezzi_cicli_filtrato = _df_prezzi_cicli[_df_prezzi_cicli['time'] >= _cutoff_cicli]
                elif _modalita_filtro_cicli == "Da una data":
                    with col_fc2:
                        _data_da_cicli = st.date_input(
                            "Mostra a partire da",
                            value=_df_prezzi_cicli['time'].min().date(),
                            min_value=_df_prezzi_cicli['time'].min().date(),
                            max_value=_df_prezzi_cicli['time'].max().date(),
                            key="cicli_data_da"
                        )
                    _df_prezzi_cicli_filtrato = _df_prezzi_cicli[_df_prezzi_cicli['time'].dt.date >= _data_da_cicli]

                if len(_df_prezzi_cicli_filtrato) < 2:
                    st.info("Meno di due giorni nel periodo selezionato: allarga il filtro per vedere un grafico.")
                else:
                    col_tf1, col_tf2 = st.columns(2)
                    with col_tf1:
                        _tf_cicli = st.radio(
                            "Timeframe (barre per conteggio)", ["Daily", "2D", "4D"], horizontal=True, key="cicli_timeframe"
                        )
                    with col_tf2:
                        _tipo_grafico_cicli = st.radio(
                            "Tipo grafico", ["Candele", "Barre"], horizontal=True, key="cicli_tipo_grafico"
                        )

                    col_cy1, col_cy2, col_cy3, col_cy4 = st.columns(4)
                    with col_cy1:
                        _ciclo_barre_cicli = st.number_input(
                            "Lunghezza ciclo (barre del timeframe scelto)",
                            min_value=4, value=32, step=1, key="cicli_ciclo_barre"
                        )
                    with col_cy2:
                        _mostra_ciclo_inverso_cicli = st.checkbox(
                            "Cicli inversi (da massimi)", value=True, key="cicli_mostra_inverso"
                        )
                    with col_cy3:
                        _mostra_ciclo_standard_cicli = st.checkbox(
                            "Cicli diritti (da minimi)", value=True, key="cicli_mostra_standard"
                        )
                    with col_cy4:
                        _mostra_etichette_cicli = st.checkbox(
                            "Etichette data/valore sui pivot", value=True, key="cicli_mostra_etichette",
                            help="Utile su un daily denso dove leggere data/livello a colpo d'occhio è "
                                 "difficile - disattivala se il grafico diventa troppo affollato (es. su 'Tutto')."
                        )
                    _finestra_conferma_cicli = max(1, round(_ciclo_barre_cicli / 4))
                    st.caption(
                        f"Finestra di conferma: **{_finestra_conferma_cicli} barre** senza nuovo estremo "
                        f"(¼ di {_ciclo_barre_cicli:.0f})."
                    )

                    # Le barre nel timeframe scelto e la rilevazione pivot si calcolano sull'INTERA serie
                    # storica (non solo sul periodo filtrato), per evitare artefatti ai bordi del filtro -
                    # stessa logica gia' validata nel tab Treno.
                    _df_completo_cicli = _df_prezzi_cicli.sort_values('time').reset_index(drop=True)
                    if _tf_cicli == "2D":
                        _df_barre_completo_cicli = aggrega_barre_n(_df_completo_cicli, 2)
                    elif _tf_cicli == "4D":
                        _df_barre_completo_cicli = aggrega_barre_n(_df_completo_cicli, 4)
                    else:
                        _df_barre_completo_cicli = _df_completo_cicli.copy()
                    _df_barre_completo_cicli['sma20'] = _df_barre_completo_cicli['close'].rolling(20).mean()

                    _data_min_cicli = _df_prezzi_cicli_filtrato['time'].min().date()
                    _data_max_cicli = _df_prezzi_cicli_filtrato['time'].max().date()

                    with st.expander("➕ Aggiungi uno start di ciclo a mano", expanded=False):
                        st.caption(
                            "Per testare un'ipotesi diversa da quella rilevata in automatico (es. un nuovo "
                            "T+2 diretto partito il 9 o il 15 settembre): il punto compare sul grafico con "
                            "una stella dorata, distinta dai pivot automatici."
                        )
                        col_man1, col_man2, col_man3 = st.columns([1, 1, 2])
                        with col_man1:
                            _data_manuale_cicli = st.date_input(
                                "Data", value=_data_max_cicli, min_value=_data_min_cicli,
                                max_value=_data_max_cicli, key="cicli_data_manuale"
                            )
                        with col_man2:
                            _tipo_manuale_cicli = st.radio(
                                "Tipo", ["diretto (minimo)", "inverso (massimo)"], key="cicli_tipo_manuale"
                            )
                        with col_man3:
                            _nota_manuale_cicli = st.text_input("Nota (opzionale)", key="cicli_nota_manuale")

                        if st.button("Aggiungi punto manuale", key="cicli_aggiungi_manuale"):
                            os.makedirs(os.path.dirname(CICLI_MANUALI_PATH), exist_ok=True)
                            _esistenti_man = (
                                pd.read_csv(CICLI_MANUALI_PATH, parse_dates=['Data'])
                                if os.path.exists(CICLI_MANUALI_PATH)
                                else pd.DataFrame(columns=['Data', 'Tipo', 'Nota'])
                            )
                            _nuova_riga_man = pd.DataFrame([{
                                'Data': pd.Timestamp(_data_manuale_cicli), 'Tipo': _tipo_manuale_cicli,
                                'Nota': _nota_manuale_cicli
                            }])
                            _combinato_man = pd.concat([_esistenti_man, _nuova_riga_man], ignore_index=True)
                            _combinato_man.to_csv(CICLI_MANUALI_PATH, index=False)
                            st.success(
                                f"Punto manuale aggiunto: {_tipo_manuale_cicli} il "
                                f"{_data_manuale_cicli.strftime('%d/%m/%Y')}."
                            )
                            st.rerun()

                        _df_manuali_cicli = (
                            pd.read_csv(CICLI_MANUALI_PATH, parse_dates=['Data'])
                            if os.path.exists(CICLI_MANUALI_PATH) else pd.DataFrame(columns=['Data', 'Tipo', 'Nota'])
                        )
                        if not _df_manuali_cicli.empty:
                            st.caption("Punti manuali salvati — per eliminarne uno usa il cestino nella riga, poi salva:")
                            _df_manuali_edit = st.data_editor(
                                _df_manuali_cicli, num_rows="dynamic", hide_index=True, width="stretch",
                                key="editor_cicli_manuali"
                            )
                            if st.button("Salva modifiche ai punti manuali", key="salva_cicli_manuali"):
                                _df_manuali_edit.to_csv(CICLI_MANUALI_PATH, index=False)
                                st.success("Salvato.")
                                st.rerun()
                            _df_manuali_cicli = _df_manuali_edit

                    _df_barre_vista_cicli = _df_barre_completo_cicli[
                        (_df_barre_completo_cicli['time'].dt.date >= _data_min_cicli) &
                        (_df_barre_completo_cicli['time'].dt.date <= _data_max_cicli)
                    ]

                    _pivot_alti_full_cicli, _pivot_bassi_full_cicli = rileva_pivot_alternati(
                        _df_barre_completo_cicli, _finestra_conferma_cicli
                    )
                    # Barre trascorse dal precedente pivot DELLO STESSO TIPO (diretto con diretto, inverso
                    # con inverso - non nella sequenza alternata mista) - calcolato sull'intera serie prima
                    # del filtro periodo, cosi' il primo punto visibile non perde il conteggio.
                    if not _pivot_alti_full_cicli.empty:
                        _pivot_alti_full_cicli = _pivot_alti_full_cicli.copy()
                        _pivot_alti_full_cicli['barre_da_precedente'] = _pivot_alti_full_cicli['idx'].diff()
                    if not _pivot_bassi_full_cicli.empty:
                        _pivot_bassi_full_cicli = _pivot_bassi_full_cicli.copy()
                        _pivot_bassi_full_cicli['barre_da_precedente'] = _pivot_bassi_full_cicli['idx'].diff()

                    _pivot_alti_cicli = pd.DataFrame(columns=['idx', 'time', 'valore', 'barre_da_precedente'])
                    _pivot_bassi_cicli = pd.DataFrame(columns=['idx', 'time', 'valore', 'barre_da_precedente'])
                    if _mostra_ciclo_inverso_cicli and not _pivot_alti_full_cicli.empty:
                        _pivot_alti_cicli = _pivot_alti_full_cicli[
                            (pd.to_datetime(_pivot_alti_full_cicli['time']).dt.date >= _data_min_cicli) &
                            (pd.to_datetime(_pivot_alti_full_cicli['time']).dt.date <= _data_max_cicli)
                        ]
                    if _mostra_ciclo_standard_cicli and not _pivot_bassi_full_cicli.empty:
                        _pivot_bassi_cicli = _pivot_bassi_full_cicli[
                            (pd.to_datetime(_pivot_bassi_full_cicli['time']).dt.date >= _data_min_cicli) &
                            (pd.to_datetime(_pivot_bassi_full_cicli['time']).dt.date <= _data_max_cicli)
                        ]

                    _fig_cicli = go.Figure()
                    if _tipo_grafico_cicli == "Candele":
                        _fig_cicli.add_trace(go.Candlestick(
                            x=_df_barre_vista_cicli['time'], open=_df_barre_vista_cicli['open'],
                            high=_df_barre_vista_cicli['high'], low=_df_barre_vista_cicli['low'],
                            close=_df_barre_vista_cicli['close'], name='FTSEMIB',
                            increasing_line_color='#34d399', decreasing_line_color='#f87171'
                        ))
                    else:
                        _fig_cicli.add_trace(go.Ohlc(
                            x=_df_barre_vista_cicli['time'], open=_df_barre_vista_cicli['open'],
                            high=_df_barre_vista_cicli['high'], low=_df_barre_vista_cicli['low'],
                            close=_df_barre_vista_cicli['close'], name='FTSEMIB',
                            increasing_line_color='#34d399', decreasing_line_color='#f87171'
                        ))
                    _fig_cicli.add_trace(go.Scatter(
                        x=_df_barre_vista_cicli['time'], y=_df_barre_vista_cicli['sma20'],
                        mode='lines', name='SMA 20', line=dict(color='#facc15', width=1.5),
                        hovertemplate='%{x}<br>SMA20: %{y:,.2f}<extra></extra>'
                    ))
                    if not _pivot_alti_cicli.empty:
                        _barre_txt_alti = _pivot_alti_cicli['barre_da_precedente'].apply(
                            lambda v: f"{int(v)}b<br>" if pd.notna(v) else ""
                        )
                        _fig_cicli.add_trace(go.Scatter(
                            x=_pivot_alti_cicli['time'], y=_pivot_alti_cicli['valore'],
                            mode='markers+text' if _mostra_etichette_cicli else 'markers',
                            name='Ciclo inverso (da massimo)',
                            text=(_barre_txt_alti + pd.to_datetime(_pivot_alti_cicli['time']).dt.strftime('%d/%m')
                                  + '<br>' + _pivot_alti_cicli['valore'].round().astype(int).astype(str)),
                            textposition='top center',
                            textfont=dict(color='#c084fc', size=10),
                            marker=dict(color='#c084fc', size=13, symbol='triangle-down'),
                            hovertemplate='%{x}<br>Massimo confermato: %{y:,.2f}<extra></extra>'
                        ))
                    if not _pivot_bassi_cicli.empty:
                        _barre_txt_bassi = _pivot_bassi_cicli['barre_da_precedente'].apply(
                            lambda v: f"{int(v)}b<br>" if pd.notna(v) else ""
                        )
                        _fig_cicli.add_trace(go.Scatter(
                            x=_pivot_bassi_cicli['time'], y=_pivot_bassi_cicli['valore'],
                            mode='markers+text' if _mostra_etichette_cicli else 'markers',
                            name='Ciclo diritto (da minimo)',
                            text=(_barre_txt_bassi + pd.to_datetime(_pivot_bassi_cicli['time']).dt.strftime('%d/%m')
                                  + '<br>' + _pivot_bassi_cicli['valore'].round().astype(int).astype(str)),
                            textposition='bottom center',
                            textfont=dict(color='#38bdf8', size=10),
                            marker=dict(color='#38bdf8', size=13, symbol='triangle-up'),
                            hovertemplate='%{x}<br>Minimo confermato: %{y:,.2f}<extra></extra>'
                        ))

                    _df_manuali_vis_cicli = pd.DataFrame(columns=['Data', 'Tipo', 'Nota'])
                    if not _df_manuali_cicli.empty:
                        _df_manuali_vis_cicli = _df_manuali_cicli[
                            (_df_manuali_cicli['Data'].dt.date >= _data_min_cicli) &
                            (_df_manuali_cicli['Data'].dt.date <= _data_max_cicli)
                        ].copy()
                    if not _df_manuali_vis_cicli.empty:
                        _lookup_manuali_cicli = _df_barre_completo_cicli.set_index('time')[['high', 'low']]
                        _df_manuali_vis_cicli = _df_manuali_vis_cicli.merge(
                            _lookup_manuali_cicli, left_on='Data', right_index=True, how='left'
                        )
                        _df_manuali_vis_cicli['valore'] = np.where(
                            _df_manuali_vis_cicli['Tipo'].str.startswith('inverso'),
                            _df_manuali_vis_cicli['high'], _df_manuali_vis_cicli['low']
                        )
                        _fig_cicli.add_trace(go.Scatter(
                            x=_df_manuali_vis_cicli['Data'], y=_df_manuali_vis_cicli['valore'],
                            mode='markers+text' if _mostra_etichette_cicli else 'markers',
                            name='Punto manuale',
                            text=(pd.to_datetime(_df_manuali_vis_cicli['Data']).dt.strftime('%d/%m') + '<br>'
                                  + _df_manuali_vis_cicli['valore'].round().astype('Int64').astype(str)),
                            textposition='middle right',
                            textfont=dict(color='#facc15', size=10),
                            marker=dict(color='#facc15', size=15, symbol='star', line=dict(color='white', width=1)),
                            customdata=_df_manuali_vis_cicli['Tipo'],
                            hovertemplate='%{x}<br>Manuale: %{customdata}<extra></extra>'
                        ))
                    _fig_cicli.update_layout(
                        template='plotly_dark', height=650, margin=dict(l=10, r=10, t=30, b=10),
                        xaxis_rangeslider_visible=False,
                        # 'closest' invece di 'x unified': stesso motivo gia' risolto nel tab Treno (marker
                        # sparsi + candele dense possono far "saltare" l'hover su alcune barre).
                        hovermode='closest',
                        legend=dict(orientation='h', yanchor='bottom', y=1.02)
                    )
                    st.plotly_chart(_fig_cicli, width="stretch", key="cicli_chart")
                    st.caption(
                        f"{len(_df_barre_vista_cicli)} barre {_tf_cicli} mostrate, periodo "
                        f"{_data_min_cicli.strftime('%d/%m/%Y')} — {_data_max_cicli.strftime('%d/%m/%Y')}."
                    )

                    # ---- Tabelle di convalida (rilievo matematico + giudizio dell'analista) ----
                    _CONVALIDA_COLS_CICLI = [
                        'tipo', 'timeframe', 'ciclo_barre', 'da', 'a', 'barre', 'classificazione', 'convalida', 'nota'
                    ]
                    if os.path.exists(CICLI_CONVALIDA_PATH):
                        _df_convalida_cicli = pd.read_csv(CICLI_CONVALIDA_PATH, parse_dates=['da', 'a'])
                        _df_convalida_cicli['da'] = _df_convalida_cicli['da'].dt.date
                        _df_convalida_cicli['a'] = _df_convalida_cicli['a'].dt.date
                    else:
                        _df_convalida_cicli = pd.DataFrame(columns=_CONVALIDA_COLS_CICLI)

                    def _tabella_con_convalida_cicli(df_pivot_full, tipo_label):
                        _classificato = classifica_durata_cicli(
                            df_pivot_full, _ciclo_barre_cicli, data_min=_data_min_cicli, data_max=_data_max_cicli
                        )
                        if _classificato.empty:
                            return _classificato
                        if _df_convalida_cicli.empty:
                            _classificato['Convalida'] = ''
                            _classificato['Nota'] = ''
                            return _classificato
                        _override = _df_convalida_cicli[
                            (_df_convalida_cicli['tipo'] == tipo_label) &
                            (_df_convalida_cicli['timeframe'] == _tf_cicli) &
                            (_df_convalida_cicli['ciclo_barre'] == _ciclo_barre_cicli)
                        ][['a', 'convalida', 'nota']].rename(columns={'convalida': 'Convalida', 'nota': 'Nota'})
                        _unito = _classificato.merge(_override, left_on='A', right_on='a', how='left').drop(columns=['a'])
                        _unito['Convalida'] = _unito['Convalida'].fillna('')
                        _unito['Nota'] = _unito['Nota'].fillna('')
                        return _unito

                    _config_convalida_cicli = {
                        'Convalida': st.column_config.SelectboxColumn(
                            "Convalida", options=["", "✅ Confermato", "❌ Scartato", "❓ Dubbio"]
                        ),
                        'Nota': st.column_config.TextColumn("Nota"),
                    }
                    _colonne_disabilitate_cicli = ['Da', 'A', 'Barre', 'Classificazione']

                    _edit_alti_cicli = pd.DataFrame()
                    with st.expander("📏 Cicli inversi rilevati (da massimi) — convalida", expanded=True):
                        if not _mostra_ciclo_inverso_cicli:
                            st.caption("Attiva 'Cicli inversi (da massimi)' sopra per vedere questa tabella.")
                        else:
                            _tab_alti_cicli = _tabella_con_convalida_cicli(_pivot_alti_full_cicli, 'inverso')
                            if _tab_alti_cicli.empty:
                                st.caption("Nessun ciclo completo nel periodo mostrato.")
                            else:
                                _edit_alti_cicli = st.data_editor(
                                    _tab_alti_cicli, width="stretch", hide_index=True, key="cicli_edit_alti",
                                    disabled=_colonne_disabilitate_cicli, column_config=_config_convalida_cicli
                                )

                    _edit_bassi_cicli = pd.DataFrame()
                    with st.expander("📏 Cicli diritti rilevati (da minimi) — convalida", expanded=True):
                        if not _mostra_ciclo_standard_cicli:
                            st.caption("Attiva 'Cicli diritti (da minimi)' sopra per vedere questa tabella.")
                        else:
                            _tab_bassi_cicli = _tabella_con_convalida_cicli(_pivot_bassi_full_cicli, 'standard')
                            if _tab_bassi_cicli.empty:
                                st.caption("Nessun ciclo completo nel periodo mostrato.")
                            else:
                                _edit_bassi_cicli = st.data_editor(
                                    _tab_bassi_cicli, width="stretch", hide_index=True, key="cicli_edit_bassi",
                                    disabled=_colonne_disabilitate_cicli, column_config=_config_convalida_cicli
                                )

                    if st.button("💾 Salva convalida cicli", key="cicli_salva_convalida"):
                        _righe_visibili_cicli = []
                        for _, _r in _edit_alti_cicli.iterrows():
                            _righe_visibili_cicli.append({
                                'tipo': 'inverso', 'timeframe': _tf_cicli, 'ciclo_barre': _ciclo_barre_cicli,
                                'da': _r['Da'], 'a': _r['A'], 'barre': _r['Barre'],
                                'classificazione': _r['Classificazione'], 'convalida': _r['Convalida'], 'nota': _r['Nota']
                            })
                        for _, _r in _edit_bassi_cicli.iterrows():
                            _righe_visibili_cicli.append({
                                'tipo': 'standard', 'timeframe': _tf_cicli, 'ciclo_barre': _ciclo_barre_cicli,
                                'da': _r['Da'], 'a': _r['A'], 'barre': _r['Barre'],
                                'classificazione': _r['Classificazione'], 'convalida': _r['Convalida'], 'nota': _r['Nota']
                            })
                        _df_visibili_cicli = pd.DataFrame(_righe_visibili_cicli, columns=_CONVALIDA_COLS_CICLI)
                        # Le chiavi si calcolano su TUTTE le righe visibili (anche quelle senza convalida/nota):
                        # cosi' se l'utente svuota un campo gia' salvato in precedenza, la cancellazione viene
                        # rispettata invece di lasciare in giro il vecchio valore "orfano".
                        _chiavi_visibili_cicli = set(zip(
                            _df_visibili_cicli['tipo'], _df_visibili_cicli['timeframe'],
                            _df_visibili_cicli['ciclo_barre'], _df_visibili_cicli['a']
                        ))
                        if not _df_convalida_cicli.empty:
                            _rimanenti_cicli = _df_convalida_cicli[
                                ~_df_convalida_cicli.apply(
                                    lambda r: (r['tipo'], r['timeframe'], r['ciclo_barre'], r['a']) in _chiavi_visibili_cicli,
                                    axis=1
                                )
                            ]
                        else:
                            _rimanenti_cicli = _df_convalida_cicli
                        _df_da_salvare_cicli = _df_visibili_cicli[
                            (_df_visibili_cicli['convalida'] != '') | (_df_visibili_cicli['nota'] != '')
                        ]
                        _df_finale_cicli = pd.concat([_rimanenti_cicli, _df_da_salvare_cicli], ignore_index=True)
                        _df_finale_cicli = _df_finale_cicli.sort_values(
                            ['tipo', 'timeframe', 'ciclo_barre', 'a']
                        ).reset_index(drop=True)
                        os.makedirs(os.path.dirname(CICLI_CONVALIDA_PATH), exist_ok=True)
                        _df_finale_cicli.to_csv(CICLI_CONVALIDA_PATH, index=False)
                        st.success(f"Salvate {len(_df_finale_cicli)} righe di convalida cicli in totale.")

    # ========================= TAB TEORIA =========================
    with tab_teoria:
        st.header("📚 Teoria e Documentazione")

        with st.expander("ℹ️ Come funziona / come aggiungere un documento", expanded=False):
            st.markdown(
                f"""
Tre tipi di risorse, gestiti in modo diverso:

- **📝 Markdown** — copia il file `.md` in `{DOC_MD_FOLDER}/`. Compare subito
  nell'elenco al prossimo ricaricamento della pagina.
- **📄 PDF** — copia il file `.pdf` in `{DOC_PDF_FOLDER}/`. Richiede
  `enableStaticServing = true` in `.streamlit/config.toml` (già impostato in
  questo progetto). Si apre in una nuova scheda del browser.
- **🌐 HTML "salvato con pagina completa"** (un file `.html` + sottocartella di
  immagini/CSS/JS) — crea una sottocartella in
  `{DOC_HTML_SRC_FOLDER}/<nome documento>/` con dentro il file `.html` e la sua
  cartella di risorse. Comparirà un bottone **"📦 Impacchetta"**: premilo una
  volta per convertirlo in un unico file autosufficiente (immagini in base64,
  CSS/JS incorporati), salvato in `{DOC_HTML_READY_FOLDER}/` — da lì in poi si
  apre istantaneamente, senza ripetere l'impacchettamento.
                """
            )

        _tipo_doc_teoria = st.radio(
            "Tipo di documento", ["📝 Markdown", "📄 PDF", "🌐 HTML"], horizontal=True, key="teoria_tipo"
        )

        if _tipo_doc_teoria == "📝 Markdown":
            _md_files_teoria = elenca_markdown(DOC_MD_FOLDER)
            if not _md_files_teoria:
                st.info(f"Nessun file .md trovato in `{DOC_MD_FOLDER}/`. Aggiungine uno e ricarica la pagina.")
            else:
                _scelto_md_teoria = st.selectbox("Documento", _md_files_teoria, key="teoria_md_scelto")
                with open(os.path.join(DOC_MD_FOLDER, _scelto_md_teoria), encoding='utf-8') as f:
                    st.markdown(f.read())

        elif _tipo_doc_teoria == "📄 PDF":
            _pdf_files_teoria = elenca_pdf(DOC_PDF_FOLDER)
            if not _pdf_files_teoria:
                st.info(f"Nessun file .pdf trovato in `{DOC_PDF_FOLDER}/`. Aggiungine uno e ricarica la pagina.")
            else:
                _scelto_pdf_teoria = st.selectbox("Documento", _pdf_files_teoria, key="teoria_pdf_scelto")
                st.markdown(
                    f'<a href="app/static/pdf/{_scelto_pdf_teoria}" target="_blank">'
                    f'📄 Apri "{_scelto_pdf_teoria}" in una nuova scheda</a>',
                    unsafe_allow_html=True
                )
                st.caption(
                    "Se il link non si apre correttamente, verifica che `enableStaticServing = true` sia "
                    "impostato in `.streamlit/config.toml` e che l'app sia stata riavviata dopo averlo aggiunto."
                )

        else:  # HTML
            _html_pronti_teoria = elenca_html_pronti(DOC_HTML_READY_FOLDER)
            _html_sorgenti_teoria = elenca_html_sorgenti(DOC_HTML_SRC_FOLDER)
            _non_pronti_teoria = {
                nome: percorso for nome, percorso in _html_sorgenti_teoria.items()
                if f"{nome}.html" not in _html_pronti_teoria
            }

            if _non_pronti_teoria:
                with st.expander(f"⚙️ {len(_non_pronti_teoria)} documento/i da impacchettare", expanded=True):
                    for _nome_teoria, _percorso_teoria in _non_pronti_teoria.items():
                        col_pk1, col_pk2 = st.columns([3, 1])
                        col_pk1.write(f"**{_nome_teoria}**")
                        if col_pk2.button("📦 Impacchetta", key=f"teoria_pack_{_nome_teoria}"):
                            try:
                                _html_finale_teoria = impacchetta_html(_percorso_teoria)
                                os.makedirs(DOC_HTML_READY_FOLDER, exist_ok=True)
                                with open(
                                    os.path.join(DOC_HTML_READY_FOLDER, f"{_nome_teoria}.html"), 'w', encoding='utf-8'
                                ) as f:
                                    f.write(_html_finale_teoria)
                                st.success(f"'{_nome_teoria}' impacchettato con successo.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante l'impacchettamento di '{_nome_teoria}': {e}")

            if not _html_pronti_teoria:
                st.info(
                    f"Nessun documento HTML pronto. Aggiungine uno in "
                    f"`{DOC_HTML_SRC_FOLDER}/<nome>/` e impacchettalo con il bottone sopra."
                )
            else:
                _scelto_html_teoria = st.selectbox("Documento", _html_pronti_teoria, key="teoria_html_scelto")
                st.iframe(
                    os.path.join(DOC_HTML_READY_FOLDER, _scelto_html_teoria),
                    height=900, width="stretch"
                )










# Kriterion Quant - Analizzatore Chain Opzioni

🚀 **Prova subito l'app (gratis, senza registrazione):** https://appkzzsu3pofdhvgezsr5jh.streamlit.app/

📄 **Guida completa passo-passo:** https://kriterionquant.it/blog/spx-options-chain-analyzer.html

🎥 **Video dimostrativo (14 min):** https://www.youtube.com/watch?v=ycQm_y4JZTw

Una dashboard Streamlit ad alte prestazioni per l'analisi quantitativa posizionale di una chain di opzioni, basata su file CSV scaricati dalla CBOE.

Funziona con **qualsiasi sottostante** disponibile sulla CBOE (indici come SPX, ETF come SPY, singole azioni): il ticker viene rilevato automaticamente dall'header del CSV e usato in tutta l'app e nel nome del file JSON esportato.

Questo strumento traduce un singolo file CSV in un'analisi interattiva completa, focalizzandosi su Gamma Exposure (GEX), livelli di Open Interest/Volume, Max Pain e modelli di volatilità, come definito nel progetto Kriterion Quant.

> **Parametri di modello (sidebar):** *risk-free rate* e *dividend yield* sono impostabili dalla sidebar dell'app. I default (4,5% e 1,3%) sono calibrati su un indice azionario USA tipo SPX: **vanno adattati allo strumento analizzato** (dividend yield reale, `0` se non paga dividendi, e tasso risk-free corretto per valuta e scadenza). Incidono **solo** su Vanna/VEX e sui livelli di Gamma/Vanna Flip; GEX, DEX, Open Interest, Max Pain, Expected Move e i Wall non ne risentono. I valori usati vengono salvati nel JSON esportato (`metadata.model_params`).

> ⚠️ **Disclaimer — Non è consulenza finanziaria.** Strumento a solo scopo informativo/educativo. Le metriche su posizionamento dei dealer (GEX/DEX/VEX, Switch Point, Walls) si basano su **ipotesi di modello** e non rappresentano posizioni realmente osservate sul mercato. I dati estratti dal CSV (spot, timestamp, scadenze) possono essere non aggiornati o errati: verificali sempre in autonomia. Nessuna garanzia sui risultati. Vedi il file [LICENSE](LICENSE) per i dettagli.



-----

## 🎯 Caratteristiche Principali

Questo strumento implementa diverse analisi chiave dal documento di progettazione:

  * **Uploader CSV Interattivo**: Permette di caricare il file `.csv` della chain CBOE direttamente nell'app.
  * **Parsing Avanzato**: Esegue automaticamente il parsing del formato CSV CBOE, estraendo metadati chiave come lo Spot Price (da Bid/Ask) e il timestamp.
  * **Dashboard Riepilogativo**: Una vista "summary" con i KPI principali e i tre grafici chiave (GEX, OI, Volume) disposti in colonne per un confronto immediato.
  * **Analisi Gamma Exposure (GEX)**:
      * Calcolo del Net GEX ($) per la scadenza selezionata.
      * Identificazione del Gamma Switch Point (livello GEX=0).
      * Grafico a barre orizzontale per visualizzare l'esposizione gamma per strike.
  * **Analisi Supporti/Resistenze (OI & Volumi)**:
      * Identificazione dei "Put Wall" (supporto) e "Call Wall" (resistenza) basati sul max OI rilevante.
      * Grafici a barre orizzontali bidirezionali per visualizzare il posizionamento (OI) e l'attività (Volume) per strike.
      * **Analisi del Drift (Vol vs OI)**: Un grafico innovativo che mostra la "direzione" dell'attività odierna (Volumi) rispetto al posizionamento statico (OI), sintetizzato da una freccia di "drift" rialzista o ribassista.
  * **Modelli Statistici**:
      * Calcolo del **Max Pain** (Dolore Massimo) per la scadenza.
      * Calcolo dei **Put/Call Ratios** (sia per OI che per Volume) come indicatori di sentiment.
      * Calcolo del **Movimento Atteso (Expected Move)** basato sulla IV At-The-Money (ATM).
  * **Superficie di Volatilità**:
      * Grafico 3D interattivo della superficie di volatilità implicita (IV) (Strike vs DTE vs IV).

-----

## 🛠️ Stack Tecnologico

  * **Python 3.10+**
  * **Streamlit**: Per l'interfaccia utente web e la dashboard.
  * **Pandas**: Per il parsing, la pulizia e la manipolazione dei dati.
  * **NumPy**: Per i calcoli quantitativi (Max Pain, GEX).
  * **Plotly**: Per tutte le visualizzazioni interattive 2D e 3D.
  * **SciPy**: Per l'interpolazione della superficie di volatilità 3D.

-----

## 🚀 Installazione e Avvio

Per eseguire questa applicazione localmente:

1.  **Clona il repository:**

    ```bash
    git clone https://github.com/LukeGSW/AnalisiOpzioniCBOE.git
    cd AnalisiOpzioniCBOE
    ```

2.  **Crea e attiva un ambiente virtuale:**

    ```bash
    # (macOS/Linux)
    python3 -m venv venv
    source venv/bin/activate

    # (Windows)
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Installa le dipendenze:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Esegui l'app Streamlit:**

    ```bash
    streamlit run app.py
    ```

L'applicazione si aprirà automaticamente nel tuo browser.

-----

## 📁 Struttura del Progetto

Il progetto segue una struttura modulare per separare le responsabilità:

```
SPX_Options_Analyzer/
│
├── 📄 app.py                  # File principale Streamlit (UI e orchestrazione)
├── 📄 data_module.py           # Modulo per il parsing CSV e preprocessing
├── 📄 calculations_module.py   # Modulo per tutti i calcoli (GEX, OI, Max Pain)
├── 📄 visualization_module.py  # Modulo per creare i grafici Plotly
├── 📄 requirements.txt         # Dipendenze Python
├── 📄 LICENSE                  # Licenza MIT + disclaimer
└── 📄 README.md                # Questo file
```

-----

## 📜 Licenza

Distribuito con licenza **MIT** (vedi [LICENSE](LICENSE)). Include un disclaimer esplicito: strumento a scopo informativo/educativo, **non è consulenza finanziaria**, nessuna garanzia sui risultati.

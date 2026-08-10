# Changelog — AnalisiOpzioniFTSEMIB

Tutte le modifiche rilevanti al progetto sono documentate qui. Le versioni
seguono più o meno lo schema `MAJOR.MINOR.PATCH`: MAJOR per cambi
architetturali o l'aggiunta di intere sezioni nuove (nuovi tab), MINOR per
funzionalità nuove dentro un tab esistente, PATCH per correzioni.

---

## [2.0.0] — 2026-08-10

Versione "grande": due tab completamente nuovi (Treno, Teoria), una
ristrutturazione architetturale che rende l'app utilizzabile anche senza OI, e
un ampliamento consistente del tab Stats con uno storico persistente.

### 🆕 Nuovo tab: 🚂 Treno

In memoria del trader Treno (trenotrading), che ha reso pubblico
gratuitamente il suo metodo di analisi ciclica ("il pornociclo").

- Grafico del FTSEMIB a candele o barre OHLC, timeframe Daily / Weekly /
  Monthly, con filtro periodo (Tutto / Ultimi N giorni / Da una data) per
  evitare il problema del mancato autorange dell'asse Y con lo zoom nativo
  di Plotly.
- **Settlement mensili e trimestrali**: calcolati come prezzo di Apertura del
  terzo venerdì del mese (con fallback al primo giorno di borsa successivo se
  festivo). I trimestrali (Mar/Giu/Set/Dic) sono il **"Vero Trend"** — il
  concetto centrale del metodo di Treno: il trend "vero" è quello che emerge
  dai settlement trimestrali, mentre l'oscillazione mensile è rumore attorno
  a quel trend.
- Tabelle settlement (mensili e trimestrali) con colonna **Settlement
  ufficiale** editabile a mano (per quando si conosce il prezzo di
  regolamento reale pubblicato da Borsa Italiana, diverso dalla
  semplificazione sull'Apertura) e colonna differenza in punti rispetto al
  settlement precedente della stessa serie. Salvataggio persistente
  (`dati_locali/treno_settlement_ufficiale.csv`) con logica di upsert (non
  perde i valori già inseriti quando si restringe il filtro periodo).
- Tabella **"Scostamento dal Vero Trend"**: per ogni settlement mensile,
  quanto si discosta (in punti e %) dalla linea che interpola i due
  settlement trimestrali più vicini — quantifica il "rumore" del mensile
  dentro l'oscillazione trimestrale.
- **Rilevazione cicli (sperimentale)**: individuazione automatica, sul
  grafico Daily, delle partenze di ciclo standard (da un minimo) e di ciclo
  inverso (da un massimo), con una regola generalizzata ispirata al metodo di
  Treno — un estremo si considera confermato quando resta "imbattuto" per
  almeno ¼ della durata del ciclo in esame (es. 8 barre per un ciclo di 32).
  La ricerca **alterna** massimo e minimo per evitare falsi segnali ripetuti
  durante un trend continuo in una sola direzione.
- **Classificazione della durata dei cicli** (ciclica classica, regola
  Migliorino): un ciclo completo tra due pivot dello stesso tipo si
  considera regolare tra 3/4 e 5/4 della durata nominale; sotto è probabile
  rumore, sopra è una "lingua" (elongazione).
- *Non ancora implementato*: il metodo completo di Treno (regola delle 9
  barre + eccezione delle 4 barre, filtro di ampiezza minima, verifica sulla
  media mobile triangolare a 34 giorni) — presente solo nella sua versione
  semplificata, sperimentale, come base di partenza.

### 🆕 Nuovo tab: 📚 Teoria

Gestione della documentazione teorica direttamente nell'app (utile perché
l'app è raggiungibile da qualunque dispositivo della rete locale).

- **Markdown**: file in `documentazione/md/`, renderizzati direttamente.
- **PDF**: file in `static/pdf/`, aperti in una nuova scheda del browser via
  lo static file serving nativo di Streamlit (richiede
  `enableStaticServing = true` in `.streamlit/config.toml`).
- **HTML "salvato con pagina completa"** (con sottocartella di
  immagini/CSS/JS): sorgenti in `documentazione/html_sorgente/<nome>/`,
  impacchettati con un bottone in un unico file autosufficiente (immagini in
  base64, CSS/JS incorporati) salvato in `documentazione/html_pronto/` —
  necessario perché lo static serving nativo di Streamlit invia `.html`,
  `.js` e `.css` con `Content-Type: text/plain`, quindi non li esegue/applica.
- Nuovo modulo `documentazione_module.py` con la logica di impacchettamento
  (`impacchetta_html`) e scansione delle cartelle.
- Nuova dipendenza: `beautifulsoup4` (aggiunta a `requirements.txt`).

### ⚙️ Ristrutturazione architetturale: app utilizzabile anche senza OI

- Rimosso il vecchio `st.stop()` che bloccava **l'intera app** quando l'OI
  non era ancora disponibile (tipico di un caricamento intraday, prima del
  calcolo di fine giornata di Borsa Italiana).
- I tab che non dipendono dall'OI (Eventi Volume, Andamento Storico, Note,
  Vol Surface, Ripartizione OI) sono ora **sempre accessibili**.
- I tab che richiedono davvero l'OI (Summary, GEX, VEX/DEX, Support/Res,
  Stats) mostrano un avviso locale solo al loro interno, invece di bloccare
  tutto.
- Motivazione: rendere possibile il lavoro sulla sezione volumi (tracciatura
  intraday) anche senza attendere l'OI del giorno successivo.

### 📉 Tab Decadimento — riscritto

- Non dipende più dall'OI (prima richiedeva `df_selected_expiry_oi`, ora usa
  tutti gli strike quotati).
- **Selettore di strike**: qualunque strike quotato nella scadenza, non solo
  l'ATM.
- **Stima IV robusta multi-giorno**: mediana delle IV valide su fino a 5
  giorni (oggi incluso), calcolate Call e Put separatamente, con fallback
  alla sola IV di oggi se i giorni validi sono meno di 3. Funzione batch
  (`estimate_iv_multi_day_batch`) che scansiona i file storici una sola
  volta per tutti gli strike, non uno alla volta.
- Tabella riepilogativa "colpo d'occhio" con la stima per **tutti** gli
  strike della scadenza, non solo quello selezionato.
- Date con giorno della settimana nel dettaglio (utile per capire a colpo
  d'occhio i salti weekend/festivi).
- Tabella prezzi teorici per giorno con colonna Data esatta accanto ai
  giorni residui.

### 📉 Tab Stats — nuovo storico persistente

- Sezione **"📈 Storico Stats"**: ricostruisce Max Pain, P/C Ratio (OI e
  Volume) ed Expected Move giorno per giorno per la scadenza selezionata,
  scansionando `dati/`.
- Persistenza incrementale (`dati_locali/storico_stats.csv`): i giorni già
  calcolati non vengono ricalcolati; due bottoni, uno per l'aggiornamento
  incrementale e uno per il ricalcolo completo forzato.
- Colonne **volumi totali Call/Put** per ogni giorno storico, visibili anche
  nel tooltip del grafico (utile per capire a colpo d'occhio cosa ha causato
  un picco nel P/C Ratio Volume).
- Grafico a 3 pannelli (Spot vs Max Pain, P/C Ratio, Spot vs Bande Expected
  Move) con lo stesso filtro periodo di Andamento Storico.

### 📈 Tab Andamento Storico

- Aggiunto filtro periodo (Tutto / Ultimi N giorni / Da una data), per
  evitare il problema del mancato autorange dell'asse Y con lo zoom nativo
  di Plotly.

### 🐛 Fix

- `st.components.v1.html` (deprecato, rimosso da Streamlit dopo il
  2026-06-01) sostituito con `st.iframe` nel tab Teoria.

---

## [1.1.0] e precedenti

Versione base pre-esistente: tab Summary, GEX, VEX/DEX, Support/Res, Stats,
Vol Surface, Eventi Volume, Andamento Storico, Note, Decadimento (versione
solo ATM), Ripartizione OI. Derivazione di Delta/Gamma/IV/Vanna via
inversione Black-Scholes dal prezzo Settle (Euronext non li fornisce
direttamente). Vedi commit precedenti per il dettaglio.

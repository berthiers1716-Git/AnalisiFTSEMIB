# AnalisiOpzioniFTSEMIB — Cos'è e come funziona

## In breve

Un'app Streamlit per leggere il posizionamento del mercato sulle opzioni
FTSEMIB (MIBO, Borsa Italiana/Euronext Milan) — dove sono concentrati Open
Interest e volumi, quali livelli agiscono da supporto/resistenza, come si
muovono Max Pain e P/C Ratio nel tempo, e — a partire dalla v2.0 — come si
comporta l'indice rispetto ai cicli temporali dei settlement mensili e
trimestrali.

È un adattamento di [AnalisiOpzioniCBOE](https://github.com/LukeGSW/AnalisiOpzioniCBOE)
di Kriterion Quant (pensato per SPX/CBOE), portato sul mercato italiano.

## Perché esiste

Su CBOE, Delta/Gamma/IV/Vanna sono forniti direttamente dal mercato. **Su
Euronext no.** Questa è la differenza metodologica di fondo che attraversa
tutta l'app: ogni Greca è **stimata**, invertendo Black-Scholes dal prezzo
**Settle** di ciascuna opzione (con fallback sul prezzo **Last** quando il
Settle non è ancora disponibile, tipico durante la sessione). Sono quindi
ipotesi di modello sopra un modello — non dati di mercato osservati come lo
sarebbero su CBOE. L'app lo ricorda esplicitamente in più punti, ed è il
motivo per cui in molti punti (Decadimento, storico Stats, rilevazione
cicli) si preferisce la robustezza (mediane su più giorni, fallback
espliciti) alla precisione apparente di un singolo numero.

Il moltiplicatore contratto MIBO è **€2,5/punto**, non 100 come SPX — altro
dettaglio che cambia i conti delle esposizioni nozionali (GEX/DEX/VEX)
rispetto all'app CBOE originale.

## Il flusso dati, in tre passi

1. **Caricamento del file opzioni**: un export testuale copiato da Euronext
   (o un file salvato in `dati/YYYYMMDD.csv`), parsato in blocchi per
   scadenza. Da questo si ricava anche la data di riferimento dell'analisi.
2. **Storico prezzi FTSEMIB**: un CSV OHLC giornaliero (`time,open,high,low,close`),
   usato per trovare lo spot del giorno e per tutto ciò che serve dati
   storici — Decadimento (stima IV multi-giorno), Stats (ricostruzione
   storico), Treno (grafico e settlement).
3. **Parametri di mercato** (sidebar): risk-free rate, dividend yield,
   moltiplicatore contratto, soglia volume significativo — usati ovunque
   serva calcolare o inferire una Greca.

## Tour dei tab

**Sempre accessibili** (non richiedono OI — importante per lavorare intraday,
prima che l'OI del giorno arrivi il giorno successivo):

- **📋 Eventi Volume** — log dei movimenti di volume significativi,
  riconciliabile con l'OI del giorno dopo.
- **📈 Andamento Storico** — Spot / OI totale / Volume totale nel tempo, con
  filtro periodo.
- **📝 Note** — diario libero di osservazioni.
- **📈 Vol Surface** — superficie di volatilità 3D su tutte le scadenze.
- **⚖️ Ripartizione OI** — distribuzione cumulata Put/Call con punto di
  equilibrio.

**Richiedono l'OI della scadenza selezionata** (mostrano un avviso locale se
manca, senza bloccare il resto dell'app):

- **📋 Summary** — panoramica generale della scadenza.
- **📊 Gamma (GEX)** — esposizione gamma netta, Gamma Flip.
- **🧩 Vanna & Delta (VEX/DEX)** — esposizioni Vanna e Delta.
- **🎯 Support/Res (OI & Vol)** — muri di OI, Put Wall/Call Wall.
- **📉 Stats** — Max Pain, P/C Ratio, Expected Move, **più lo storico
  persistente** di questi indicatori giorno per giorno (v2.0).

**Sul singolo strike o sulla serie temporale:**

- **⏳ Decadimento** — curva Theta per uno strike a scelta (non solo ATM),
  con stima IV robusta su più giorni.
- **🚂 Treno** (v2.0) — settlement mensili/trimestrali (il "Vero Trend"),
  grafico Daily/Weekly/Monthly, rilevazione sperimentale dei cicli.
- **📚 Teoria** (v2.0) — documentazione teorica (Markdown, PDF, HTML)
  consultabile direttamente nell'app.

## La filosofia di fondo (cose che vale la pena ricordare)

- **Scetticismo verso Max Pain** come strumento decisionale, a favore
  dell'analisi di distribuzione dell'OI — Max Pain è presente per
  completezza, non come segnale principale.
- **L'OI è disponibile solo il giorno successivo.** L'app è progettata per
  restare utile anche senza (da qui la ristrutturazione della v2.0): il
  volume grezzo intraday è comunque un'informazione, non va sprecata.
- **Preferire la robustezza alla precisione apparente**: dove possibile
  (stima IV nel Decadimento, ricostruzione storico Stats) si usano mediane
  su più giorni invece di un singolo dato che potrebbe essere anomalo
  (Settle fuori dai limiti di no-arbitraggio quel giorno specifico).
- **Approssimazioni dichiarate esplicitamente**, mai nascoste: es. il
  settlement mensile/trimestrale nel tab Treno usa il prezzo di Apertura
  come semplificazione (non il prezzo ufficiale di regolamento, non
  disponibile nel dataset) — lo dice chiaramente nell'interfaccia, con la
  possibilità di correggerlo a mano dove serve.
- **Testing prima di consegnare**: ogni modifica a `app_euronext.py` viene
  verificata con `streamlit.testing.v1.AppTest` end-to-end (non solo un
  avvio "a vuoto" senza dati, che darebbe falsa sicurezza), sia nel caso
  normale che in casi limite (OI assente, filtri estremi, dati storici
  insufficienti).

## Struttura dei file

- `app_euronext.py` — l'app Streamlit, file principale.
- `euronext_module.py` — parsing Euronext, Black-Scholes, storico Stats,
  stima IV multi-giorno, log eventi/note.
- `calculations_module.py` / `visualization_module.py` — moduli originali
  CBOE, riusati quasi invariati.
- `documentazione_module.py` (v2.0) — impacchettamento HTML autosufficienti
  e scansione delle cartelle di documentazione.
- `monitora_euronext.py` / `recupera_storico.py` / `ripara_file_dati.py` —
  strumenti di supporto per il monitoraggio e il recupero dati storici.
- Cartelle **non tracciate in git**: `dati/` (file opzioni giornalieri),
  `dati_locali/` (log persistenti: eventi volume, storico totali, storico
  Stats, settlement ufficiali Treno, note).
- Cartelle **tracciate in git** (v2.0): `documentazione/` (Markdown, HTML
  sorgente/pronto), `static/pdf/`, `.streamlit/config.toml` (necessario per
  lo static file serving dei PDF — richiede il riavvio completo dell'app se
  modificato).

## Cosa manca ancora (idee per il prossimo passo)

- **Metodo Treno completo**: la regola delle 9 barre + eccezione delle 4
  barre, il filtro di ampiezza minima, la verifica sulla media mobile
  triangolare a 34 giorni — oggi c'è solo una versione semplificata e
  sperimentale (solo tempo, nessun filtro di prezzo).
- **Tab Cicli** dedicato, con ogni tipo di ciclo associato al proprio
  timeframe naturale e alla propria media mobile di conferma (es. mensile su
  Daily con MM20), e l'accoppiamento esplicito tra ciclo diritto e inverso.
- **Legacy tkinter app**: esiste ancora un'app separata (`launcher_v49.py` e
  moduli collegati) per FTSE MIB, mantenuta indipendente da questa —
  nessuna integrazione prevista tra le due.

# Changelog — App FTSEMIB Euronext

Formato: `## versione - data`, elenco puntato di cosa è cambiato. Aggiornare ad ogni
modifica che vale la pena ricordare (non serve per ogni minuzia).

Numerazione: `MAJOR.MINOR.PATCH` — MAJOR per cambi strutturali importanti, MINOR per
nuove funzionalità, PATCH per correzioni di bug o piccoli aggiustamenti.

---

## 1.1.0 - 2026-08-01

- Nuova tab **⏳ Decadimento**: curva del prezzo teorico Call/Put ATM avvicinandosi
  alla scadenza (spot e IV tenuti fissi ai valori odierni), con vista tabellare
  a giorni interi
- Nuova tab **⚖️ Ripartizione OI**: barre Put/Call per strike + due linee cumulate
  percentuali (Put dal basso, Call dall'alto) con punto di Equilibrio dove si
  incrociano, disponibile per ogni scadenza selezionata, con vista tabellare
- Nuovo expander **"📄 Dati opzione in forma tabellare"** nella tab Summary: tutti
  gli strike della scadenza selezionata (Strike/Tipo/Settle/Volume/OI/Delta/Gamma/
  IV/Moneyness), con distinzione chiara tra dati grezzi Euronext e valori stimati
  dall'app (Delta/Gamma/IV/Moneyness)
- Numero di versione mostrato nel titolo dell'app (letto da `VERSION.txt`)
- Corretto bug: colonna "nota" nella tab Eventi Volume causava un errore di tipo
  dati quando vuota su tutte le righe esistenti, bloccando il rendering di tutte
  le tab successive

## 1.0.0 - 2026-07-30

Prima versione "numerata" — battezza come baseline tutto il lavoro fatto finora
(dal porting su Debian fino ad oggi), che comprende già:

- App Streamlit (`app_euronext.py`) con stima Delta/Gamma/Vanna via Black-Scholes
  (Euronext non li fornisce), moltiplicatore MIBO (€2.5/punto)
- Selezione file opzioni da upload browser **oppure** da cartella `dati/` sul server
  (utile per accesso da altri dispositivi in rete)
- Storico prezzi FTSEMIB per spot automatico (percorso su disco, non serve ricaricare)
- Tab Eventi Volume: log persistente con notional stimato, conferma tramite variazione
  OI (confronto col giorno precedente), flag "Significativo", campi "Ora"/"Spot preciso"/
  "Nota" editabili
- Tab Andamento Storico: Volume/OI totali giornalieri + Spot, grafico a 3 pannelli
  allineati con tooltip che mostra la data, ricostruibile da cartella `dati/`
- Tab Note: diario libero con modifica/eliminazione
- `euronext_live_module.py` + `monitora_euronext.py`: fetch live diretto da Euronext
  (bypassa il browser), con fallback su prezzo Last quando il Settle è "N/A" intraday
- `recupera_storico.py`: backfill automatico di date passate, spot letto dallo storico
  prezzi, nessun bisogno di copiare a mano
- `ripara_file_dati.py`: rigenera un file `dati/YYYYMMDD.csv` incompleto (es. senza OI)
  da un fetch fresco a Euronext

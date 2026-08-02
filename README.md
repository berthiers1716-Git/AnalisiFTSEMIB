# Analisi Opzioni FTSEMIB (Euronext)

Dashboard Streamlit per l'analisi del posizionamento in opzioni sull'indice **FTSEMIB**
(Borsa Italiana / Euronext Milan) — Gamma Exposure (GEX), DEX/VEX, Max Pain, Put/Call
Wall, superficie di volatilità, decadimento temporale e ripartizione dell'Open Interest.

## Origine e attribuzione

Questo progetto nasce come **adattamento** di [AnalisiOpzioniCBOE](https://github.com/LukeGSW/AnalisiOpzioniCBOE)
di Kriterion Quant — un ottimo strumento pensato per la chain opzioni **CBOE** (SPX, SPY,
azioni USA). Due moduli (`calculations_module.py`, `visualization_module.py`) restano in
larga parte quelli originali; il resto è stato riscritto per adattarsi a un mercato con
caratteristiche molto diverse. Licenza MIT originale mantenuta invariata, vedi [LICENSE](LICENSE).

## Cosa cambia rispetto all'originale CBOE

La differenza più importante: **CBOE fornisce Delta/Gamma/IV già pronti nel CSV, Euronext no**.
Qui vengono stimati invertendo Black-Scholes dal prezzo *Settle* di ciascuna opzione (o dal
prezzo *Last* quando il Settle non è ancora disponibile, tipico durante la sessione) — sono
quindi ipotesi di modello, non dati di mercato osservati.

Altre differenze sostanziali:
- Moltiplicatore contratto MIBO: **€2,5/punto indice** (non 100 come SPX)
- Parser per il formato Euronext (copia-incolla dalla pagina prezzi, o fetch diretto dal
  suo endpoint AJAX interno)
- Recupero automatico di date passate direttamente da Euronext (`recupera_storico.py`,
  `ripara_file_dati.py`), senza dipendere dal download manuale giorno per giorno
- Monitoraggio live durante la sessione (`monitora_euronext.py`)
- Log persistente degli eventi di volume significativo, con conferma tramite variazione
  di Open Interest e note libere
- Storico Volume/OI/Spot con grafico a pannelli allineati
- Curva di decadimento temporale (Theta) e ripartizione cumulata dell'OI

## Avvio rapido

Vedi [SETUP_VENV.md](SETUP_VENV.md) per la predisposizione dell'ambiente Python, poi:

```bash
streamlit run app_euronext.py
```

## Stato del progetto

Vedi [CHANGELOG.md](CHANGELOG.md) per la cronologia delle versioni e [IDEE_FUTURE.md](IDEE_FUTURE.md)
per le idee di sviluppo non ancora realizzate.

## Disclaimer

Solo a scopo informativo/educativo — **non è consulenza finanziaria**. Le metriche di
posizionamento (GEX/DEX/VEX, Max Pain, Wall) si basano su ipotesi di modello, non su
posizioni realmente osservate. I valori di Delta/Gamma/IV sono stime, non dati di mercato.

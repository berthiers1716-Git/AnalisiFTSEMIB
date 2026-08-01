# Predisposizione ambiente Python (venv) — App FTSEMIB Euronext

Guida per creare da zero l'ambiente virtuale Python necessario a far girare `app_euronext.py`
e gli script collegati (`monitora_euronext.py`, `recupera_storico.py`, `ripara_file_dati.py`).

Va ripetuta ogni volta che:
- si installa l'app su una macchina nuova
- si fa un upgrade major di Debian (es. bookworm → trixie), perché cambia la versione di
  Python di sistema e il venv precedente smette di funzionare correttamente

---

## 1. Prerequisiti di sistema

Serve il pacchetto `python3-venv` (il numero di versione dipende dalla Debian in uso, es.
`python3.11-venv` su bookworm, `python3.13-venv` su trixie — verificare con `python3 --version`):

```bash
python3 --version
sudo apt install python3.XX-venv    # sostituire XX con la versione mostrata sopra
```

## 2. Creazione del venv

Nella cartella dell'app (es. `~/py-env/AnalisiOpzioniCBOE`):

```bash
cd ~/py-env/AnalisiOpzioniCBOE
python3 -m venv venv
```

Se compare l'errore `ensurepip is not available`, è segno che il pacchetto del punto 1 non è
installato: installarlo e ripetere questo comando.

## 3. Attivazione

Da ripetere ad ogni nuova sessione di terminale (non è permanente):

```bash
source venv/bin/activate
```

Il prompt del terminale dovrebbe mostrare `(venv)` all'inizio della riga quando è attivo.
Per uscirne: `deactivate`.

## 4. Installazione delle dipendenze

Con il venv attivo:

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install requests
```

Nota: `requests` non è incluso in `requirements.txt` (che viene dal progetto originale CBOE) —
serve solo per `euronext_live_module.py` (fetch dati live da Euronext), va installato a parte.

## 5. Verifica

```bash
python3 -c "import streamlit, pandas, numpy, scipy, plotly, requests; print('Tutto OK')"
```

## 6. Avvio dell'app

```bash
streamlit run app_euronext.py
```

Si apre nel browser, di solito su `http://localhost:8501`.

## 7. Script da riga di comando (stesso venv, nessuna installazione aggiuntiva)

```bash
python3 monitora_euronext.py --spot <valore>
python3 recupera_storico.py --da AAAA-MM-GG --a AAAA-MM-GG --prezzi <file_storico_prezzi.csv>
python3 ripara_file_dati.py --data AAAA-MM-GG --file dati/AAAAMMGG.csv
```

---

## Struttura di cartelle attesa

Non incluse nel pacchetto dei file di codice (sono dati, non codice), ma necessarie per il
funzionamento completo:

```
AnalisiOpzioniCBOE/
├── venv/                  ← creato al punto 2, mai da copiare da un'altra macchina
├── dati/                  ← file opzioni YYYYMMDD.csv (copia-incolla o script di recupero)
├── dati_locali/           ← log persistenti generati dall'app (eventi_volume.csv,
│                             storico_totali.csv, diario_note.csv) — creata automaticamente
│                             al primo utilizzo se non esiste
└── *.py, *.md             ← file di codice e note
```

## Problemi frequenti

- **Errore di import dopo un upgrade di Debian**: quasi sempre serve ricreare il venv da zero
  (punti 2-4), perché la versione di Python di sistema è cambiata. Il vecchio venv non va
  "aggiornato", va ricreato.
- **`pip: command not found` dopo l'attivazione**: verificare di aver davvero attivato il venv
  (`source venv/bin/activate`), non il Python di sistema.
- **Librerie mancanti solo per gli script live** (`requests`): non fanno parte del
  `requirements.txt` originale, vanno installate a parte (punto 4).

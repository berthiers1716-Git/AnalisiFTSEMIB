# File: scarica_backfill_opzioni.py
#
# Backfill storico delle opzioni MIBO da Euronext: per ciascun giorno lavorativo
# nell'intervallo richiesto, scarica tutte le scadenze e scrive un file
# dati/YYYYMMDD.csv nello stesso formato dei file copia-incolla manuali - lo
# stesso formato che rigenera_file_dati.py e il download live dell'app
# scrivono, grazie al riuso di euronext_module.scrivi_file_dati().
#
# A differenza del backfill future (un solo storico_oi_future.csv, perche' e'
# una riga per scadenza): qui, con decine di strike per scadenza e piu'
# scadenze, un file per giorno resta il formato piu' maneggevole - lo stesso
# che l'app gia' usa per l'archivio in dati/.
#
# USO:
#   python3 scarica_backfill_opzioni.py --da 2026-06-19 --a 2026-09-14
#   python3 scarica_backfill_opzioni.py --data 2026-09-14
#   python3 scarica_backfill_opzioni.py --da 2026-06-19 --a 2026-09-14 --forza   # riscrive anche se il file esiste gia'
#
# Salta automaticamente sabato/domenica; un giorno che da' errore (es. festivo
# di borsa) non blocca gli altri - viene segnalato e si passa al successivo.
# Se un file dati/YYYYMMDD.csv esiste gia', il giorno viene saltato di default
# (evita di sovrascrivere/ri-scaricare inutilmente su backfill ripetuti).
#
# Ultima modifica: 2026-09-14
# -----------------------------------------------------------------------------

import argparse
import os
import time
import datetime as dt
import pandas as pd

from euronext_live_module import (
    crea_sessione, fetch_scadenze_disponibili, fetch_live_html_batched, parse_live_html,
)
from euronext_module import scrivi_file_dati

_CARTELLA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DATI_FOLDER = os.path.join(_CARTELLA_SCRIPT, "dati")
PAUSA_DEFAULT_SEC = 5


def scarica_un_giorno(session, scadenze, giorno, forza=False):
    """giorno: datetime.date. Ritorna 'scaricato' / 'saltato' / 'errore'."""
    filepath = os.path.join(DATI_FOLDER, giorno.strftime("%Y%m%d") + ".csv")
    if os.path.exists(filepath) and not forza:
        print(f"  ⏭️  già presente ({filepath}), salto (usa --forza per riscrivere)")
        return 'saltato'

    trade_date_euronext = giorn_a_mmddyyyy(giorno)
    try:
        html_parts = fetch_live_html_batched(session, expiries=scadenze,
                                              trade_date=trade_date_euronext, batch_size=5)
    except Exception as e:
        print(f"  ❌ Richiesta fallita: {e}")
        return 'errore'

    dfs = []
    for i, h in enumerate(html_parts):
        try:
            dfs.append(parse_live_html(h))
        except ValueError:
            # Capita se un blocco di scadenze non aveva ancora attivita' quel
            # giorno storico (es. scadenze lontane non ancora quotate allora):
            # si salta solo quel blocco, non l'intero giorno.
            print(f"  ⚠️  blocco {i+1}/{len(html_parts)} senza dati riconoscibili, salto solo quello")

    if not dfs:
        print("  ❌ Nessun dato riconosciuto in nessun blocco per questo giorno.")
        return 'errore'

    df_raw = pd.concat(dfs, ignore_index=True)
    os.makedirs(DATI_FOLDER, exist_ok=True)
    scrivi_file_dati(df_raw, filepath, trade_date=pd.Timestamp(giorno))
    print(f"  ✅ scritto {filepath} ({len(df_raw)} righe)")
    return 'scaricato'


def giorn_a_mmddyyyy(giorno):
    return giorno.strftime("%m-%d-%Y")


def main():
    parser = argparse.ArgumentParser(description="Backfill storico opzioni MIBO da Euronext.")
    parser.add_argument("--data", help="Un giorno storico singolo, formato YYYY-MM-DD")
    parser.add_argument("--da", help="Inizio intervallo per il backfill, formato YYYY-MM-DD")
    parser.add_argument("--a", help="Fine intervallo per il backfill, formato YYYY-MM-DD (default: oggi)")
    parser.add_argument("--forza", action="store_true", help="Riscrive anche i file già presenti")
    parser.add_argument("--pausa", type=float, default=PAUSA_DEFAULT_SEC,
                         help=f"Secondi di pausa tra un giorno e l'altro nel backfill "
                              f"(default: {PAUSA_DEFAULT_SEC}; alza fino a 60 se il server sembra bloccarti)")
    args = parser.parse_args()

    print("Connessione a Euronext...")
    session = crea_sessione()
    scadenze = fetch_scadenze_disponibili(session)
    print(f"Scadenze rilevate: {scadenze}")
    print(f"Cartella dati: {DATI_FOLDER}")

    if args.da:
        inizio = dt.datetime.strptime(args.da, "%Y-%m-%d").date()
        fine = dt.datetime.strptime(args.a, "%Y-%m-%d").date() if args.a else dt.date.today()
        giorni = []
        d = inizio
        while d <= fine:
            if d.weekday() < 5:
                giorni.append(d)
            d += dt.timedelta(days=1)

        print(f"\nBackfill di {len(giorni)} giorni lavorativi, da {inizio} a {fine}...")
        conteggi = {'scaricato': 0, 'saltato': 0, 'errore': 0}
        for i, giorno in enumerate(giorni, 1):
            print(f"[{i}/{len(giorni)}] {giorno}...")
            esito = scarica_un_giorno(session, scadenze, giorno, forza=args.forza)
            conteggi[esito] += 1
            if i < len(giorni) and esito != 'saltato':
                time.sleep(args.pausa)
        print(f"\n✅ Backfill completato: {conteggi['scaricato']} scaricati, "
              f"{conteggi['saltato']} già presenti, {conteggi['errore']} in errore.")
        return

    giorno = (dt.datetime.strptime(args.data, "%Y-%m-%d").date() if args.data else dt.date.today())
    print(f"\nScarico i dati per {giorno}...")
    scarica_un_giorno(session, scadenze, giorno, forza=args.forza)


if __name__ == "__main__":
    main()

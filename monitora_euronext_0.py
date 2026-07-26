#!/usr/bin/env python3
# File: monitora_euronext.py
#
# Interroga l'endpoint live di Euronext per le opzioni FTSEMIB (MIB-DMIL) e
# registra nel log eventi_volume.csv i movimenti di volume sopra soglia,
# con data/ora prese automaticamente dal timestamp "as of" di ciascuna scadenza.
#
# Pensato per essere lanciato periodicamente (es. una volta all'ora durante
# l'orario di negoziazione) tramite cron. Esempio crontab (ogni ora, 9-17, lun-ven):
#   0 9-17 * * 1-5 cd /percorso/AnalisiOpzioniCBOE && venv/bin/python3 monitora_euronext.py --spot 52280 >> log_monitor.txt 2>&1
#
# NOTA: lo spot va fornito a mano (--spot) o aggiornato in questo file, perche'
# la pagina Euronext non lo include nella risposta AJAX. In assenza di uno spot
# aggiornato, usa l'ultima chiusura nota: sufficiente per la classificazione
# volume/notional, meno preciso per il campo 'moneyness'.
# -----------------------------------------------------------------------------

import argparse
import sys

from euronext_live_module import crea_sessione, fetch_live_html, parse_live_html, \
    log_significant_volume_events_live, SCADENZE_NOTE

VOLUME_LOG_PATH = "dati_locali/eventi_volume.csv"
CONTRACT_MULTIPLIER = 2.5
DEFAULT_THRESHOLD = 100


def main():
    parser = argparse.ArgumentParser(description="Monitora volumi live opzioni FTSEMIB (Euronext).")
    parser.add_argument('--spot', type=float, required=True, help="Spot FTSEMIB attuale (es. ultima chiusura nota)")
    parser.add_argument('--soglia', type=float, default=DEFAULT_THRESHOLD, help=f"Soglia volume significativo (default {DEFAULT_THRESHOLD})")
    parser.add_argument('--scadenze', nargs='*', default=None,
                         help="Scadenze da interrogare, formato MM-01-YYYY (default: tutte quelle note)")
    args = parser.parse_args()

    try:
        session = crea_sessione()
        html = fetch_live_html(session, expiries=args.scadenze or SCADENZE_NOTE)
        df_raw = parse_live_html(html)
    except Exception as e:
        print(f"[ERRORE] Recupero/parsing dati live fallito: {e}", file=sys.stderr)
        sys.exit(1)

    n_new, n_fix, log_df = log_significant_volume_events_live(
        df_raw, args.spot, CONTRACT_MULTIPLIER, args.soglia, VOLUME_LOG_PATH
    )

    print(f"Righe lette: {len(df_raw)}  |  Nuovi eventi: {n_new}  |  OI completati: {n_fix}  |  Totale nel log: {len(log_df)}")
    if n_new > 0:
        nuovi = log_df.sort_values('data_riferimento', ascending=False).head(n_new)
        print(nuovi[['data_riferimento', 'ora', 'scadenza', 'strike', 'tipo', 'volume', 'notional_stimato_eur']].to_string(index=False))


if __name__ == '__main__':
    main()

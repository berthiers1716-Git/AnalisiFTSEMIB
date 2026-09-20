# File: pornociclo_lab.py
#
# Rilevatore oggettivo dei pivot del "Metodo Treno" (pornociclo/69): identifica
# la sequenza alternata di massimi/minimi settimanali confermati secondo la
# regola a 3 barre + distanza minima di 9 barre (vedi Il_pornociclo_-
# _trenotrading__autosufficiente_.docx). Validato il 16/09/2026 contro il
# grafico reale fornito dall'utente: entrambi i punti verificabili (27/03 e
# 10/07/2026, incluse le rispettive date di conferma) combaciano esattamente.
#
# Nota: la regola dell'eccezione delle 4 barre (usa_eccezione=True) esiste nel
# codice ma è DISATTIVATA di default - una prima verifica su un caso reale ha
# mostrato che la mia lettura del trigger sballa una conferma già validata.
# Da ricalibrare quando si presenterà un altro caso reale da confrontare.
#
# Ultima modifica: 2026-09-16
#

import pandas as pd
import numpy as np


def resample_weekly(df_daily):
    """df_daily: colonne time, open, high, low, close. Ritorna barre settimanali W-FRI."""
    df = df_daily.set_index('time').sort_index()
    return (
        df.resample('W-FRI')
        .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
        .dropna()
        .reset_index()
    )


def rileva_pivot_pornociclo(df_w, primo_idx, primo_tipo, min_barre=9, min_barre_eccezione=4,
                             usa_eccezione=False):
    """
    df_w: barre settimanali (colonne time, open, high, low, close), indice 0..N-1.
    primo_idx: indice del primo pivot noto (punto di partenza, es. 'A').
    primo_tipo: 'massimo' o 'minimo'.

    Regola (Treno/Pornociclo):
    - un candidato e' il massimo (o minimo) piu' estremo dal pivot precedente ad oggi,
      aggiornato ad ogni nuovo estremo (azzera la conferma in corso).
    - confermato quando: (a) sono trascorse >= min_barre dal pivot precedente, E
      (b) si sono manifestate 3 barre successive al candidato con l'estremo opposto
      via via piu' spinto (minimi decrescenti per confermare un massimo, massimi
      crescenti per confermare un minimo) - non devono essere consecutive, l'uguaglianza
      non conta come passo.

    usa_eccezione: se True, applica la regola delle 4 barre (invece di 9) quando il prezzo
      ha risuperato il pivot precedente - DISATTIVATA di default: verificata contro i due
      punti reali noti (27/03 e 10/07/2026), la mia prima lettura di questa regola scattava
      troppo facilmente (bastava un minimo superamento) producendo una conferma anticipata
      e sbagliata (17/04 invece del 25/04-01/05 reale). Con la sola regola dei 9 barre,
      ENTRAMBI i punti noti combaciano esattamente. Da ricalibrare quando saranno
      disponibili dati oltre il 31/07/2026, per testarla sul caso reale "eccez. 4w".
    """
    n = len(df_w)
    pivots = [{
        'idx': primo_idx, 'time': df_w.loc[primo_idx, 'time'], 'tipo': primo_tipo,
        'valore': df_w.loc[primo_idx, 'high' if primo_tipo == 'massimo' else 'low'],
        'idx_conferma': None, 'time_conferma': None, 'distanza_barre': None,
        'eccezione_attivata': False,
    }]

    start_idx = primo_idx
    valore_pivot_prec = pivots[0]['valore']
    tipo_cercato = 'minimo' if primo_tipo == 'massimo' else 'massimo'

    while True:
        candidato_idx = start_idx
        candidato_valore = valore_pivot_prec
        riferimento = np.inf if tipo_cercato == 'massimo' else -np.inf
        passi = 0
        eccezione_attivata = False
        confermato_a = None

        for i in range(start_idx + 1, n):
            riga = df_w.loc[i]
            estremo_stesso_verso = riga['high'] if tipo_cercato == 'massimo' else riga['low']

            # Nuovo estremo piu' spinto -> aggiorna il candidato, azzera la conferma in corso
            supera_candidato = (
                estremo_stesso_verso > candidato_valore if tipo_cercato == 'massimo'
                else estremo_stesso_verso < candidato_valore
            )
            if supera_candidato:
                candidato_idx = i
                candidato_valore = estremo_stesso_verso
                riferimento = np.inf if tipo_cercato == 'massimo' else -np.inf
                passi = 0
                continue

            if usa_eccezione and not eccezione_attivata:
                if tipo_cercato == 'minimo' and riga['high'] > valore_pivot_prec:
                    eccezione_attivata = True
                elif tipo_cercato == 'massimo' and riga['low'] < valore_pivot_prec:
                    eccezione_attivata = True

            # Passo della scala di conferma (verso OPPOSTO a quello del candidato)
            estremo_opposto = riga['low'] if tipo_cercato == 'massimo' else riga['high']
            step_valido = (
                estremo_opposto < riferimento if tipo_cercato == 'massimo'
                else estremo_opposto > riferimento
            )
            if step_valido:
                passi += 1
                riferimento = estremo_opposto

            distanza = i - start_idx
            min_richiesto = min_barre_eccezione if eccezione_attivata else min_barre
            if passi >= 3 and distanza >= min_richiesto:
                confermato_a = i
                break

        if confermato_a is None:
            pivots.append({
                'idx': candidato_idx, 'time': df_w.loc[candidato_idx, 'time'], 'tipo': tipo_cercato,
                'valore': candidato_valore, 'idx_conferma': None, 'time_conferma': None,
                'distanza_barre': None, 'eccezione_attivata': eccezione_attivata,
            })
            break

        pivots.append({
            'idx': candidato_idx, 'time': df_w.loc[candidato_idx, 'time'], 'tipo': tipo_cercato,
            'valore': candidato_valore, 'idx_conferma': confermato_a,
            'time_conferma': df_w.loc[confermato_a, 'time'],
            'distanza_barre': confermato_a - start_idx, 'eccezione_attivata': eccezione_attivata,
        })
        start_idx = candidato_idx
        valore_pivot_prec = candidato_valore
        tipo_cercato = 'minimo' if tipo_cercato == 'massimo' else 'massimo'

    return pivots


def genera_etichette(pivots):
    """
    Genera le etichette doppie (masculo/fimmina) per ciascun pivot, stile
    'A fimmina', 'A masc. / B fimmina', 'B masc. / A fimmina2', ecc.

    Convenzione (verificata contro le etichette reali del grafico allegato):
    ogni pivot mostra l'APERTURA della nuova triade (A) piuttosto che la
    chiusura di quella precedente (C) - le due cose coincidono sullo stesso
    pivot, si preferisce la piu' "in avanti". Eccezione: l'ultimissimo pivot
    della sequenza, se ancora non confermato, non apre una nuova triade
    (non sappiamo ancora se/dove finira'): mostra 'C?' invece di una nuova 'A'.

    Ritorna una lista di stringhe (una per pivot).
    """
    n = len(pivots)
    et_masc = [None] * n
    et_fim = [None] * n

    def _suff(k):
        return '' if k == 1 else str(k)

    k_masc = 0
    for i, p in enumerate(pivots):
        if p['tipo'] == 'minimo':
            ultimo = (i == n - 1)
            if k_masc == 0:
                k_masc = 1
                et_masc[i] = f"A masc.{_suff(k_masc)}"
            elif ultimo:
                et_masc[i] = f"C? masc.{_suff(k_masc)}"
            else:
                k_masc += 1
                et_masc[i] = f"A masc.{_suff(k_masc)}"
        elif k_masc > 0:
            et_masc[i] = f"B masc.{_suff(k_masc)}"

    k_fim = 0
    for i, p in enumerate(pivots):
        if p['tipo'] == 'massimo':
            ultimo = (i == n - 1)
            if k_fim == 0:
                k_fim = 1
                et_fim[i] = f"A fimmina{_suff(k_fim)}"
            elif ultimo:
                et_fim[i] = f"C? fimmina{_suff(k_fim)}"
            else:
                k_fim += 1
                et_fim[i] = f"A fimmina{_suff(k_fim)}"
        elif k_fim > 0:
            et_fim[i] = f"B fimmina{_suff(k_fim)}"

    etichette = []
    for i in range(n):
        parti = [x for x in (et_masc[i], et_fim[i]) if x]
        etichette.append(' / '.join(parti) if parti else '?')
    return etichette

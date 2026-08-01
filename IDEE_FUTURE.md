# Idee future — AnalisiOpzioniCBOE / App Euronext FTSEMIB

Note e idee raccolte durante lo sviluppo, da riprendere quando c'è tempo. Non impegnative, solo promemoria.

---

## 2026-07-27 — Tracciare la IV intraday, non solo a scatti

**Osservazione che ha innescato l'idea:** in una giornata (ore 10:55 → 16:00), lo spot FTSEMIB è sceso di ~100 punti, ma le call di agosto sono salite di diversi punti — segno che qualcosa (probabilmente la volatilità implicita, o un flusso di acquisto specifico su quello strike) ha sovrastato l'effetto delta atteso dal solo movimento di prezzo.

**Il problema attuale:** l'app calcola la IV solo nel momento in cui carichi un file — è una fotografia isolata, non una serie. Per notare un salto di IV durante la giornata bisogna confrontare "a mano" due fotografie separate (mattina vs pomeriggio), come è successo oggi.

**L'idea:** usare lo stesso principio già costruito per il log Volume/OI (`monitora_euronext.py`, polling orario) per **calcolare e salvare anche la IV** ad ogni interrogazione — almeno su un paniere di strike ATM per le scadenze principali, se non su tutta la catena. Questo darebbe:
- una curva IV intraday, non solo il valore di fine giornata
- la possibilità di incrociare i salti di IV con il log eventi volume (`eventi_volume.csv`), per capire se un salto di prezzo su uno strike coincide con un evento di volume tracciato o è un movimento più generale di mercato

**Non ancora deciso:**
- Ogni quanto calcolare la IV durante il giorno (stessa cadenza oraria del monitoraggio volumi, o più/meno frequente?)
- Salvare la IV per singolo strike o solo un valore ATM riassuntivo per scadenza (più leggero, meno preciso)
- Dove visualizzarla: nuovo pannello nella tab "Andamento Storico", o una tab dedicata

---

## Note sparse su interpretazione degli eventi (esempi, non regole fisse)

- **2026-07-24**: osservati due movimenti da 500 put strike 50500 (scadenze settembre e dicembre) durante una discesa dell'indice. Ipotesi da tenere d'occhio in casi simili: la vendita di put sotto lo spot durante un ribasso può in alcuni casi segnalare l'opposto di quanto sembra a prima vista (posizionamento che scommette contro la continuazione del ribasso, non a favore). Da verificare con l'evoluzione successiva del prezzo, non è una regola generale.

- **2026-07-27 (lunedì)**: gap up di apertura di ~300pt rispetto al close di venerdì. Ci si aspetterebbe che le call si riprezzassero subito coerentemente (più delta, spot più alto). Invece in mattinata le call quotavano più o meno come al riferimento di venerdì, quasi ignorando il gap — fenomeno osservato su **tutti gli strike**, non isolato. Alle 16:00, con l'indice sceso di ~100pt dal massimo di mattina, i valori sono apparsi molto più coerenti/realistici. Ipotesi: il Settle ufficiale di venerdì (usato come riferimento per calcolare le variazioni di lunedì) potrebbe essere stato impreciso, e ci è voluta buona parte della sessione perché gli scambi reali "correggessero" le quotazioni. Coerente con l'osservazione precedente sui margini T3 a volte sballati che si sistemano il giorno dopo.

  **Idea collegata — controllo di sanità sui prezzi**: l'app calcola già IV/Delta/Gamma teorici via Black-Scholes per ogni strike. Si potrebbe confrontare sistematicamente il prezzo quotato (Settle o Last) con quello teorico atteso dato lo spot del momento, e segnalare gli strike che si discostano troppo — un "controllo di sanità" sui prezzi, complementare al log eventi volume che già guarda ai volumi/OI. Utile per individuare automaticamente casi come quello di oggi, invece di notarli solo "a occhio" confrontando due fotografie della giornata.

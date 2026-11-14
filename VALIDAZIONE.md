# Validazione del progetto

Data: 14 novembre 2026. Verifiche locali su Windows, Python 3.12, ambiente virtuale dedicato.

Esito locale: **32 test superati**, **93% di copertura** dei moduli app/core/publisher, lint e compilazione Python superati. Dopo l'aggiornamento a Pillow 13, l'audit delle dipendenze runtime non ha rilevato vulnerabilità note al momento della verifica. L'esito non garantisce assenza di vulnerabilità future.

## Perimetro

Il progetto prepara annunci a partire da gruppi di foto e calcola prezzi secondo un listino fisso. La pubblicazione sul sito reale è un'integrazione ancora da configurare. I test automatici non costituiscono una prova di compatibilità con l'interfaccia corrente di Vinted.

## Controlli automatici

32 test coprono:

- Tutte le 34 categorie del listino, T-shirt a 5 euro e felpe a 15 euro; nessun moltiplicatore implicito in modalità fissa.
- Formula alternativa con prezzo originale, stato, marca, margine, arrotondamento e limiti.
- Configurazioni invalide, valori negativi, zero, booleani, valori non numerici e precisione monetaria.
- Raggruppamento per sottocartella, foto nella radice, rinomina e riordino delle foto, identificazione dei contenuti e deduplicazione.
- API HTTP: scansione asincrona senza sovrapposizioni, aggiornamento dati, ricalcolo prezzo, lettura foto e salvataggio persistente.
- Esportazione completa con nomi foto relativi, senza percorsi personali nel pacchetto esportato.
- Gestione di errori di scansione, dati incompleti e risposte AI incomplete o malformate.
- Protocollo della richiesta AI, ridimensionamento immagini e pulizia dei valori restituiti, con servizio remoto simulato.
- Protezioni locali: token sulle scritture, verifica Host, JSON malformato, limite richiesta e blocco delle modifiche dopo l'invio.
- Publisher con browser simulato: anteprima senza invio, salvataggio prima dell'invio, successo, timeout, blocco dei tentativi duplicati e processi concorrenti.
- Chromium reale sul server locale: scelta cartella simulata, modifica listino, scansione con AI simulata, correzione annuncio, ricalcolo, esportazione, ricaricamento, foto, protezione da HTML iniettato e layout mobile senza scorrimento orizzontale.

La copertura misura le righe eseguite; non dimostra da sola l'assenza di difetti. I rami non coperti comprendono avvio dell'app, alcune condizioni di errore e ciclo di monitoraggio continuo.

## Problemi trovati e corretti

- La configurazione verificava solo il prezzo Altro: ora valida ogni categoria e le regole avanzate.
- Le preferenze personali venivano scritte nel file pubblico: ora vengono conservate in `data/settings.json`, escluso da Git.
- La deduplicazione dipendeva dall'ordine dei nomi e concatenava dati senza separazione: ora usa hash separati e ordinati dei contenuti.
- Spostare una cartella rendeva inutilizzabili i percorsi delle foto: ora la scansione li aggiorna senza sovrascrivere le correzioni dell'utente.
- Campi AI non testuali e liste di incertezze malformate potevano rompere l'interfaccia: ora vengono ripuliti.
- L'interfaccia permetteva categorie libere: ora offre le categorie del listino e gli stati previsti.
- Un salvataggio poteva lasciare il prezzo visualizzato non aggiornato finché il campo manteneva il focus: ora aggiorna subito la scheda.
- L'export includeva percorsi locali: ora i riferimenti alle immagini sono relativi al pacchetto.
- Mancavano protezioni contro publisher concorrenti: aggiunto lock con indicazioni per recupero dopo interruzioni.
- Il controllo dipendenze ha segnalato Pillow 12.3.0: requisito aggiornato a Pillow 13 o successiva nella stessa versione maggiore, installata in ambiente virtuale.

## Riproduzione

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m coverage run -m unittest discover -v
python -m coverage report -m
python -m ruff check .
python -m compileall -q app.py core.py publisher.py pick_folder.py
python -m pip_audit -r requirements.txt
```

GitHub Actions ripete i controlli su Windows e Linux e salva gli screenshot come artefatti. Il dialogo nativo viene simulato nei test: la sua effettiva apertura dipende dalla disponibilità di Tkinter e di una sessione desktop.

## Limiti operativi ancora presenti

- Nessuna chiave API disponibile durante la verifica: qualità del riconoscimento, accesso al modello e costi non provati con foto reali. Le risposte remote sono simulate nei test.
- Nessun account Vinted collegato: login, menu, caricamento e pubblicazione sul sito reale non verificati. I selettori di esempio sono intenzionalmente vuoti.
- Foto sfuse non vengono raggruppate per somiglianza. Occorre una sottocartella per ogni capo con più foto.
- Materiale, taglia e marca non leggibili richiedono inserimento manuale. Stato e pacco richiedono verifica fisica.
- Non esistono stime di mercato: il listino è una scelta modificabile dell'utente.
- Il monitoraggio funziona solo con app avviata; va abilitato dopo avere completato la copia delle foto. Un gruppo modificato dopo l'analisi genera un nuovo ID, da controllare per evitare duplicati logici.
- Nessuna pubblicazione continua automatica dalla cartella. Evitare scansioni durante l'uso del publisher; una terminazione brusca può richiedere la rimozione manuale del lock dopo verifica dell'account.
- Archivio JSON adatto a uso personale locale. Nessuna cifratura, autenticazione multiutente, sincronizzazione cloud o garanzia di ripristino in caso di corruzione del disco. Conservare backup di `data/`.

Il risultato verificato è un preparatore di annunci locale con adapter di pubblicazione da completare, non un autolister Vinted già operativo end-to-end.

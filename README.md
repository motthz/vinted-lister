# Vinted Studio

App locale per Windows: scelta cartella, riconoscimento foto tramite OpenAI, annunci modificabili, prezzi fissi per categoria, esportazione foto e dati. T-shirt **5 €**, felpe **15 €**. Il [listino completo](PREZZI.md) contiene 34 categorie modificabili: camicie 10 €, jeans e maglioni 15 €, giacche 20 €, cappotti e piumini 30 €. Sono prezzi iniziali scelti per il guardaroba, non quotazioni di mercato. Nessun dato inventato per completare campi mancanti.

## Avvio

Richiede Python 3.12+. Da PowerShell nella cartella progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:OPENAI_API_KEY = 'la-tua-chiave'
python app.py
```

Si apre http://127.0.0.1:8765. In seguito puoi usare `Avvia.bat` se la variabile API è già configurata nell'ambiente. La chiave non viene salvata dall'app né inviata al browser. Le chiamate API hanno un costo e le foto vengono inviate a OpenAI. Senza chiave è possibile aprire l'app e configurarla, ma non analizzare nuove foto.

1. Premi **Scegli cartella**, quindi **Salva impostazioni**.
2. Organizza ogni capo in una sottocartella, es. `guardaroba/felpa-blu/1.jpg`, `2.jpg`, `etichetta.jpg`. Una foto nella radice è trattata come un capo separato. Non è implementato il raggruppamento visivo automatico di foto sfuse.
3. Premi **Analizza cartella**, oppure abilita il monitoraggio. L'app deve rimanere aperta. Attendi la fine della copia delle foto prima della scansione.
4. Controlla campi e stato fisico; salva per ricalcolare il prezzo. Se un dato non è visibile, compilalo manualmente. La categoria locale `maglietta` corrisponde alle T-shirt.
5. Esporta l'annuncio: `data/exports/<id>/` contiene foto, JSON e testo. Apri Vinted dal pulsante per completare la pubblicazione.

Il prezzo è la voce esatta della tabella `pricing.base`, senza maggiorazioni; per cambiare i prezzi usa i campi della tabella nelle impostazioni. Il JSON avanzato consente di modificare anche il motore a formula. Categoria non riconosciuta: usa `altro` e verifica. Puoi attivare il motore alternativo con `mode: "formula"`: base categoria o prezzo originale × retail_ratio, moltiplicatori stato e marca, margine trattativa, arrotondamento e limiti. Il prezzo originale si inserisce manualmente. Le preferenze e il percorso personale della cartella vengono salvati in `data/settings.json`, escluso da Git; `config.json` rimane il modello pubblico. Le regole nuove si applicano ai nuovi articoli e agli annunci salvati successivamente.

## Integrazione browser: da completare sul sito reale

**La pubblicazione automatica sul tuo account non è ancora configurata né collaudata.** È presente un adapter Playwright che richiede una sessione utente e selettori verificati sulla versione corrente di Vinted. Non usa API private né aggira CAPTCHA. L'utilizzo di strumenti esterni va verificato rispetto ai termini Vinted e alle autorizzazioni del tuo account: https://www.vinted.it/terms_and_conditions.

```powershell
python -m playwright install chromium
python publisher.py --login
```

Il login si effettua nel browser, senza fornire password all'app. La sessione è conservata in `browser-profile/`: proteggi questa cartella.

Copia `vinted-selectors.example.json` in `vinted-selectors.json` e configura tutti i selettori reali. L'adapter supporta campi testuali (`fill`), select HTML (`select`) e menu personalizzati (`click_option`, con traduzioni tramite `values`). Categorie gerarchiche e menu complessi possono richiedere di estendere l'adapter; il template non garantisce la compatibilità con il sito corrente.

```powershell
python publisher.py ID_ANNUNCIO
python publisher.py ID_ANNUNCIO --publish
```

Il primo comando compila e lascia il controllo all'utente. Il secondo invia solo se sono configurati anche `publish` e `success`. Non c'è un invio automatico in background dei nuovi capi. Un timeout dopo l'invio lascia lo stato `publishing`: verifica il tuo profilo prima di qualsiasi nuovo tentativo. Nessun retry automatico della pubblicazione. Un lock blocca publisher concorrenti e modifiche dall'editor durante la compilazione. Se il processo termina bruscamente, il lock può rimanere: verifica il profilo Vinted e lo stato degli annunci prima di rimuovere `data/publisher.lock`. Evita scansioni durante la pubblicazione.

## Verifiche

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m coverage run -m unittest discover -v
python -m coverage report -m
python -m ruff check .
python -m pip_audit -r requirements.txt
```

La suite include prezzi di tutte le categorie, validazione dati, raggruppamento e deduplicazione, richieste HTTP, salvataggio, esportazione, protezioni locali, protocollo immagini AI e stati del publisher. Chromium verifica il flusso completo su desktop e mobile. Le chiamate AI e il sito Vinted sono simulati nei test: nessun costo API e nessun annuncio reale. GitHub Actions esegue i controlli su Windows e Linux.

Dettagli e limiti: [VALIDAZIONE.md](VALIDAZIONE.md).

Analisi reale e pubblicazione richiedono rispettivamente chiave API e account, non inclusi nel progetto. L'app ascolta solo su localhost; non esporla su Internet. I dati locali non sono cifrati. Non eliminare gli ID archiviati se vuoi conservare la deduplicazione. Foto, dati, impostazioni personali, chiavi e profili browser sono esclusi dalla repository.

Documentazione visione: https://developers.openai.com/api/docs/guides/images-vision.

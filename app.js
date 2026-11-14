'use strict';
const $ = selector => document.querySelector(selector);
const token = window.APP_TOKEN;
const labels = {title:'Titolo', description:'Descrizione', category:'Tipo di capo', brand:'Marca', size:'Taglia', condition:'Stato', color:'Colore', material:'Materiale', package_size:'Pacco', retail_price:'Prezzo originale (facoltativo)'};
const conditions = {nuovo_con_cartellino:'Nuovo con cartellino', nuovo_senza_cartellino:'Nuovo senza cartellino', ottimo:'Ottimo', buono:'Buono', discreto:'Discreto'};
const defaultsFields = ['size','brand','material','package_size','condition'];
let cfg, state, snapshot = '', filter = 'all', uploading = false, settingsDirty = false, keyEditing = false;
const edits = new Map();
let toastTimer;
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').hidden = true, 6000);
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function post(path, body = {}) {
  const res = await fetch('/api/' + path, {method:'POST', headers:{'Content-Type':'application/json', 'X-App-Token':token}, body:JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Operazione non riuscita');
  return data;
}
function field(key, value, name = key) {
  const label = el('label', labels[key]);
  let input;
  if (['category','condition'].includes(key)) {
    input = el('select');
    input.append(new Option('Da scegliere', ''));
    const options = key === 'category' ? Object.keys(cfg.pricing.base) : Object.keys(conditions);
    options.forEach(v => input.append(new Option(key === 'condition' ? conditions[v] : v === 'maglietta' ? 'T-shirt' : v, v)));
  } else input = el(key === 'description' ? 'textarea' : 'input');
  input.name = name;
  input.value = value ?? '';
  if (key === 'retail_price') {input.type = 'number'; input.min = '.01'; input.step = '.01';}
  label.append(input);
  return label;
}
function populateSettings() {
  $('#folder').value = cfg.folder;
  $('#model').value = cfg.model;
  $('#watch').checked = cfg.watch;
  $('#rules').value = JSON.stringify(cfg.pricing, null, 2);
  $('#price-table').replaceChildren();
  Object.entries(cfg.pricing.base).forEach(([key, value]) => {
    const label = el('label', key === 'maglietta' ? 'T-shirt' : key);
    const input = el('input');
    Object.assign(input, {type:'number', min:'.01', max:'10000', step:'.01', value, required:true});
    input.dataset.category = key;
    input.oninput = () => {
      try {const rules = JSON.parse($('#rules').value); rules.base[key] = Number(input.value); $('#rules').value = JSON.stringify(rules, null, 2);} catch (_) { /* Error shown when saving. */ }
    };
    label.append(input); $('#price-table').append(label);
  });
  $('#defaults').replaceChildren();
  defaultsFields.forEach(key => $('#defaults').append(field(key, cfg.defaults?.[key], 'default-' + key)));
  settingsDirty = false;
}
function updateCounts() {
  const items = state.items;
  const ready = items.filter(i => i.status === 'ready');
  $('#n-all').textContent = items.length;
  $('#n-todo').textContent = items.filter(i => i.status === 'draft').length;
  $('#n-ready').textContent = ready.length;
  $('#count').textContent = items.length ? `${ready.length} pronti · ${items.filter(i => i.status === 'draft').length} da completare` : 'Nessun capo da gestire';
  $('#download').hidden = ready.length === 0;
}
function render(force = false) {
  if (!state) return;
  updateCounts();
  // Polling must never destroy pending or unsaved edits, even after blur.
  if (!force && edits.size) return;
  if (!force && $('#items').contains(document.activeElement)) return;
  const next = JSON.stringify(state.items) + filter;
  if (!force && next === snapshot) return;
  snapshot = next;
  const items = state.items.filter(i => filter === 'all' || (filter === 'todo' ? i.status === 'draft' : i.status === 'ready'));
  $('#items').replaceChildren();
  $('#empty').hidden = !!items.length;
  if (!items.length) {
    $('#empty h2').textContent = state.items.length ? 'Tutto a posto in questa lista.' : 'Il prossimo annuncio parte da una foto.';
    $('#empty p').textContent = state.items.length ? 'Passa a un’altra scheda per vedere gli altri capi.' : 'Aggiungi le foto dello stesso capo. L’app le organizza e avvia l’analisi da sola.';
  }
  items.sort((a,b) => Number(b.status === 'draft') - Number(a.status === 'draft')).forEach(item => $('#items').append(card(item)));
}
function card(item) {
  const article = el('article', undefined, 'card'); article.dataset.id = item.id;
  const images = el('div', undefined, 'images');
  item.photos.forEach((_, n) => {const img = el('img'); img.src = `/photo?id=${encodeURIComponent(item.id)}&n=${n}`; img.alt = `Foto ${n+1}`; img.loading = 'lazy'; images.append(img);});
  article.append(images);
  const body = el('div', undefined, 'body'), top = el('div', undefined, 'bar');
  const statusText = {ready:'Pronto per esportazione', draft:'Manca qualche dettaglio', published:'Pubblicato', publishing:'Invio da verificare'};
  top.append(el('span', statusText[item.status] || 'Da verificare', 'badge ' + (item.status === 'ready' ? 'ready' : '')));
  const price = el('span', Number(item.price).toLocaleString('it-IT',{style:'currency',currency:'EUR'}), 'price');
  top.append(price); body.append(top, el('h3', item.title || item.name));
  const form = el('form');
  const missing = state.missing[item.id] || [];
  const locked = ['published','publishing'].includes(item.status);
  const short = el('p', [item.brand, item.size, item.color].filter(Boolean).join(' · '), 'saved-summary');
  body.append(short);
  const remaining = el('div');
  missing.forEach(key => {const label = field(key, item[key]); label.classList.add('needs-input'); remaining.append(label);});
  form.append(remaining);
  const details = el('details'); details.append(el('summary', 'Vedi o modifica tutti i dati'));
  Object.keys(labels).filter(key => !missing.includes(key)).forEach(key => details.append(field(key, item[key])));
  details.append(el('p', item.price_reason, 'muted'));
  form.append(details);
  if (item.uncertainties?.length) form.append(el('p', 'Da controllare: ' + item.uncertainties.join('; '), 'warning'));
  const saveStatus = el('p', locked ? 'Annuncio bloccato dopo l’invio' : 'Le modifiche si salvano da sole', 'save-status');
  const save = el('button', 'Salva ora', 'secondary'); save.type = 'submit';
  form.append(saveStatus, save);
  let timer;
  async function persist() {
    clearTimeout(timer);
    if (!form.reportValidity()) return false;
    const values = Object.fromEntries(new FormData(form));
    const revision = JSON.stringify(values);
    edits.set(item.id, revision);
    saveStatus.textContent = 'Salvataggio...';
    try {
      await post('item', {id:item.id, ...values});
      // A newer edit must not be marked saved by an older response.
      if (JSON.stringify(Object.fromEntries(new FormData(form))) !== revision) return false;
      edits.delete(item.id);
      saveStatus.textContent = 'Salvato';
      await refresh(false);
      const saved = state.items.find(i => i.id === item.id);
      if (saved) {
        price.textContent = Number(saved.price).toLocaleString('it-IT',{style:'currency',currency:'EUR'});
        top.querySelector('.badge').textContent = statusText[saved.status];
        top.querySelector('.badge').className = 'badge ' + (saved.status === 'ready' ? 'ready' : '');
      }
      return true;
    } catch (error) {saveStatus.textContent = 'Non salvato: ' + error.message; return false;}
  }
  form.oninput = () => {
    edits.set(item.id, true); saveStatus.textContent = 'Modifiche in corso...'; clearTimeout(timer); timer = setTimeout(persist, 800);
  };
  form.onsubmit = async event => {event.preventDefault(); if (await persist()) {snapshot = ''; render();}};
  if (locked) form.querySelectorAll('input,select,textarea,button').forEach(input => input.disabled = true);
  body.append(form);
  const actions = el('div', undefined, 'actions');
  const copy = el('button', 'Copia descrizione', 'ghost'); copy.onclick = () => navigator.clipboard.writeText(form.elements.description?.value || item.description || '').then(() => toast('Descrizione copiata')).catch(() => toast('Copia non disponibile in questo browser'));
  const exp = el('button', 'Esporta questo capo', 'ghost'); exp.onclick = async () => {if (edits.has(item.id) && !await persist()) return; try {const data = await post('export',{id:item.id}); toast('Esportato in ' + data.path);} catch (error) {toast(error.message);}};
  actions.append(copy, exp); body.append(actions); article.append(body); return article;
}
async function refresh(draw = true) {
  const res = await fetch('/api/state');
  if (!res.ok) throw Error('Connessione all’app non disponibile');
  state = await res.json();
  if (!cfg) {cfg = state.config; populateSettings();}
  $('#setup').hidden = state.has_key && !keyEditing;
  $('#remember-label').hidden = !state.remember_key;
  $('#scan').disabled = state.state.busy;
  $('#status').textContent = uploading ? 'Caricamento foto...' : state.state.message;
  $('#notice').textContent = state.state.errors.join('\n');
  updateCounts();
  if (draw) render();
}
async function chooseFolder(quick) {
  const button = quick ? $('#choose-folder') : $('#pick'); button.disabled = true;
  try {
    const data = await post('folder'); if (!data.folder) return;
    $('#folder').value = data.folder;
    if (quick) {
      const next = {...cfg, folder:data.folder, watch:true};
      await post('config', next); cfg = next; populateSettings(); await post('scan'); await refresh();
      toast('Cartella collegata. Le nuove foto vengono analizzate automaticamente.');
    } else settingsDirty = true;
  } catch (error) {toast(error.message);} finally {button.disabled = false;}
}
async function addPhotos(files) {
  if (uploading) return;
  const list = Array.from(files);
  if (!list.length) return;
  if (list.length > 20 || list.reduce((n,f) => n + f.size, 0) > 20 * 1024 * 1024) return toast('Scegli fino a 20 foto, massimo 20 MB in totale.');
  if (list.some(f => !['image/jpeg','image/png','image/webp'].includes(f.type))) return toast('Sono supportate foto JPG, PNG e WEBP.');
  uploading = true; $('#dropzone').setAttribute('aria-busy', 'true'); $('#status').textContent = 'Caricamento foto...';
  try {
    const photos = await Promise.all(list.map(file => new Promise((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve({data:reader.result.split(',')[1]}); reader.onerror = () => reject(Error('Impossibile leggere una foto')); reader.readAsDataURL(file);
    })));
    await post('import', {photos}); toast('Foto aggiunte: ora prepariamo l’annuncio.'); await refresh();
  } catch (error) {toast(error.message);} finally {uploading = false; $('#upload').value = ''; $('#dropzone').removeAttribute('aria-busy');}
}
$('#dropzone').onclick = () => $('#upload').click();
$('#dropzone').onkeydown = event => {if (['Enter',' '].includes(event.key)) {event.preventDefault(); $('#upload').click();}};
$('#upload').onchange = event => addPhotos(event.target.files);
$('#dropzone').ondragover = event => {event.preventDefault(); $('#dropzone').classList.add('over');};
$('#dropzone').ondragleave = () => $('#dropzone').classList.remove('over');
$('#dropzone').ondrop = event => {event.preventDefault(); $('#dropzone').classList.remove('over'); addPhotos(event.dataTransfer.files);};
$('#open-settings').onclick = () => $('#settings-dialog').showModal();
$('#close-settings').onclick = () => $('#settings-dialog').close();
$('#settings-form').oninput = () => {settingsDirty = true; $('#settings-status').textContent = 'Da salvare';};
$('#choose-folder').onclick = () => chooseFolder(true);
$('#pick').onclick = () => chooseFolder(false);
$('#scan').onclick = async () => {try {await post('scan'); await refresh();} catch (error) {toast(error.message);}};
$('#key-form').onsubmit = async event => {
  event.preventDefault(); const button = $('#key-form button'); button.disabled = true;
  try {await post('key', {key:$('#api-key').value, remember:state.remember_key && $('#remember-key').checked}); $('#api-key').value = ''; keyEditing = false; await post('scan'); await refresh(); toast('Chiave salvata. Aggiungi le foto per iniziare.');}
  catch (error) {toast(error.message);} finally {button.disabled = false;}
};
$('#change-key').onclick = () => {keyEditing = true; $('#settings-dialog').close(); $('#setup').hidden = false; $('#api-key').focus();};
$('#settings-form').onsubmit = async event => {
  event.preventDefault();
  if (edits.size) return toast('Attendi il salvataggio delle modifiche prima di cambiare preferenze.');
  try {
    const pricing = JSON.parse($('#rules').value);
    document.querySelectorAll('#price-table input').forEach(input => {if (!input.checkValidity()) throw Error('Inserisci prezzi positivi con due decimali'); pricing.base[input.dataset.category] = Number(input.value);});
    const defaults = Object.fromEntries(defaultsFields.map(key => [key, $('#defaults [name="default-' + key + '"]').value]));
    const next = {folder:$('#folder').value, model:$('#model').value, watch:$('#watch').checked, pricing, defaults};
    await post('config', next); cfg = next; settingsDirty = false;
    await post('defaults');
    $('#settings-status').textContent = 'Salvate'; $('#settings-dialog').close();
    snapshot = ''; await refresh(); toast('Preferenze salvate e dettagli mancanti aggiornati.');
  } catch (error) {toast(error.message);}
};
$('#rules').onchange = () => {
  try {const rules = JSON.parse($('#rules').value); document.querySelectorAll('#price-table input').forEach(input => {if (input.dataset.category in rules.base) input.value = rules.base[input.dataset.category];});}
  catch (_) {toast('Le regole avanzate non contengono JSON valido');}
};
document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => {
  if (edits.size) return toast('Attendi il salvataggio delle modifiche prima di cambiare scheda.');
  filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('active', b === button)); render(true);
});
$('#download').onclick = event => {if (edits.size) {event.preventDefault(); toast('Attendi il salvataggio prima di scaricare gli annunci.');}};
window.addEventListener('beforeunload', event => {if (edits.size || settingsDirty || uploading) {event.preventDefault(); event.returnValue = '';}});
refresh().catch(error => toast(error.message));
setInterval(() => refresh().catch(() => {$('#status').textContent = 'Connessione interrotta. Riapri l’app per continuare.';}), 2500);

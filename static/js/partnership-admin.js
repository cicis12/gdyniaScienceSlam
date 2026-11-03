(() => {
  let state = JSON.parse(document.getElementById('partnership-config').textContent);
  const types = JSON.parse(document.getElementById('partnership-types').textContent);
  const form = document.getElementById('partnership-editor-form');
  const sections = document.getElementById('partnership-sections');
  const status = document.getElementById('partnership-editor-status');
  const files = new Map();
  const urls = new Map();
  let dirty = false;
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const changed = () => { dirty = true; status.textContent = 'Niezapisane zmiany — zapisz całą stronę, aby je opublikować.'; };
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function button(parent, text, action) {
    const element = node('button', text);
    element.type = 'button';
    element.addEventListener('click', action);
    parent.append(element);
    return element;
  }
  function field(parent, target, key, label, options = {}) {
    const wrapper = node('label');
    const input = node(options.rows ? 'textarea' : 'input');
    if (!options.rows) input.type = options.type || 'text';
    if (options.type === 'checkbox') input.checked = Boolean(target[key]);
    else input.value = target[key] ?? '';
    if (options.rows) input.rows = options.rows;
    if (options.max) input.maxLength = options.max;
    if (options.required) input.required = true;
    if (options.type === 'number') { input.min = 0; input.max = 100000; }
    input.addEventListener('input', () => {
      target[key] = options.type === 'checkbox' ? input.checked : options.type === 'number' ? Number(input.value) : input.value;
      changed();
    });
    wrapper.append(node('span', label), input);
    parent.append(wrapper);
    return input;
  }
  function photo(parent, person, key) {
    const image = node('img');
    image.width = 100; image.height = 100; image.alt = 'Zdjęcie kontaktowe';
    const source = urls.get(key) || person.photo;
    if (source) image.src = source;
    image.hidden = !source;
    parent.append(image);
    const label = node('label', 'Zdjęcie (JPG, PNG, WebP; do 10 MB)');
    const input = node('input'); input.type = 'file'; input.accept = 'image/jpeg,image/png,image/webp';
    input.addEventListener('change', () => selectPhoto(key, input.files[0], image));
    label.append(input); parent.append(label);
    if (files.has(key)) parent.append(node('small', 'Wybrane zdjęcie: ' + files.get(key).name));
  }
  function selectPhoto(key, file, image) {
    if (!file) return;
    if (urls.has(key)) URL.revokeObjectURL(urls.get(key));
    files.set(key, file); urls.set(key, URL.createObjectURL(file));
    image.src = urls.get(key); image.hidden = false; changed();
  }
  function newPerson() { return { id: id(), name: '', occupation: '', details: '', photo: '' }; }
  function renderSection(section, open = false) {
    const details = node('details', null, 'member-editor');
    details.id = 'section-' + section.id; details.open = open;
    const summary = node('summary', `${types[section.type]} · ${section.title || 'Bez nagłówka'}`);
    details.append(summary);
    const fields = node('div', null, 'member-fields'); details.append(fields);
    field(fields, section, 'title', section.type === 'heading' ? 'Tekst nagłówka' : 'Nagłówek sekcji (opcjonalny)', { max: 300, required: section.type === 'heading' });
    field(fields, section, 'sort_order', 'Kolejność', { type: 'number', required: true });
    field(fields, section, 'enabled', 'Pokaż sekcję', { type: 'checkbox' });
    if (['paragraph', 'contact'].includes(section.type)) field(fields, section, 'text', 'Treść', { rows: 6, max: 10000 });
    if (['grid', 'icons'].includes(section.type)) section.items.forEach((item, index) => {
      const group = node('fieldset'); group.append(node('legend', 'Pole ' + (index + 1))); fields.append(group);
      if (section.type === 'icons') field(group, item, 'svg', 'Kod SVG (pełny kod z viewBox)', { rows: 4, max: 20000 });
      field(group, item, 'title', 'Tytuł', { max: 160 });
      field(group, item, 'text', 'Tekst', { rows: 4, max: 10000 });
    });
    if (section.type === 'person') {
      section.people.forEach((person, index) => {
        const group = node('fieldset'); group.append(node('legend', 'Osoba ' + (index + 1))); fields.append(group);
        field(group, person, 'name', 'Imię i nazwisko', { max: 160 });
        field(group, person, 'occupation', 'Stanowisko / zajęcie', { max: 160 });
        photo(group, person, `photo:${section.id}:${person.id}`);
        field(group, person, 'details', 'Dane kontaktowe (HTML)', { rows: 4, max: 10000 });
        button(group, 'Usuń osobę', () => { section.people.splice(index, 1); changed(); refresh(section.id); });
      });
      const add = button(fields, 'Dodaj osobę', () => { section.people.push(newPerson()); changed(); refresh(section.id); });
      add.disabled = section.people.length >= 20;
      field(fields, section, 'team_link', 'Dodaj link do całego zespołu poniżej osób', { type: 'checkbox' });
      field(fields, section, 'team_link_label', 'Tekst linku do zespołu', { max: 160, required: true });
    }
    if (section.type === 'faq') {
      section.items.forEach((item, index) => {
        const group = node('fieldset'); group.append(node('legend', 'Pytanie ' + (index + 1))); fields.append(group);
        field(group, item, 'question', 'Pytanie', { max: 300, required: true });
        field(group, item, 'answer', 'Odpowiedź', { rows: 4, max: 10000, required: true });
        button(group, 'Usuń pytanie', () => { section.items.splice(index, 1); changed(); refresh(section.id); });
      });
      const add = button(fields, 'Dodaj pytanie', () => { section.items.push({ question: '', answer: '' }); changed(); refresh(section.id); });
      add.disabled = section.items.length >= 50;
    }
    button(fields, 'Usuń sekcję', () => {
      if (confirm('Usunąć tę sekcję? Zmiana zostanie opublikowana po zapisaniu całej strony.')) {
        state.sections = state.sections.filter(item => item.id !== section.id); changed(); refresh();
      }
    }).className = 'delete-member';
    return details;
  }
  function refresh(openId) {
    const opened = new Set([...sections.querySelectorAll('details[open]')].map(item => item.id));
    sections.replaceChildren(...state.sections.map(section => renderSection(section, section.id === openId || opened.has('section-' + section.id))));
    document.getElementById('section-count').textContent = `${state.sections.length}/50`;
    document.getElementById('add-partnership-section').disabled = state.sections.length >= 50;
  }
  ['title', 'featured', 'uuid_only', 'teaser', 'link_label', 'recipient'].forEach(key => {
    const input = form.elements.namedItem(key);
    input.addEventListener('input', () => { state[key] = input.type === 'checkbox' ? input.checked : input.value; changed(); });
  });
  document.getElementById('feature-photo').addEventListener('change', event => selectPhoto('feature_photo', event.target.files[0], document.getElementById('feature-photo-preview')));
  document.getElementById('add-partnership-section').addEventListener('click', () => {
    const type = document.getElementById('new-section-type').value;
    const section = { id: id(), type, title: types[type], enabled: false, sort_order: Math.min(100000, Math.max(-1, ...state.sections.map(s => s.sort_order)) + 1) };
    if (['paragraph', 'contact'].includes(type)) section.text = '';
    if (['grid', 'icons'].includes(type)) section.items = Array.from({ length: type === 'grid' ? 6 : 3 }, () => ({ title: '', text: '', ...(type === 'icons' ? { svg: '' } : {}) }));
    if (type === 'person') Object.assign(section, { people: [newPerson()], team_link: false, team_link_label: 'Poznaj cały zespół' });
    if (type === 'faq') section.items = [];
    state.sections.push(section); changed(); refresh(section.id);
    document.getElementById('section-' + section.id).scrollIntoView({ block: 'nearest' });
  });
  function payload() {
    const body = new FormData(); body.append('config', JSON.stringify(state));
    const keys = ['feature_photo', ...state.sections.filter(s => s.type === 'person').flatMap(s => s.people.map(p => `photo:${s.id}:${p.id}`))];
    keys.forEach(key => { if (files.has(key)) body.append(key, files.get(key)); });
    return body;
  }
  async function request(action) {
    const response = await fetch('/admin/become-a-partner/' + action, { method: 'POST', body: payload() });
    if (response.redirected) throw new Error('Sesja wygasła. Zaloguj się ponownie w drugiej karcie, aby zachować zmiany.');
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Nie udało się przetworzyć zmian. Spróbuj ponownie.');
    }
    return response;
  }
  form.addEventListener('invalid', event => { const details = event.target.closest('details'); if (details) details.open = true; }, true);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const fields = document.getElementById('partnership-editor-fields');
    const save = document.getElementById('save-partnership');
    const preview = document.getElementById('preview-partnership');
    fields.disabled = true; save.disabled = true; preview.disabled = true;
    status.textContent = 'Zapisywanie całej strony…';
    try {
      const response = await request('save');
      const data = await response.json();
      state = data.config;
      files.clear(); urls.forEach(url => URL.revokeObjectURL(url)); urls.clear();
      document.getElementById('feature-photo').value = '';
      const image = document.getElementById('feature-photo-preview');
      image.src = state.feature_photo; image.hidden = !state.feature_photo;
      dirty = false; refresh(); status.textContent = data.message;
    } catch (error) { status.textContent = error.message; }
    finally { fields.disabled = false; save.disabled = false; preview.disabled = false; }
  });
  const dialog = document.getElementById('partnership-preview');
  const frame = document.getElementById('partnership-preview-frame');
  const previewButton = document.getElementById('preview-partnership');
  const previewStatus = document.getElementById('partnership-preview-status');
  let previewForm = null;
  let previewTimeout = null;
  function finishPreview() {
    clearTimeout(previewTimeout);
    previewTimeout = null;
    previewButton.disabled = false;
    previewForm?.remove();
    previewForm = null;
  }
  function previewError(message) {
    finishPreview();
    frame.hidden = true;
    previewStatus.hidden = false;
    previewStatus.textContent = message;
  }
  frame.addEventListener('load', () => {
    if (!previewForm) return;
    try {
      // Ignore the iframe's initial about:blank document.
      const doc = frame.contentDocument;
      if (!doc || frame.contentWindow.location.href === 'about:blank') return;
      if (doc.querySelector('.partnership-page')) {
        finishPreview();
        previewStatus.hidden = true;
        frame.hidden = false;
      } else {
        let message = 'Nie udało się załadować podglądu. Zamknij podgląd i spróbuj ponownie.';
        try {
          const error = JSON.parse(doc.body.textContent);
          if (typeof error.detail === 'string') message = error.detail;
        } catch { /* The response may be a login page rather than JSON. */ }
        previewError(message);
      }
    } catch {
      previewError('Nie udało się wyświetlić podglądu. Zamknij podgląd i spróbuj ponownie.');
    }
  });
  previewButton.addEventListener('click', () => {
    previewButton.disabled = true;
    previewStatus.textContent = 'Ładowanie podglądu…';
    previewStatus.hidden = false;
    frame.hidden = true;
    dialog.showModal();
    document.body.classList.add('settings-preview-open');
    try {
      // A normal document navigation works in embedded browsers too. Scripts and
      // submissions inside the resulting preview remain blocked by its sandbox.
      previewForm = document.createElement('form');
      previewForm.method = 'POST';
      previewForm.action = '/admin/become-a-partner/preview';
      previewForm.enctype = 'multipart/form-data';
      previewForm.target = frame.name;
      previewForm.hidden = true;
      for (const [key, value] of payload()) {
        const input = document.createElement('input');
        input.name = key;
        if (value instanceof File) {
          input.type = 'file';
          const transfer = new DataTransfer();
          transfer.items.add(value);
          input.files = transfer.files;
        } else {
          input.type = 'hidden';
          input.value = value;
        }
        previewForm.append(input);
      }
      document.body.append(previewForm);
      previewTimeout = setTimeout(() => previewError('Podgląd ładuje się zbyt długo. Zamknij go i spróbuj ponownie.'), 30000);
      HTMLFormElement.prototype.submit.call(previewForm);
    } catch {
      previewError('Nie udało się otworzyć podglądu. Zamknij go i spróbuj ponownie.');
    }
  });
  document.getElementById('close-partnership-preview').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    finishPreview();
    frame.src = 'about:blank';
    frame.hidden = true;
    document.body.classList.remove('settings-preview-open');
  });
  document.getElementById('partnership-preview-width').addEventListener('change', event => { frame.style.width = event.target.value; });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  refresh();
})();

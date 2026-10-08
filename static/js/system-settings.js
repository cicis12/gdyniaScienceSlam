(() => {
  const tabList = document.getElementById('settings-tabs');
  if (!tabList) return;
  const tabs = [...tabList.querySelectorAll('[data-settings-tab]')];
  const panels = [...document.querySelectorAll('[data-settings-panel]')];
  const selectTab = (id, focus = false) => {
    const selected = tabs.find(tab => tab.dataset.settingsTab === id) || tabs[0];
    tabs.forEach(tab => {
      const active = tab === selected;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach(panel => {
      panel.hidden = panel.id !== selected.dataset.settingsTab;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', `tab-${panel.id}`);
    });
    if (focus) selected.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => {
      selectTab(tab.dataset.settingsTab);
      history.replaceState(null, '', `#${tab.dataset.settingsTab}`);
    });
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
      else if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === 'Home') target = tabs[0];
      else if (event.key === 'End') target = tabs[tabs.length - 1];
      if (!target) return;
      event.preventDefault();
      selectTab(target.dataset.settingsTab, true);
      history.replaceState(null, '', `#${target.dataset.settingsTab}`);
    });
  });
  window.addEventListener('hashchange', () => selectTab(location.hash.slice(1)));
  selectTab(location.hash.slice(1));
  tabList.hidden = false;
})();

(() => {
  const form = document.getElementById('site-theme-form');
  const dialog = document.getElementById('site-theme-preview');
  const frame = document.getElementById('preview-frame');
  if (!form || !dialog || !frame) return;
  const fields = [...form.querySelectorAll('input[type="color"]')];
  const applyPreview = () => {
    const doc = frame.contentDocument;
    if (!doc || !doc.body) return;
    const modes = document.getElementById('page-modes-form');
    const mode = modes?.elements.namedItem(doc.body.dataset.displayPage);
    if (mode) doc.body.dataset.displayMode = mode.value;
    fields.forEach(field => doc.documentElement.style.setProperty(`--theme-${field.name.replaceAll('_', '-')}`, field.value));
    const previewWindow = frame.contentWindow;
    if (!previewWindow.previewWritesBlocked) {
      // Keep navigation available while blocking writes in the preview.
      doc.addEventListener('submit', event => { event.preventDefault(); event.stopImmediatePropagation(); }, true);
      doc.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !doc.querySelector('dialog[open]')) {
          event.preventDefault();
          dialog.close();
        }
      });
      const originalFetch = previewWindow.fetch.bind(previewWindow);
      previewWindow.fetch = (input, options = {}) => {
        const method = options.method || input?.method || 'GET';
        if (!['GET', 'HEAD'].includes(method.toUpperCase())) return Promise.reject(new Error('Podgląd nie zapisuje zmian.'));
        return originalFetch(input, options);
      };
      const originalOpen = previewWindow.XMLHttpRequest.prototype.open;
      previewWindow.XMLHttpRequest.prototype.open = function(method, ...args) {
        if (!['GET', 'HEAD'].includes(method.toUpperCase())) throw new Error('Podgląd nie zapisuje zmian.');
        return originalOpen.call(this, method, ...args);
      };
      previewWindow.previewWritesBlocked = true;
    }
  };
  fields.forEach(field => field.addEventListener('input', () => {
    field.closest('label').querySelector('output').textContent = field.value;
    if (dialog.open) applyPreview();
  }));
  frame.addEventListener('load', applyPreview);
  document.getElementById('preview-colors').addEventListener('click', () => {
    dialog.showModal();
    document.body.classList.add('settings-preview-open');
    frame.src = '/admin/content/preview';
  });
  document.getElementById('close-preview').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    document.body.classList.remove('settings-preview-open');
    frame.removeAttribute('src');
  });
  document.getElementById('preview-width').addEventListener('change', event => {
    frame.style.width = event.target.value;
  });
})();

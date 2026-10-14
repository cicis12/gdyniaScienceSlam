(() => {
  const key = 'gss-display-mode';
  const readMode = () => {
    try { return localStorage.getItem(key) === 'light' ? 'light' : 'dark'; }
    catch { return 'dark'; }
  };
  function apply(mode) {
    document.body.dataset.displayMode = mode;
    document.querySelectorAll('.theme-switch').forEach(button => {
      button.hidden = false;
      button.setAttribute('aria-checked', String(mode === 'dark'));
      button.title = mode === 'dark' ? 'Włącz jasny motyw' : 'Włącz ciemny motyw';
    });
  }
  // Loaded immediately after <body>, before page content can paint.
  apply(readMode());
  document.addEventListener('DOMContentLoaded', () => apply(readMode()));
  document.addEventListener('click', event => {
    if (!event.target.closest('.theme-switch')) return;
    const mode = document.body.dataset.displayMode === 'dark' ? 'light' : 'dark';
    apply(mode);
    try { localStorage.setItem(key, mode); } catch { /* Still works on this page. */ }
  });
  window.addEventListener('pageshow', () => apply(readMode()));
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) apply(readMode());
  });
})();

(() => {
  document.querySelectorAll('[data-logo-scale]').forEach(input => {
    input.addEventListener('input', () => {
      const preview = input.closest('.partner-editor')?.querySelector('.admin-partner-logo img');
      const value = Number(input.value);
      if (preview && Number.isFinite(value) && value >= .5 && value <= 3) preview.style.setProperty('--logo-scale', value);
    });
  });
})();

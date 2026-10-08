(() => {
  const form = document.getElementById('palette-form');
  const preview = document.getElementById('palette-preview');
  if (!form || !preview) return;

  form.addEventListener('input', (event) => {
    const input = event.target;
    if (!input.matches('input[data-color-key]')) return;
    preview.style.setProperty(`--team-${input.dataset.colorKey}`, input.value);
    input.closest('.palette-control').querySelector('output').textContent = input.value;
  });
})();

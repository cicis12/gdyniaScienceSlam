document.querySelectorAll('[data-partner-contact]').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector('[data-contact-status]');
    if (button.disabled) return;
    button.disabled = true;
    form.setAttribute('aria-busy', 'true');
    status.textContent = 'Wysyłanie wiadomości…';
    try {
      const response = await fetch(form.action, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sprawdź pola formularza i spróbuj ponownie.');
      status.textContent = data.message;
      form.reset();
    } catch (error) {
      status.textContent = error instanceof TypeError ? 'Nie udało się połączyć z serwerem. Spróbuj ponownie.' : error.message;
    } finally {
      button.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });
});

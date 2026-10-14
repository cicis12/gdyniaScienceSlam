(() => {
  function initialize(form) {
    window.initializeSchoolAutocomplete?.(form);
    const phones = new Map();
    form.querySelectorAll('.phone').forEach(input => {
      if (window.intlTelInput) phones.set(input, window.intlTelInput(input, {
        initialCountry: 'pl', countryOrder: ['pl'], separateDialCode: true,
        loadUtils: () => import('https://cdn.jsdelivr.net/npm/intl-tel-input@26.0.6/build/js/utils.js'),
      }));
    });
    const syncSelects = () => form.querySelectorAll('select').forEach(select => { select.dataset.filled = String(select.value !== ''); });
    syncSelects();
    window.addEventListener('pageshow', syncSelects);
    form.addEventListener('reset', () => requestAnimationFrame(() => {
      syncSelects();
      phones.forEach(widget => widget.setNumber(''));
      form.querySelectorAll('.long-text').forEach(input => { input.style.height = ''; });
      form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
    }));
    form.querySelectorAll('.long-text').forEach(input => input.addEventListener('input', () => {
      input.style.height = 'auto'; input.style.height = `${input.scrollHeight}px`;
    }));
    let toastTimer;
    function toast(message, ok) {
      const container = document.getElementById('toast');
      const content = document.getElementById('toast-content');
      content.textContent = message;
      content.classList.remove('bg-green-600', 'bg-red-600');
      content.classList.add(ok ? 'bg-green-600' : 'bg-red-600');
      container.classList.remove('hidden');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => container.classList.add('hidden'), ok ? 6000 : 15000);
    }
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type=submit]');
      if (button.disabled) return;
      const data = new FormData(form);
      phones.forEach((widget, input) => data.set(input.name, input.value.trim() ? widget.getNumber() : ''));
      const answers = {};
      const uploads = new FormData();
      let hasFiles = false;
      let fileCount = 0, fileBytes = 0;
      for (const [name, value] of data.entries()) {
        if (value instanceof File) {
          if (value.name) {
            if (value.size > 100 * 1024 * 1024) {
              toast('Plik jest zbyt duży. Maksymalny rozmiar to 100 MB.', false);
              return;
            }
            fileCount++; fileBytes += value.size;
            uploads.append(`file:${name}`, value);
            hasFiles = true;
          }
        } else answers[name] = value;
      }
      if (fileCount > 3 || fileBytes > 110 * 1024 * 1024 - 256 * 1024) {
        toast('Możesz przesłać do 3 plików. Całe zgłoszenie musi zmieścić się w 110 MB.', false);
        return;
      }
      const payload = JSON.stringify({form_id: Number(form.dataset.formId), form_version_id: Number(form.dataset.versionId), answers});
      if (hasFiles) uploads.append('payload', payload);
      form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
      button.disabled = true;
      try {
        const response = await fetch('/api/forms/submit', {
          method: 'POST', headers: hasFiles ? {} : {'Content-Type': 'application/json'},
          body: hasFiles ? uploads : payload,
        });
        const result = await response.json().catch(() => ({}));
        if (response.ok) {
          toast('Formularz wysłany pomyślnie!', true); form.reset();
        } else {
          const messages = {
            404: 'Ten formularz nie jest już dostępny.',
            409: 'Formularz został zmieniony. Odśwież stronę i spróbuj ponownie.',
            413: 'Plik jest zbyt duży. Maksymalny rozmiar pliku to 100 MB, a całego zgłoszenia 110 MB.',
            415: 'Nieobsługiwany format formularza. Odśwież stronę i spróbuj ponownie.',
            503: 'Formularz jest chwilowo niedostępny. Spróbuj później lub skontaktuj się z organizatorem.',
            422: 'Sprawdź wymagane pola i poprawność wpisanych danych.',
            429: 'Zbyt wiele prób. Odczekaj chwilę i spróbuj ponownie.',
          };
          // Only our explicit public validation contract may supply a message.
          toast(result.code === 'invalid_answers' && typeof result.message === 'string'
            ? result.message : (messages[response.status] || 'Nie udało się zapisać formularza. Spróbuj ponownie za chwilę.'), false);
          if (result.code === 'invalid_answers' && Array.isArray(result.fields)) {
            result.fields.forEach(name => form.elements.namedItem(name)?.setAttribute?.('aria-invalid', 'true'));
            form.querySelector('[aria-invalid="true"]')?.focus();
          }
        }
      } catch {
        toast('Nie udało się połączyć z serwerem. Sprawdź połączenie internetowe i spróbuj ponownie.', false);
      } finally { button.disabled = false; }
    });
  }
  document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('form.public-form').forEach(initialize));
})();

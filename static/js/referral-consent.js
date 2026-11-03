(() => {
  const settings = document.getElementById('referral-session-config');
  if (!settings || window.self !== window.top) return;
  const config = JSON.parse(settings.textContent);
  const dialog = document.getElementById('referral-consent');
  if (!config.needs_popup || !dialog) return;
  const status = document.getElementById('referral-consent-status');
  const buttons = [...dialog.querySelectorAll('[data-referral-choice]')];
  let saving = false;
  function removeIdentifier() {
    const url = new URL(location.href);
    url.searchParams.delete('ref');
    history.replaceState(history.state, '', url);
    document.querySelectorAll('a[href]').forEach(link => {
      const target = new URL(link.href, location.href);
      if (target.origin === location.origin && target.searchParams.get('ref') === config.tracking.link_id) {
        target.searchParams.delete('ref'); link.href = target.href;
      }
    });
    config.tracking.link_id = null;
    settings.remove();
  }
  function startTracking() {
    if (!config.analytics_enabled || document.getElementById('interaction-analytics-script')) return;
    const data = document.createElement('script');
    data.type = 'application/json'; data.id = 'interaction-analytics-config';
    data.textContent = JSON.stringify({ ...config.tracking, consented: true });
    const script = document.createElement('script');
    script.id = 'interaction-analytics-script'; script.src = config.analytics_url;
    document.body.append(data, script);
  }
  async function choose(accepted) {
    if (saving) return;
    saving = true;
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = 'Zapisywanie wyboru…';
    const privacyOptOut = navigator.doNotTrack === '1' || navigator.globalPrivacyControl || new URL(location.href).searchParams.get('analytics') === 'off';
    accepted = accepted && !privacyOptOut;
    try {
      const response = await fetch('/api/referrals/decision', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted, link_id: config.tracking.link_id, revision: config.revision }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Nie udało się zapisać wyboru. Spróbuj ponownie.');
      if (!result.consented) removeIdentifier();
      dialog.close();
      if (result.tracking) startTracking();
    } catch (error) {
      status.textContent = error instanceof TypeError ? 'Nie udało się połączyć z serwerem. Spróbuj ponownie.' : error.message;
    } finally {
      saving = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  }
  buttons.forEach(button => button.addEventListener('click', () => choose(button.dataset.referralChoice === 'yes')));
  dialog.addEventListener('cancel', event => { event.preventDefault(); choose(false); });
  dialog.showModal();
})();

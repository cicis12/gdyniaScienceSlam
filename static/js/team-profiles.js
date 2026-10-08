(() => {
  const dialog = document.getElementById('team-profile');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const photo = dialog.querySelector('#team-profile-photo');
  const scrollArea = dialog.querySelector('.team-dialog-scroll');
  const closeButton = dialog.querySelector('.team-dialog-close');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const easing = 'cubic-bezier(.22, 1, .36, 1)';
  let source = null;
  let closing = false;
  let animations = [];

  function clearAnimations() {
    animations.forEach((animation) => animation.cancel());
    animations = [];
  }

  function animate(element, frames, options) {
    const animation = element.animate(frames, { easing, fill: 'both', ...options });
    animations.push(animation);
    return animation;
  }

  function clipToCard(card) {
    const rect = card.getBoundingClientRect();
    return `inset(${Math.max(0, rect.top)}px ${Math.max(0, innerWidth - rect.right)}px ${Math.max(0, innerHeight - rect.bottom)}px ${Math.max(0, rect.left)}px round 16px)`;
  }

  function imageTransform(from, to) {
    return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
  }

  function openProfile(card) {
    if (dialog.open) return;
    source = card;
    const sourcePhoto = card.querySelector('img');
    const imageRect = sourcePhoto.getBoundingClientRect();
    const startClip = clipToCard(card);
    photo.src = sourcePhoto.currentSrc || sourcePhoto.src;
    photo.alt = sourcePhoto.alt;
    dialog.querySelector('#team-profile-name').textContent = card.querySelector('.team-name').textContent;
    dialog.querySelector('#team-profile-position').textContent = card.querySelector('.team-position').textContent;
    dialog.querySelector('#team-profile-description').textContent = card.querySelector('.team-description').textContent;
    dialog.style.setProperty('--profile-color', getComputedStyle(card).backgroundColor);
    document.documentElement.classList.add('team-profile-open');
    dialog.showModal();
    scrollArea.scrollTop = 0;
    closeButton.focus({ preventScroll: true });

    if (!reducedMotion.matches && typeof dialog.animate === 'function') {
      animate(dialog, [{ clipPath: startClip }, { clipPath: 'inset(0px 0px 0px 0px round 0px)' }], { duration: 540 });
      animate(photo, [{ transform: imageTransform(imageRect, photo.getBoundingClientRect()) }, { transform: 'none' }], { duration: 540 });
      for (const element of dialog.querySelectorAll('.team-dialog-header, .team-dialog-copy')) {
        animate(element, [{ opacity: 0, transform: 'translateY(18px)' }, { opacity: 1, transform: 'none' }], { duration: 340, delay: 140 });
      }
    }
  }

  async function closeProfile() {
    if (!dialog.open || closing) return;
    closing = true;
    // Finish an interrupted opening so quick Escape/clicks still close cleanly.
    clearAnimations();
    if (!reducedMotion.matches && typeof dialog.animate === 'function' && source?.isConnected) {
      const targetPhoto = source.querySelector('img').getBoundingClientRect();
      animate(photo, [{ transform: 'none' }, { transform: imageTransform(targetPhoto, photo.getBoundingClientRect()) }], { duration: 360 });
      for (const element of dialog.querySelectorAll('.team-dialog-header, .team-dialog-copy')) {
        animate(element, [{ opacity: 1 }, { opacity: 0 }], { duration: 160 });
      }
      const closingAnimation = animate(dialog, [
        { clipPath: 'inset(0px 0px 0px 0px round 0px)' },
        { clipPath: clipToCard(source) },
      ], { duration: 360 });
      await closingAnimation.finished.catch(() => {});
    }
    dialog.close();
  }

  document.querySelectorAll('.team-grid .team-card summary').forEach((summary) => {
    summary.setAttribute('aria-haspopup', 'dialog');
    summary.setAttribute('aria-controls', dialog.id);
    summary.addEventListener('click', (event) => {
      event.preventDefault();
      openProfile(summary.closest('.team-card'));
    });
  });
  closeButton.addEventListener('click', closeProfile);
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    closeProfile();
  });
  dialog.addEventListener('close', () => {
    clearAnimations();
    document.documentElement.classList.remove('team-profile-open');
    source?.querySelector('summary').focus({ preventScroll: true });
    closing = false;
  });
})();

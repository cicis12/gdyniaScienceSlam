(() => {
  const photos = Array.from(document.querySelectorAll('.archive-photo'));
  const dialog = document.getElementById('gallery-lightbox');
  if (!photos.length || !dialog || typeof dialog.showModal !== 'function') return;
  const image = document.getElementById('gallery-full-image');
  const previous = document.getElementById('gallery-prev');
  const next = document.getElementById('gallery-next');
  const close = document.getElementById('gallery-close');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let index = 0;
  let trigger = null;
  let animation = null;

  function showPhoto(newIndex, direction = 1) {
    index = (newIndex + photos.length) % photos.length;
    const photo = photos[index];
    animation?.cancel();
    image.src = photo.href;
    image.alt = photo.dataset.caption;
    document.getElementById('gallery-caption').textContent = photo.dataset.caption;
    document.getElementById('gallery-year').textContent = `Gdynia Science Slam / ${photo.dataset.year}`;
    document.getElementById('gallery-counter').textContent = `${index + 1} / ${photos.length}`;
    previous.disabled = next.disabled = photos.length < 2;
    if (!reducedMotion.matches && typeof image.animate === 'function') {
      animation = image.animate([{ opacity: .2, transform: `translateX(${direction * 20}px)` }, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'ease-out' });
    }
    if (photos.length > 1) {
      const preload = new Image();
      preload.src = photos[(index + 1) % photos.length].href;
    }
  }

  photos.forEach((photo, number) => photo.addEventListener('click', (event) => {
    event.preventDefault();
    trigger = photo;
    document.documentElement.classList.add('gallery-open');
    showPhoto(number);
    dialog.showModal();
    close.focus({ preventScroll: true });
  }));
  previous.addEventListener('click', () => showPhoto(index - 1, -1));
  next.addEventListener('click', () => showPhoto(index + 1));
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      showPhoto(index + (event.key === 'ArrowLeft' ? -1 : 1), event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
  dialog.querySelector('.gallery-stage').addEventListener('click', (event) => {
    if (event.target !== image) dialog.close();
  });
  let touchStart = null;
  const stage = dialog.querySelector('.gallery-stage');
  stage.addEventListener('touchstart', (event) => {
    touchStart = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
  }, { passive: true });
  stage.addEventListener('touchend', (event) => {
    if (!touchStart) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) showPhoto(index + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1);
    touchStart = null;
  }, { passive: true });
  stage.addEventListener('touchcancel', () => { touchStart = null; });
  dialog.addEventListener('close', () => {
    animation?.cancel();
    document.documentElement.classList.remove('gallery-open');
    trigger?.focus({ preventScroll: true });
  });
})();

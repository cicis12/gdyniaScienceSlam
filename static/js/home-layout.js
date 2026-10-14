(() => {
  const root = document.documentElement;
  const nav = document.querySelector('.site-nav');
  const sections = [...document.querySelectorAll('.homepage-flow > .home-scroll-section')];
  if (!root.classList.contains('homepage-scroll-snap') || !nav) return;
  let frame;
  function fitSections() {
    frame = null;
    root.style.setProperty('--site-nav-height', `${nav.getBoundingClientRect().height}px`);
    // Restore the preferred padding before measuring the natural overflow.
    sections.forEach(section => section.style.removeProperty('padding-block'));
    const padding = sections.map(section => {
      const style = getComputedStyle(section);
      const preferred = parseFloat(style.paddingTop);
      const available = parseFloat(style.minHeight);
      const content = parseFloat(style.height) - preferred * 2;
      // Long content remains scrollable; content that fits gets one screen.
      return content > available ? Math.min(preferred, 16)
        : Math.max(0, Math.min(preferred, Math.floor((available - content) / 2)));
    });
    sections.forEach((section, index) => { section.style.paddingBlock = `${padding[index]}px`; });
  }
  const schedule = () => {
    if (frame == null) frame = requestAnimationFrame(fitSections);
  };
  new ResizeObserver(schedule).observe(nav);
  window.addEventListener('resize', schedule);
  window.addEventListener('pageshow', schedule);
  document.querySelectorAll('.homepage-flow img').forEach(img => img.addEventListener('load', schedule));
  document.fonts?.ready.then(schedule);
  schedule();
})();

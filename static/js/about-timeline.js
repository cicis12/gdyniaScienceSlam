(() => {
  const timeline = document.querySelector('[data-timeline]');
  if (!timeline) return;
  const stages = [...timeline.querySelectorAll('.timeline-stage')];
  const links = [...timeline.querySelectorAll('.timeline-nav a')];
  if (!stages.length) return;
  let active = -1;
  let scheduled = false;

  const select = (index) => {
    if (index === active) return;
    active = index;
    stages.forEach((stage, i) => stage.classList.toggle('is-active', i === index));
    links.forEach((link, i) => {
      if (i === index) link.setAttribute('aria-current', 'step');
      else link.removeAttribute('aria-current');
    });
  };
  const update = () => {
    scheduled = false;
    const navHeight = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--site-nav-height')) || 97;
    const center = Math.min(innerHeight * .65, (innerHeight + navHeight) / 2);
    let nearest = 0;
    let distance = Infinity;
    stages.forEach((stage, index) => {
      const bounds = stage.getBoundingClientRect();
      // Use distance from the section's visible range, so long descriptions stay active.
      const delta = center < bounds.top ? bounds.top - center : Math.max(0, center - bounds.bottom);
      if (delta < distance) { nearest = index; distance = delta; }
    });
    select(nearest);
    timeline.classList.add('timeline-ready');
  };
  const schedule = () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(update); }
  };
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule);
  addEventListener('pageshow', schedule);
  timeline.addEventListener('load', schedule, true);
  update();
})();

/* Shrink only overflowing copy, preserving the card/caption's allocated space. */
(() => {
  const selector = '.team-card .team-name, .team-card .team-position, .archive-photo-overlay > span:first-child, #gallery-caption';
  function fit(element) {
    if (!element.clientWidth || !element.clientHeight) return;
    element.style.fontSize = '';
    const original = parseFloat(getComputedStyle(element).fontSize);
    const minimum = element.closest('.team-card') ? 10 : Math.min(original, 12);
    let size = original;
    while (size > minimum && (element.scrollHeight > element.clientHeight + 1 || element.scrollWidth > element.clientWidth + 1)) {
      size = Math.max(minimum, size - .5);
      element.style.fontSize = `${size}px`;
    }
  }
  let scheduled = false;
  function refresh() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      document.querySelectorAll(selector).forEach(fit);
    });
  }
  const observer = new ResizeObserver(refresh);
  document.querySelectorAll(selector).forEach(element => {
    observer.observe(element);
    new MutationObserver(refresh).observe(element, {childList: true, subtree: true, characterData: true});
  });
  window.addEventListener('resize', refresh);
  document.fonts?.ready.then(refresh);
  refresh();
})();

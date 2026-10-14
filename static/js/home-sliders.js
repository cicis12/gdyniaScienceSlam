(() => {
  // Both carousels travel at the same speed, regardless of the number of items.
  const pixelsPerSecond = 40;
  const tracks = [...document.querySelectorAll('.homepage-flow .slider-track')];
  const update = track => {
    const width = track.firstElementChild?.offsetWidth || 0;
    if (width > 0) track.style.setProperty('--slider-duration', `${width / pixelsPerSecond}s`);
  };
  const observer = new ResizeObserver(entries => {
    entries.forEach(entry => update(entry.target.parentElement));
  });
  tracks.forEach(track => {
    if (track.firstElementChild) observer.observe(track.firstElementChild);
    update(track);
  });
  document.fonts?.ready.then(() => tracks.forEach(update));
})();

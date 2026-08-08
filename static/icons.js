// Single source of truth for inline SVG icons used across index.html,
// admin.html, and jobs.html - change the markup here once and every
// <... data-icon="name"> picks it up, instead of hunting down N copies.
// (Not using an external <svg><symbol>/<use> sprite: older Safari has a
// history of flaky support for referencing SVG symbols across documents,
// and this app has already hit more than one iOS-only rendering surprise -
// plain innerHTML injection has no such risk.)
const ICONS = {
  calendar:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
};

document.querySelectorAll("[data-icon]").forEach((el) => {
  const svg = ICONS[el.dataset.icon];
  if (svg) el.innerHTML = svg;
});

/** Small route-scoped reveal helper. Observes only elements that have not entered view. */
export function bindMotion(root) {
  if (!root) return;
  const page = root.firstElementChild;
  if (page) { page.classList.remove('motion-page-enter'); void page.offsetWidth; page.classList.add('motion-page-enter'); }
  const targets = root.querySelectorAll('section:not(.nera-hero-split), .nera-card, .nera-grid-3 > *, .nera-grid-2 > *');
  if (!('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries, currentObserver) => {
    entries.forEach((entry) => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); currentObserver.unobserve(entry.target); } });
  }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });
  targets.forEach((element) => {
    if (element.getBoundingClientRect().top < window.innerHeight * 0.92) { element.classList.add('is-visible'); return; }
    element.classList.add('motion-reveal'); observer.observe(element);
  });
}

(() => {
  const header = document.querySelector('.site-header');
  const nav = header?.querySelector('nav');
  if (!header || !nav) return;

  const toggle = header.querySelector('.nav-toggle') ?? document.createElement('button');
  if (!toggle.parentElement) {
    toggle.className = 'nav-toggle';
    toggle.type = 'button';
    toggle.setAttribute('aria-label', 'Open navigation');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '☰';
    header.append(toggle);
  }

  const close = () => {
    header.dataset.navOpen = 'false';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '☰';
  };
  toggle.addEventListener('click', () => {
    const open = header.dataset.navOpen !== 'true';
    header.dataset.navOpen = String(open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? '×' : '☰';
  });
  nav.addEventListener('click', (event) => {
    if (event.target.closest('a')) close();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });
  window.matchMedia('(min-width: 801px)').addEventListener('change', close);
})();

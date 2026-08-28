// 청정 블로그 — 모바일 내비게이션 토글 & 카테고리 필터

document.addEventListener('DOMContentLoaded', () => {
  const navToggle = document.querySelector('.nav-toggle');
  const mainNav = document.querySelector('.main-nav');
  if (navToggle && mainNav) {
    navToggle.addEventListener('click', () => {
      const isOpen = mainNav.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
    mainNav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => mainNav.classList.remove('open'));
    });
  }

  const filterButtons = document.querySelectorAll('.filter-tabs button');
  const postCards = document.querySelectorAll('.post-card');
  if (filterButtons.length && postCards.length) {
    filterButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        filterButtons.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        const category = btn.dataset.category;
        postCards.forEach((card) => {
          const show = category === 'all' || card.dataset.category === category;
          card.style.display = show ? '' : 'none';
        });
      });
    });
  }
});

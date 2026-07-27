/* Weight Streaming Website — Navigation & Interactivity */

// Active nav link highlight
document.addEventListener('DOMContentLoaded', () => {
  const current = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(link => {
    const href = link.getAttribute('href');
    if (href === current || (current === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });
});

// Copy code blocks
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('pre code').forEach(block => {
    const btn = document.createElement('button');
    btn.textContent = 'Copy';
    btn.className = 'copy-btn';
    btn.style.cssText = `
      position: absolute; top: 8px; right: 8px;
      background: var(--surface); border: 1px solid var(--border);
      color: var(--text-dim); padding: 4px 10px;
      border-radius: var(--radius-sm); cursor: pointer;
      font-size: 0.75rem; font-family: var(--font);
      transition: all var(--transition);
    `;
    btn.onclick = () => {
      navigator.clipboard.writeText(block.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 2000);
      });
    };
    block.parentElement.style.position = 'relative';
    block.parentElement.appendChild(btn);
  });
});

// Smooth scroll for anchor links
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const target = document.querySelector(link.getAttribute('href'));
      if (target) target.scrollIntoView({ behavior: 'smooth' });
    });
  });
});

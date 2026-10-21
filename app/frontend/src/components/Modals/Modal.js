/**
 * Generic Accessible Modal Controller
 */

export class Modal {
  static open(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
      el.style.display = 'flex';
      el.setAttribute('aria-hidden', 'false');
      const firstInput = el.querySelector('input, select, textarea, button');
      firstInput?.focus();
    }
  }

  static close(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
      el.style.display = 'none';
      el.setAttribute('aria-hidden', 'true');
    }
  }

  static initEscapeListener() {
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay').forEach((m) => {
          if (m.style.display === 'flex') {
            m.style.display = 'none';
          }
        });
      }
    });
  }
}

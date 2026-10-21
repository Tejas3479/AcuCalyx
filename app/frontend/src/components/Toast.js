/**
 * Clinical Toast Notification Component
 */

export function showToast(message, type = 'info', durationMs = 3500) {
  const toast = document.createElement('div');
  toast.className = `clinical-toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add('visible');
  });

  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, durationMs);
}

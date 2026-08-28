// ZoiKYC Interactive Frontend Helper Script
document.addEventListener('DOMContentLoaded', () => {
  // Preset Recharge Amount Selection
  const presetButtons = document.querySelectorAll('.btn-preset');
  const amountInput = document.getElementById('amount');

  if (presetButtons.length > 0 && amountInput) {
    presetButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        presetButtons.forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        amountInput.value = btn.getAttribute('data-amount');
      });
    });
  }

  // Auto-dismiss alert notifications after 8 seconds
  const alerts = document.querySelectorAll('.alert-auto-dismiss');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.opacity = '0';
      alert.style.transition = 'opacity 0.5s ease';
      setTimeout(() => alert.remove(), 500);
    }, 8000);
  });
});

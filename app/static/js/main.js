// ZoiKYC Interactive Frontend Helper Script
document.addEventListener('DOMContentLoaded', () => {
  // Mobile Sidebar Toggle Handling
  const mobileToggleBtn = document.getElementById('mobileMenuToggle');
  const sidebar = document.getElementById('appSidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');

  function openSidebar() {
    if (sidebar) sidebar.classList.add('sidebar-open');
    if (backdrop) backdrop.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove('sidebar-open');
    if (backdrop) backdrop.classList.remove('active');
    document.body.style.overflow = '';
  }

  if (mobileToggleBtn) {
    mobileToggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openSidebar();
    });
  }

  if (sidebarCloseBtn) {
    sidebarCloseBtn.addEventListener('click', closeSidebar);
  }

  if (backdrop) {
    backdrop.addEventListener('click', closeSidebar);
  }

  // Close sidebar on ESC key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
  });

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
        amountInput.dispatchEvent(new Event('input'));
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

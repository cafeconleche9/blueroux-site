// Theme switcher. localStorage can throw (private mode etc.), so always guard it.
(function () {
  var sel = document.getElementById('theme-select');
  if (!sel) return;
  sel.value = document.documentElement.dataset.theme || 'dark';
  sel.addEventListener('change', function () {
    document.documentElement.dataset.theme = sel.value;
    try { localStorage.setItem('br-theme', sel.value); } catch (e) {}
  });
})();

(function () {
  var BTN_ID = 'cl-resume-btn';

  function injectButton() {
    if (document.getElementById(BTN_ID)) return;

    var newChatBtn = document.getElementById('new-chat-button');
    if (!newChatBtn) return;

    var btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.title = '載入歷史對話';
    btn.className = newChatBtn.className;
    btn.setAttribute('type', 'button');
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="!size-6"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';

    btn.addEventListener('click', function () {
      // 選取 resume command（點 command button）
      var resumeCmd = document.getElementById('command-resume');
      if (!resumeCmd) return;
      resumeCmd.click();

      // 等 React 更新後再點 submit
      setTimeout(function () {
        var submitBtn = document.getElementById('chat-submit');
        if (submitBtn) submitBtn.click();
      }, 50);
    });

    newChatBtn.parentNode.insertBefore(btn, newChatBtn);
  }

  fetch('/api/config')
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      if (!cfg.enable_session_history) return;

      var observer = new MutationObserver(function () {
        injectButton();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      window.addEventListener('load', injectButton);
    })
    .catch(function () {
      // fetch 失敗時預設仍啟用（保持向後相容）
      var observer = new MutationObserver(function () {
        injectButton();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      window.addEventListener('load', injectButton);
    });
})();

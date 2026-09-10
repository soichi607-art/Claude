/* Web Share API flow (feature-detected at runtime; nothing is assumed).
   1) copy caption  2) share video via navigator.share({files})  3) user picks YouTube/TikTok  4) user publishes  5) back → record.
   Fallback when unsupported: download video + copy caption + open app manually. */
(function () {
  'use strict';
  var root = document.getElementById('share-root');
  if (!root) return;
  var videoUrl = root.getAttribute('data-video');
  var fileName = root.getAttribute('data-filename');
  var status = document.getElementById('share-status');
  var btn = document.getElementById('share-btn');
  var fb = document.getElementById('share-fallback');
  var capEl = document.getElementById('caption-text');
  function say(t, cls) { status.textContent = t; status.className = 'flash ' + (cls || 'info'); }
  function copyCaption() {
    var text = capEl ? capEl.value : '';
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return Promise.reject(new Error('clipboard unsupported'));
  }
  var supportsFiles = !!(navigator.share && navigator.canShare);
  var supportText = document.getElementById('share-support');
  if (supportText) {
    supportText.textContent = navigator.share ? (navigator.canShare ? 'このブラウザは Web Share API に対応しています（ファイル共有可否は実行時に確認します）' : 'navigator.share はありますが canShare がありません → フォールバック') : 'このブラウザは Web Share API 非対応 → フォールバック手順を使ってください';
  }
  if (!supportsFiles) { btn.hidden = true; fb.hidden = false; return; }
  btn.addEventListener('click', function () {
    btn.disabled = true;
    say('動画を読み込み中…');
    copyCaption().then(function () { say('投稿文をコピーしました。動画を準備中…'); }).catch(function () {});
    fetch(videoUrl, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    }).then(function (blob) {
      var file = new File([blob], fileName, { type: 'video/mp4' });
      var data = { files: [file], title: root.getAttribute('data-title') || '' };
      if (!navigator.canShare(data)) {
        say('この端末はファイル共有に非対応です。フォールバック手順を使ってください。', 'error');
        fb.hidden = false; btn.disabled = false; return;
      }
      return navigator.share(data).then(function () {
        say('共有シートに渡しました。YouTube / TikTok アプリで公開後、下の「投稿済み」を押してください。', 'ok');
        var mark = document.getElementById('mark-shared'); if (mark) mark.submit();
      });
    }).catch(function (e) {
      if (e && e.name === 'AbortError') { say('共有をキャンセルしました。'); }
      else { say('共有に失敗: ' + (e && e.message ? e.message : e) + ' → フォールバック手順へ', 'error'); fb.hidden = false; }
    }).then(function () { btn.disabled = false; });
  });
})();

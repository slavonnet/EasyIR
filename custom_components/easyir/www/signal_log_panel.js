/** Minimal EasyIR sidebar panel: embeds the Signal Log HTML tool (session cookies). */
(function () {
  var frame = document.createElement("iframe");
  frame.setAttribute("src", "/api/easyir/signal_log/page");
  frame.setAttribute(
    "style",
    "width:100%;height:100%;min-height:70vh;border:0;display:block;"
  );
  document.body.appendChild(frame);
})();

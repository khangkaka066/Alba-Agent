/** A quiet, text-free launch screen. The existing mark is a packaged local asset. */
export function startupPage(mark: string, vietnamese: boolean): string {
  const label = vietnamese ? "Alba Agent đang khởi động" : "Alba Agent is starting";
  const source = `data:image/svg+xml;base64,${Buffer.from(mark).toString("base64")}`;
  return `<!doctype html><html lang="${vietnamese ? "vi" : "en"}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>Alba Agent</title><style>
:root{color-scheme:dark;background:#090a0f;color:#f4f4f6}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;-webkit-app-region:drag}
.launch{display:grid;justify-items:center;gap:28px;animation:arrive .5s ease-out both}
.mark{width:80px;height:80px;display:block;animation:breathe 2.8s ease-in-out infinite}
.activity{display:flex;align-items:center;gap:7px;height:8px}
.activity i{width:4px;height:4px;border-radius:50%;background:currentColor;opacity:.24;animation:signal 1.8s ease-in-out infinite}
.activity i:nth-child(2){animation-delay:.2s}.activity i:nth-child(3){animation-delay:.4s}
@keyframes arrive{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes breathe{0%,100%{opacity:.65;transform:translateY(2px)}50%{opacity:1;transform:translateY(-2px)}}
@keyframes signal{0%,70%,100%{opacity:.24;transform:scale(1)}35%{opacity:.85;transform:scale(1.3)}}
@media(prefers-reduced-motion:reduce){.launch,.mark,.activity i{animation:none}.mark{opacity:1}.activity i{opacity:.5}}
</style></head><body><main class="launch" role="status" aria-label="${label}" aria-busy="true">
<img class="mark" src="${source}" alt="" draggable="false"><span class="activity" aria-hidden="true"><i></i><i></i><i></i></span>
</main></body></html>`;
}

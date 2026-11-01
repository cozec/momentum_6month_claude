// Turn the live dashboard into a self-contained static page (report.html).
// Evaluated in the loaded dashboard by scripts/build_report.py; returns the
// page HTML. Charts become PNG images, app scripts are dropped, and a small
// inline script keeps the view tabs working.
async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 600; i++) {
    if (document.querySelectorAll('[data-el="chart-container"] canvas').length >= 2 &&
        (document.getElementById('last-updated')?.innerText || '').match(/\d/) &&
        document.querySelector('#strategy-A [data-el="stats-grid"]').innerText.match(/CAGR/i)) break;
    await sleep(500);
  }
  await sleep(1000);
  const dpr = window.devicePixelRatio || 1;
  for (const s of ['A']) {
    // Charts only lay out while their tab is visible.
    document.querySelector(`[data-view-tab="${s}:top3"]`).click();
    await sleep(800);
    const cont = document.querySelector(`#strategy-${s} [data-el="chart-container"]`);
    const r0 = cont.getBoundingClientRect();
    const W = Math.round(r0.width), H = Math.round(r0.height);
    const oc = document.createElement('canvas');
    oc.width = Math.round(W * dpr); oc.height = Math.round(H * dpr);
    const ctx = oc.getContext('2d'); ctx.scale(dpr, dpr);
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, W, H);
    cont.querySelectorAll('canvas').forEach(cv => {
      const r = cv.getBoundingClientRect();
      try { ctx.drawImage(cv, r.left - r0.left, r.top - r0.top, r.width, r.height); } catch (e) {}
    });
    const img = document.createElement('img');
    img.src = oc.toDataURL('image/png');
    img.style.width = '100%'; img.style.height = 'auto';
    cont.replaceChildren(img);
    cont.classList.remove('h-[768px]');
  }
  document.querySelector('[data-view-tab="A:top3"]').click();
  await sleep(300);
  document.getElementById('refresh-btn')?.remove();
  document.querySelectorAll('[data-el="chart-tabs"]').forEach(t => t.remove());
  document.querySelectorAll('script').forEach(s => {
    const src = s.getAttribute('src') || '';
    if (src.includes('app.js') || src.includes('lightweight-charts')) s.remove();
  });
  const tabJs = document.createElement('script');
  tabJs.textContent = `
const TAB_ON='bg-slate-900 text-white border-slate-900',TAB_OFF='bg-white text-slate-700 border-slate-200 hover:bg-slate-100';
function applyView(v){const[s,m]=v.split(':');
document.querySelectorAll('.strategy').forEach(r=>{r.classList.toggle('view-hidden',r.id!=='strategy-'+s);
r.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('view-hidden',!el.dataset.view.split(' ').includes(m)));});
document.querySelectorAll('[data-view-tab]').forEach(b=>{const on=b.dataset.viewTab===v;
b.className='flex flex-col items-start rounded-xl border px-4 py-2.5 text-left transition '+(on?TAB_ON:TAB_OFF);
b.querySelector('small').className='text-[11px] '+(on?'text-slate-300':'text-slate-500');b.setAttribute('aria-selected',String(on));});
history.replaceState(null,'','#'+s.toLowerCase()+'-'+m);}
document.querySelectorAll('[data-view-tab]').forEach(b=>b.addEventListener('click',()=>applyView(b.dataset.viewTab)));
const h=location.hash.match(/^#(a)-(top3|top20)$/);applyView(h?h[1].toUpperCase()+':'+h[2]:'A:top3');`;
  document.body.appendChild(tabJs);
  document.title = 'Nasdaq-100 Momentum · Static Report';
  const cap = (document.getElementById('last-updated')?.innerText || '').replace(/\s+/g, ' ').trim();
  const banner = document.createElement('div');
  banner.setAttribute('style', 'margin-bottom:1.25rem;padding:.6rem .9rem;border:1px solid #e2e8f0;border-radius:.6rem;background:#f8fafc;color:#475569;font-size:12px;');
  banner.innerHTML = '\u{1F4CC} Static snapshot of the live dashboard · ' + cap +
    ' · charts are point-in-time images; the interactive version runs locally via <code>python run_webapp.py</code>.';
  const wrap = document.querySelector('.max-w-7xl');
  wrap.insertBefore(banner, wrap.firstChild);
  return '<!doctype html>\n' + document.documentElement.outerHTML;
}

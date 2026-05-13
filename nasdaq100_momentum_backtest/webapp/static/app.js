/* Nasdaq-100 Momentum picks — frontend.
 * Pulls /api/picks on load, on the Refresh button, and on tab focus.
 * Adds ?refresh=1 when the user clicks Refresh so the backend re-downloads
 * the latest yfinance data instead of trusting the cache.
 */

// Tailwind-ish 500 shades, stable per ticker via hash.
const ACCENT_PALETTE = [
  '#6366F1', '#10B981', '#F59E0B', '#EC4899', '#06B6D4',
  '#8B5CF6', '#EF4444', '#84CC16', '#0EA5E9', '#F97316',
  '#14B8A6', '#A855F7', '#22C55E', '#E11D48', '#3B82F6',
  '#EAB308', '#D946EF', '#0891B2', '#65A30D', '#DB2777',
];

function tickerColor(ticker) {
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = (h * 31 + ticker.charCodeAt(i)) >>> 0;
  return ACCENT_PALETTE[h % ACCENT_PALETTE.length];
}

function fmtPct(x, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const sign = x >= 0 ? '+' : '';
  return `${sign}${(x * 100).toFixed(digits)}%`;
}

function fmtPctMulti(x, digits = 0) {
  // For total_return where values are already in fraction form like 369.x
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return `${(x * 100).toFixed(digits)}%`;
}

function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}

function fmtMonthLong(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

function fmtDay(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function bgFromReturn(ret, maxAbs) {
  if (ret === null || ret === undefined) return '#FFFFFF';
  const intensity = Math.min(1, Math.pow(Math.abs(ret) / Math.max(maxAbs, 1e-9), 0.6));
  // Mint #D1FADF for positive, rose #FEE2E2 for negative.
  const pos = [217, 250, 219];
  const neg = [254, 226, 226];
  const neutral = [248, 250, 252];
  const target = ret >= 0 ? pos : neg;
  const c = neutral.map((n, i) => Math.round(n + (target[i] - n) * intensity));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function pickCard(pick, opts = {}) {
  const { isOpen = false, maxAbs = 0.5, compact = false } = opts;
  const color = tickerColor(pick.ticker);
  const bg = bgFromReturn(pick.stock_return, maxAbs);
  const sign = pick.stock_return >= 0;
  const retColor = sign ? 'text-emerald-700' : 'text-red-700';
  const border = isOpen ? 'border-2 border-dashed border-slate-400' : 'border border-slate-200';

  if (compact) {
    // Slim single-line layout: ticker on the left, return on the right.
    const mtdSuffix = isOpen
      ? `<span class="ml-1 text-[9px] tracking-wider text-slate-400 uppercase">mtd</span>`
      : '';
    return `
      <div class="card rounded-lg ${border} bg-white overflow-hidden flex items-stretch">
        <div class="w-1" style="background:${color}"></div>
        <div class="flex-1 flex items-center justify-between px-2.5 py-1.5" style="background:${bg}">
          <div class="text-sm font-bold text-slate-900 leading-tight">${pick.ticker}</div>
          <div class="text-sm font-semibold ${retColor} leading-tight">
            ${fmtPct(pick.stock_return)}${mtdSuffix}
          </div>
        </div>
      </div>
    `;
  }

  // Full-size card (open holdings).
  const mtdBadge = isOpen
    ? `<span class="inline-block mt-2 text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">MTD</span>`
    : '';
  return `
    <div class="card rounded-xl ${border} bg-white overflow-hidden">
      <div class="accent-stripe" style="background:${color}"></div>
      <div class="p-5" style="background:${bg}">
        <div class="flex items-center justify-between">
          <div class="text-3xl font-bold text-slate-900">${pick.ticker}</div>
          <div class="text-[10px] text-slate-400 font-medium">#${pick.rank}</div>
        </div>
        <div class="mt-1 text-lg font-semibold ${retColor}">
          ${fmtPct(pick.stock_return)}
        </div>
        ${mtdBadge}
      </div>
    </div>
  `;
}

function renderOpen(data) {
  const grid = document.getElementById('open-grid');
  const label = document.getElementById('open-entry-label');
  const mtdLabel = document.getElementById('open-portfolio-mtd');
  if (!data.open || data.open.length === 0) {
    grid.innerHTML = `<div class="col-span-full p-8 text-center text-slate-500 italic">
      No open rebalance — the latest holding period has already closed. Refresh after market data updates.
    </div>`;
    label.textContent = '';
    mtdLabel.textContent = '';
    return;
  }
  const meta = data.open_meta || {};
  label.innerHTML = `entry ${fmtDay(meta.entry_date)} · MTD through ${fmtDay(meta.as_of)}`;
  const maxAbs = Math.max(...data.open.map(p => Math.abs(p.stock_return || 0)), 0.1);
  grid.innerHTML = data.open
    .map(p => pickCard(p, { isOpen: true, maxAbs }))
    .join('');
  if (meta.mtd_portfolio_return !== undefined && meta.mtd_portfolio_return !== null) {
    const v = meta.mtd_portfolio_return;
    const sign = v >= 0 ? 'text-emerald-700' : 'text-red-700';
    mtdLabel.innerHTML =
      `Equal-weight portfolio MTD: <span class="font-semibold ${sign}">${fmtPct(v)}</span>`;
  }
}

function renderStats(data) {
  const s = data.stats || {};
  const strat = s.strategy || {};
  const qqq = s.qqq || {};
  const card = (label, value, sub) => `
    <div class="rounded-xl bg-white border border-slate-200 p-4">
      <div class="text-xs font-medium text-slate-500 uppercase tracking-wider">${label}</div>
      <div class="text-2xl font-bold text-slate-900 mt-1">${value}</div>
      ${sub ? `<div class="text-xs text-slate-500 mt-1">${sub}</div>` : ''}
    </div>
  `;
  const grid = document.getElementById('stats-grid');
  grid.innerHTML = [
    card('CAGR',          fmtPct(strat.cagr),         `QQQ ${fmtPct(qqq.cagr)}`),
    card('Sharpe',        (strat.sharpe ?? 0).toFixed(2), '(monthly, annualized)'),
    card('Max drawdown',  fmtPct(strat.max_drawdown), `QQQ ${fmtPct(qqq.max_drawdown)}`),
    card('Win vs QQQ',    fmtPct(strat.win_rate_vs_qqq), 'of months beat QQQ'),
  ].join('');
}

function renderHistory(data) {
  const completed = data.completed || [];
  const list = document.getElementById('history-list');
  if (!completed.length) {
    list.innerHTML =
      `<div class="text-slate-500 italic p-6">No completed rebalances yet.</div>`;
    return;
  }
  // Group by date → array of picks (sorted by rank).
  const byDate = new Map();
  for (const p of completed) {
    if (!byDate.has(p.date)) byDate.set(p.date, []);
    byDate.get(p.date).push(p);
  }
  const dates = [...byDate.keys()].sort().reverse();   // newest first
  document.getElementById('history-count').textContent = dates.length;

  const maxAbs = Math.max(
    ...completed.map(p => Math.abs(p.stock_return || 0)), 0.1,
  );

  list.innerHTML = dates.map(date => {
    const picks = byDate.get(date).sort((a, b) => a.rank - b.rank);
    const portfolioRet = picks.reduce((s, p) => s + (p.stock_return || 0), 0) / picks.length;
    const portfolioColor = portfolioRet >= 0 ? 'text-emerald-700' : 'text-red-700';
    return `
      <div class="rounded-lg bg-white border border-slate-200 px-3 py-2 flex items-center gap-3">
        <div class="w-28 flex-shrink-0 flex items-baseline gap-2">
          <div class="text-xs font-semibold text-slate-700 leading-tight">${fmtDate(date)}</div>
          <div class="text-xs font-bold ${portfolioColor} leading-tight">${fmtPct(portfolioRet)}</div>
        </div>
        <div class="grid grid-cols-3 gap-2 flex-1">
          ${picks.map(p => pickCard(p, { compact: true, maxAbs })).join('')}
        </div>
      </div>
    `;
  }).join('');

  // Window cumulative label.
  const w = data.window || {};
  const cumStratColor = (w.cum_strategy ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-700';
  document.getElementById('window-cum').innerHTML =
    `Strategy <span class="font-semibold ${cumStratColor}">${fmtPct(w.cum_strategy, 1)}</span>
     · QQQ <span class="font-medium text-slate-700">${fmtPct(w.cum_qqq, 1)}</span>`;
}

function renderUpdated(data) {
  const el = document.getElementById('last-updated');
  const dt = new Date(data.computed_at);
  el.innerHTML = `
    <div>updated ${dt.toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}</div>
    <div class="text-[10px] text-slate-400">${data.took_seconds}s · as of ${fmtDay(data.as_of)}</div>
  `;
}

async function load({ refresh = false } = {}) {
  const refreshBtn = document.getElementById('refresh-btn');
  const refreshLabel = document.getElementById('refresh-label');
  const refreshIcon = document.getElementById('refresh-icon');
  const err = document.getElementById('error');
  err.classList.add('hidden');
  refreshBtn.disabled = true;
  refreshLabel.textContent = refresh ? 'Downloading…' : 'Loading…';
  refreshIcon.classList.add('animate-spin');

  try {
    const url = '/api/picks' + (refresh ? '?refresh=1' : '');
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderOpen(data);
    renderStats(data);
    renderHistory(data);
    renderUpdated(data);
  } catch (e) {
    err.textContent = `Failed to load picks: ${e.message}. Check that the server is running and Yahoo Finance is reachable.`;
    err.classList.remove('hidden');
    document.getElementById('last-updated').innerHTML = `<div class="text-red-600">load failed</div>`;
  } finally {
    refreshBtn.disabled = false;
    refreshLabel.textContent = 'Refresh';
    refreshIcon.classList.remove('animate-spin');
  }
}

document.getElementById('refresh-btn').addEventListener('click', () => load({ refresh: true }));

// First load uses the cache (fast). Manual refresh re-downloads.
load({ refresh: false });

// Re-poll if tab regains focus after >60 s.
let lastLoaded = Date.now();
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && Date.now() - lastLoaded > 60_000) {
    lastLoaded = Date.now();
    load({ refresh: false });
  }
});

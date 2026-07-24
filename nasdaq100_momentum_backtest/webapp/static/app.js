/* Nasdaq-100 Momentum picks — frontend.
 * Renders TWO strategies side-by-side on the page:
 *   A: L=6m / P=1m  (baseline)
 *   B: L=3m / P=2m  (grid-search winner)
 * Both call /api/picks with the appropriate query params. Refresh button
 * adds ?refresh=1 to both calls so the backend re-downloads fresh data.
 */

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

function fmtPrice(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return x.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}

function fmtDay(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function bgFromReturn(ret, maxAbs) {
  if (ret === null || ret === undefined) return '#FFFFFF';
  const intensity = Math.min(1, Math.pow(Math.abs(ret) / Math.max(maxAbs, 1e-9), 0.6));
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

  const mtdBadge = isOpen
    ? `<span class="inline-block mt-2 text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">MTD</span>`
    : '';
  // Current holdings: show the first-of-month entry price and the latest price
  // beside the MTD return.
  const priceBlock = (isOpen && pick.entry_price != null && pick.latest_price != null)
    ? `<div class="text-[11px] text-slate-500 leading-tight text-right">
         <div><span class="text-slate-400">entry</span> $${fmtPrice(pick.entry_price)}</div>
         <div><span class="text-slate-400">current</span> $${fmtPrice(pick.latest_price)}</div>
       </div>`
    : '';
  return `
    <div class="card rounded-xl ${border} bg-white overflow-hidden">
      <div class="accent-stripe" style="background:${color}"></div>
      <div class="p-5" style="background:${bg}">
        <div class="flex items-center justify-between">
          <div class="text-3xl font-bold text-slate-900">${pick.ticker}</div>
          <div class="text-[10px] text-slate-400 font-medium">#${pick.rank}</div>
        </div>
        <div class="mt-1 flex items-end justify-between gap-2">
          <div class="text-lg font-semibold ${retColor}">
            ${fmtPct(pick.stock_return)}
          </div>
          ${priceBlock}
        </div>
        ${mtdBadge}
      </div>
    </div>
  `;
}

function renderNext(root, data) {
  const section = root.querySelector('.strategy-next');
  if (!section) return;
  const grid = section.querySelector('[data-el="next-grid"]');
  const label = section.querySelector('[data-el="next-entry-label"]');
  const note = section.querySelector('[data-el="next-note"]');
  const picks = data.next || [];
  const meta = data.next_meta || {};

  if (!picks.length) {
    section.classList.add('hidden');
    grid.innerHTML = '';
    label.textContent = '';
    if (note) note.textContent = '';
    return;
  }

  section.classList.remove('hidden');
  label.innerHTML = `signal locked through ${fmtDay(meta.signal_locked_as_of)} · planned entry ${fmtDay(meta.planned_entry_date)}`;
  // Synthesize "preview" cards — no return colouring (return is 0), just
  // ticker accent stripe so they read as "upcoming" not "performing".
  grid.innerHTML = picks.map(p => {
    const color = tickerColor(p.ticker);
    const priceEst = p.entry_price_estimate;
    const priceLine = priceEst != null
      ? `est. entry ≈ $${priceEst.toFixed(2)}`
      : '';
    return `
      <div class="card rounded-xl border-2 border-dashed border-indigo-300 bg-indigo-50 overflow-hidden">
        <div class="accent-stripe" style="background:${color}"></div>
        <div class="p-5">
          <div class="flex items-center justify-between">
            <div class="text-3xl font-bold text-slate-900">${p.ticker}</div>
            <div class="text-[10px] text-slate-500 font-medium">#${p.rank} · NEXT</div>
          </div>
          <div class="mt-1 text-sm text-indigo-700 font-medium">
            ${priceLine}
          </div>
        </div>
      </div>
    `;
  }).join('');
  if (note) {
    note.innerHTML = `Signal is determined by the last close before ${fmtDay(meta.planned_entry_date)}. Place an MOC order to match the backtest's entry assumption.`;
  }
}


function renderOpen(root, data) {
  const grid = root.querySelector('[data-el="open-grid"]');
  const label = root.querySelector('[data-el="open-entry-label"]');
  const mtdLabel = root.querySelector('[data-el="open-portfolio-mtd"]');
  if (!data.open || data.open.length === 0) {
    grid.innerHTML = `<div class="col-span-full p-6 text-center text-slate-500 italic">
      No open rebalance — the latest holding period has already closed.
    </div>`;
    label.textContent = '';
    mtdLabel.textContent = '';
    return;
  }
  const meta = data.open_meta || {};
  label.innerHTML = `entry ${fmtDay(meta.entry_date)} · MTD through ${fmtDay(meta.as_of)}`;
  const maxAbs = Math.max(...data.open.map(p => Math.abs(p.stock_return || 0)), 0.1);
  grid.innerHTML = data.open.map(p => pickCard(p, { isOpen: true, maxAbs })).join('');
  if (meta.mtd_portfolio_return !== undefined && meta.mtd_portfolio_return !== null) {
    const v = meta.mtd_portfolio_return;
    const sign = v >= 0 ? 'text-emerald-700' : 'text-red-700';
    mtdLabel.innerHTML =
      `Equal-weight portfolio MTD: <span class="font-semibold ${sign}">${fmtPct(v)}</span>`;
  }
}

// Cache of {strategyId -> {chart, series, activeTicker, abortController}}.
const CHART_STATE = new WeakMap();

async function loadCandles(ticker, signal) {
  const resp = await fetch(`/api/ohlc?ticker=${encodeURIComponent(ticker)}&months=6`, {
    cache: 'no-store',
    signal,
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} from /api/ohlc`);
  const json = await resp.json();
  return (json.candles || [])
    .filter(c => c.open != null && c.high != null && c.low != null && c.close != null)
    .map(c => ({ time: c.date, open: c.open, high: c.high, low: c.low, close: c.close }));
}

function ensureChart(root) {
  let state = CHART_STATE.get(root);
  if (state && state.chart) return state;
  const container = root.querySelector('[data-el="chart-container"]');
  if (!container || !window.LightweightCharts) return null;
  container.style.position = 'relative';
  const chart = window.LightweightCharts.createChart(container, {
    layout: { background: { color: '#FFFFFF' }, textColor: '#475569', fontFamily: 'Inter, system-ui, sans-serif' },
    grid: { vertLines: { color: '#F1F5F9' }, horzLines: { color: '#F1F5F9' } },
    rightPriceScale: { borderColor: '#E2E8F0' },
    timeScale: { borderColor: '#E2E8F0', timeVisible: false, secondsVisible: false },
    crosshair: { mode: window.LightweightCharts.CrosshairMode.Normal },
    autoSize: true,
  });
  const series = chart.addCandlestickSeries({
    upColor: '#10B981', downColor: '#EF4444',
    borderUpColor: '#10B981', borderDownColor: '#EF4444',
    wickUpColor: '#10B981', wickDownColor: '#EF4444',
  });

  // Overlay for the vertical "entry" line — positioned in CSS px via
  // chart.timeScale().timeToCoordinate() and refreshed on pan/zoom/resize.
  const overlay = document.createElement('div');
  overlay.dataset.el = 'entry-line';
  overlay.style.cssText =
    'position:absolute;top:0;width:2px;background:#6366F1;pointer-events:none;' +
    'display:none;z-index:2;box-shadow:0 0 0 1px rgba(255,255,255,0.6);';
  const label = document.createElement('div');
  label.dataset.el = 'entry-label';
  label.style.cssText =
    'position:absolute;top:4px;left:6px;font:600 10px Inter,system-ui,sans-serif;' +
    'color:#fff;background:#6366F1;padding:2px 6px;border-radius:4px;' +
    'white-space:nowrap;letter-spacing:0.04em;text-transform:uppercase;';
  overlay.appendChild(label);
  container.appendChild(overlay);

  state = { chart, series, activeTicker: null, entryDate: null, abortController: null };
  CHART_STATE.set(root, state);

  const reposition = () => positionEntryLine(root);
  chart.timeScale().subscribeVisibleTimeRangeChange(reposition);
  if (window.ResizeObserver) new ResizeObserver(reposition).observe(container);
  return state;
}

function positionEntryLine(root) {
  const state = CHART_STATE.get(root);
  if (!state) return;
  const container = root.querySelector('[data-el="chart-container"]');
  const overlay = container && container.querySelector('[data-el="entry-line"]');
  if (!overlay) return;
  const entry = state.entryDate;
  if (!entry) { overlay.style.display = 'none'; return; }

  // Snap forward to the first trading day if entry falls on a weekend/holiday.
  const ts = state.chart.timeScale();
  let coord = ts.timeToCoordinate(entry);
  if (coord == null) {
    const d = new Date(entry + 'T00:00');
    for (let i = 1; i <= 7 && coord == null; i++) {
      d.setDate(d.getDate() + 1);
      coord = ts.timeToCoordinate(d.toISOString().slice(0, 10));
    }
  }
  if (coord == null) { overlay.style.display = 'none'; return; }

  // Leave room for the time axis at the bottom (~28 px in default theme).
  const timeAxisPx = 28;
  overlay.style.display = 'block';
  overlay.style.left = `${Math.round(coord)}px`;
  overlay.style.height = `${Math.max(0, container.clientHeight - timeAxisPx)}px`;
  const label = overlay.querySelector('[data-el="entry-label"]');
  if (label) {
    const dt = new Date(entry + 'T00:00');
    label.textContent =
      `Entry ${dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
  }
}

async function loadChartFor(root, ticker, entryDate) {
  const state = ensureChart(root);
  if (!state) return;
  const status = root.querySelector('[data-el="chart-status"]');
  if (state.abortController) state.abortController.abort();
  state.abortController = new AbortController();
  state.activeTicker = ticker;
  if (entryDate !== undefined) state.entryDate = entryDate || null;
  status.textContent = `loading ${ticker}…`;
  try {
    const data = await loadCandles(ticker, state.abortController.signal);
    if (state.activeTicker !== ticker) return; // a newer click superseded us
    if (!data.length) {
      status.textContent = `no price data for ${ticker}`;
      state.series.setData([]);
      positionEntryLine(root);
      return;
    }
    state.series.setData(data);
    state.chart.timeScale().fitContent();
    positionEntryLine(root);
    const first = data[0], last = data[data.length - 1];
    const pct = (last.close / first.open - 1);
    const sign = pct >= 0 ? '+' : '';
    status.textContent = `${ticker} · ${first.time} → ${last.time} · ${sign}${(pct * 100).toFixed(1)}% over window`;
  } catch (e) {
    if (e.name === 'AbortError') return;
    status.textContent = `failed to load ${ticker}: ${e.message}`;
  }
}

function renderChart(root, data) {
  const section = root.querySelector('.strategy-chart');
  if (!section) return;
  const tabsEl = root.querySelector('[data-el="chart-tabs"]');
  const open = data.open || [];
  if (!open.length) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  const state = ensureChart(root);
  const tickers = open.map(p => p.ticker);
  const active = (state && tickers.includes(state.activeTicker)) ? state.activeTicker : tickers[0];
  const entryDate = (data.open_meta && data.open_meta.entry_date) || (open[0] && open[0].date) || null;

  tabsEl.innerHTML = tickers.map(t => {
    const isActive = t === active;
    const cls = isActive
      ? 'bg-slate-900 text-white'
      : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200';
    return `<button type="button" data-chart-ticker="${t}"
      class="px-2.5 py-1 rounded-md text-xs font-semibold tracking-wide ${cls}">${t}</button>`;
  }).join('');

  tabsEl.querySelectorAll('button[data-chart-ticker]').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.chartTicker;
      const s = ensureChart(root);
      if (s) s.activeTicker = t;
      loadChartFor(root, t, entryDate);
      // Rebuild styling now that activeTicker has been updated.
      tabsEl.querySelectorAll('button[data-chart-ticker]').forEach(b => {
        const isActive = b.dataset.chartTicker === t;
        b.className = `px-2.5 py-1 rounded-md text-xs font-semibold tracking-wide ${
          isActive ? 'bg-slate-900 text-white'
                   : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
        }`;
      });
    });
  });

  // Only kick off a fetch when the active ticker actually changes (e.g. on
  // the first render or when the open holdings rotate to a new set).
  if (!state || state.activeTicker !== active || state.entryDate !== entryDate) {
    if (state) state.activeTicker = active;
    loadChartFor(root, active, entryDate);
  }
}

function renderStats(root, data) {
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
  const grid = root.querySelector('[data-el="stats-grid"]');
  grid.innerHTML = [
    card('CAGR',          fmtPct(strat.cagr),         `QQQ ${fmtPct(qqq.cagr)}`),
    card('Sharpe',        (strat.sharpe ?? 0).toFixed(2), '(annualized)'),
    card('Max drawdown',  fmtPct(strat.max_drawdown), `QQQ ${fmtPct(qqq.max_drawdown)}`),
    card('Win vs QQQ',    fmtPct(strat.win_rate_vs_qqq), 'of rebalances beat QQQ'),
  ].join('');
}

function renderHistory(root, data) {
  const list = root.querySelector('[data-el="history-list"]');
  const completed = data.completed || [];
  if (!completed.length) {
    list.innerHTML = `<div class="text-slate-500 italic p-6">No completed rebalances yet.</div>`;
    return;
  }
  const byDate = new Map();
  for (const p of completed) {
    if (!byDate.has(p.date)) byDate.set(p.date, []);
    byDate.get(p.date).push(p);
  }
  const dates = [...byDate.keys()].sort().reverse();
  root.querySelector('[data-el="history-count"]').textContent = dates.length;

  const maxAbs = Math.max(...completed.map(p => Math.abs(p.stock_return || 0)), 0.1);

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

  const w = data.window || {};
  const cumStratColor = (w.cum_strategy ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-700';
  root.querySelector('[data-el="window-cum"]').innerHTML =
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
    const strategyEls = Array.from(document.querySelectorAll('.strategy'));
    // Build configs query like "6-1,3-2" from the DOM.
    const configs = strategyEls
      .map(r => `${r.dataset.lookback}-${r.dataset.period}`)
      .join(',');
    const params = new URLSearchParams({ configs });
    if (refresh) params.set('refresh', '1');
    const resp = await fetch(`/api/picks-multi?${params.toString()}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} from /api/picks-multi`);
    const bundle = await resp.json();
    const list = bundle.strategies || [];

    // Match each returned strategy back to its DOM container by label.
    const byKey = new Map(
      list.map(s => [`${s.strategy.lookback_months}-${s.strategy.rebalance_period_months}`, s])
    );
    for (const root of strategyEls) {
      const key = `${root.dataset.lookback}-${root.dataset.period}`;
      const data = byKey.get(key);
      if (!data) continue;
      renderNext(root, data);
      renderOpen(root, data);
      renderChart(root, data);
      renderStats(root, data);
      renderHistory(root, data);
    }
    if (list.length) renderUpdated(list[0]);
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
load({ refresh: false });

let lastLoaded = Date.now();
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && Date.now() - lastLoaded > 60_000) {
    lastLoaded = Date.now();
    load({ refresh: false });
  }
});

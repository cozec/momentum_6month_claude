const ACCENT_PALETTE = [
  '#0F766E', '#B45309', '#BE123C', '#047857', '#A16207',
  '#334155', '#0E7490', '#9F1239', '#15803D', '#92400E',
  '#0F766E', '#B91C1C', '#166534', '#475569', '#CA8A04',
  '#0F766E', '#854D0E', '#0E7490', '#365314', '#A21CAF',
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

function fmtMoney(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  return `$${Math.round(x).toLocaleString()}`;
}

function fmtDay(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtMonth(s) {
  if (!s) return '';
  const d = new Date(s + 'T00:00');
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}

function bgFromReturn(ret, maxAbs) {
  if (ret === null || ret === undefined) return '#FFFFFF';
  const intensity = Math.min(1, Math.pow(Math.abs(ret) / Math.max(maxAbs, 1e-9), 0.6));
  const pos = [220, 245, 237];
  const neg = [255, 228, 230];
  const neutral = [250, 248, 244];
  const target = ret >= 0 ? pos : neg;
  const c = neutral.map((n, i) => Math.round(n + (target[i] - n) * intensity));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function pickCard(pick, opts = {}) {
  const { isOpen = false, compact = false, maxAbs = 0.5, rankLabel = null } = opts;
  const color = tickerColor(pick.ticker);
  const bg = bgFromReturn(pick.stock_return, maxAbs);
  const positive = (pick.stock_return ?? 0) >= 0;
  const retColor = positive ? 'text-teal-700' : 'text-rose-700';
  const border = isOpen ? 'border-2 border-dashed border-teal-700' : 'border border-stone-300';

  if (compact) {
    return `
      <div class="card rounded-lg ${border} bg-white overflow-hidden flex items-stretch">
        <div class="w-1" style="background:${color}"></div>
        <div class="flex-1 flex items-center justify-between px-2.5 py-1.5" style="background:${bg}">
          <div class="text-sm font-bold text-zinc-950 leading-tight">${pick.ticker}</div>
          <div class="text-sm font-semibold ${retColor} leading-tight">${fmtPct(pick.stock_return)}</div>
        </div>
      </div>
    `;
  }

  return `
    <div class="card rounded-xl ${border} bg-white overflow-hidden">
      <div class="accent-stripe" style="background:${color}"></div>
      <div class="p-5" style="background:${bg}">
        <div class="flex items-center justify-between">
          <div class="text-3xl font-bold text-zinc-950">${pick.ticker}</div>
          <div class="text-[10px] text-zinc-600 font-medium">${rankLabel || `#${pick.rank}`}</div>
        </div>
        <div class="mt-1 text-lg font-semibold ${retColor}">${fmtPct(pick.stock_return)}</div>
        <div class="mt-2 text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded bg-stone-200 text-zinc-700 inline-block">MTD</div>
      </div>
    </div>
  `;
}

const UNIVERSE_KEY = 'titan12.universe';
const UNIVERSE_IDS = ['sp500'];

function initialUniverse() {
  const fromHash = window.location.hash.replace('#', '');
  if (UNIVERSE_IDS.includes(fromHash)) return fromHash;
  try {
    const saved = localStorage.getItem(UNIVERSE_KEY);
    if (UNIVERSE_IDS.includes(saved)) return saved;
  } catch (e) { /* storage unavailable */ }
  return 'sp500';
}

let activeUniverse = initialUniverse();

function universeInfo(data) {
  return data.universe || { id: 'sp500', label: 'S&P 500', benchmark: 'SPY', excludes_sister: true };
}

function renderTabs() {
  document.querySelectorAll('.universe-tab').forEach(btn => {
    const active = btn.dataset.universe === activeUniverse;
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
    btn.classList.toggle('border-teal-700', active);
    btn.classList.toggle('text-teal-800', active);
    btn.classList.toggle('border-transparent', !active);
    btn.classList.toggle('text-zinc-500', !active);
  });
}

function renderUniverse(data) {
  const u = universeInfo(data);
  document.getElementById('universe-title').textContent = u.label;
  document.getElementById('benchmark-label').textContent = u.benchmark;
  document.getElementById('bias-warning').textContent = data.bias_warning || '';
  document.getElementById('basket-heading').textContent =
    u.excludes_sister ? 'Nasdaq-Overlap-Excluded Current Basket' : 'Current Basket';
  document.getElementById('history-mode').textContent =
    u.excludes_sister ? 'Nasdaq-Overlap-Excluded' : 'Baseline';
  document.getElementById('summary-file').textContent =
    u.id === 'sp500' ? 'summary.md' : `summary_${u.id}.md`;
}

function renderStats(data) {
  const stats = data.stats || {};
  const bench = universeInfo(data).benchmark;
  const card = (label, value, sub) => `
    <div class="rounded-xl bg-white border border-stone-300 p-4">
      <div class="text-xs font-medium text-zinc-600 uppercase tracking-wider">${label}</div>
      <div class="text-2xl font-bold text-zinc-950 mt-1">${value}</div>
      ${sub ? `<div class="text-xs text-zinc-600 mt-1">${sub}</div>` : ''}
    </div>
  `;
  document.getElementById('stats-grid').innerHTML = [
    card('CAGR', fmtPct(stats.cagr), `${bench} value ${fmtMoney(stats.spy_value)}`),
    card('Final value', fmtMoney(stats.final_value), 'from $100,000 initial capital'),
    card('Max drawdown', fmtPct(stats.max_drawdown), `Sharpe ${(stats.sharpe ?? 0).toFixed(2)}`),
    card(`Win vs ${bench}`, fmtPct(stats.win_rate_vs_spy), `Turnover ${fmtPct(stats.average_turnover)}/mo`),
  ].join('');
}

function renderOverlay(data) {
  const overlay = data.nasdaq_overlay || {};
  const excluded = overlay.excluded || [];
  const adjusted = overlay.adjusted || [];
  const maxAbs = Math.max(...adjusted.map(p => Math.abs(p.stock_return || 0)), 0.1);
  const rebalanceDate = (data.open && data.open.date) || (adjusted[0] && adjusted[0].date);
  const badge = document.getElementById('rebalance-date');
  if (rebalanceDate) {
    badge.textContent = `Rebalanced ${fmtDay(rebalanceDate)}`;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
  const u = universeInfo(data);
  document.getElementById('overlay-note').textContent = u.excludes_sister
    ? `Excluded Nasdaq open picks: ${excluded.join(', ') || 'none'}. Backfilled from the next S&P 500 Titan-12 ranks.`
    : `Top 3 ${u.label} Titan-12 ranks. No sister-strategy overlap exclusion.`;
  document.getElementById('overlay-grid').innerHTML = adjusted
    .map(p => pickCard(p, { isOpen: true, maxAbs, rankLabel: `${u.label} rank #${p.rank}` }))
    .join('');
}

function renderNext(data) {
  const next = data.next || {};
  const picks = next.picks || [];
  const section = document.getElementById('next-section');
  if (!picks.length) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  const u = universeInfo(data);
  document.getElementById('next-date').textContent = `Enter ${fmtDay(next.date)}`;
  const exclusion = u.excludes_sister
    ? ` Excluded Nasdaq next picks: ${(next.excluded || []).join(', ') || 'unavailable'}.`
    : '';
  document.getElementById('next-note').textContent =
    `Signal locked at the ${fmtDay(next.as_of)} close; fill at the next open.${exclusion}`;
  document.getElementById('next-grid').innerHTML = picks.map(p => `
    <div class="card rounded-xl border-2 border-dashed border-indigo-700 bg-white overflow-hidden">
      <div class="accent-stripe" style="background:${tickerColor(p.ticker)}"></div>
      <div class="p-5">
        <div class="flex items-center justify-between">
          <div class="text-3xl font-bold text-zinc-950">${p.ticker}</div>
          <div class="text-[10px] text-zinc-600 font-medium">${u.label} rank #${p.rank}</div>
        </div>
        <div class="mt-1 text-sm text-zinc-700">${p.sector || ''}</div>
        <div class="mt-2 text-xs text-zinc-600">Last close ${p.entry_price_estimate != null ? '$' + p.entry_price_estimate.toFixed(2) : '—'}</div>
      </div>
    </div>
  `).join('');
}

const VIEW_KEY = 'titan12.view';
const VIEW_IDS = ['top3', 'top20'];
let activeView = 'top3';
try {
  if (localStorage.getItem(VIEW_KEY) === 'top20') activeView = 'top20';
} catch (e) { /* storage unavailable */ }
if (VIEW_IDS.includes(window.location.hash.replace('#', ''))) {
  activeView = window.location.hash.replace('#', '');
}

function renderView() {
  document.getElementById('view-top3').classList.toggle('hidden', activeView !== 'top3');
  document.getElementById('view-top20').classList.toggle('hidden', activeView !== 'top20');
  document.querySelectorAll('.view-tab').forEach(btn => {
    const active = btn.dataset.viewTab === activeView;
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
    btn.classList.toggle('border-teal-700', active);
    btn.classList.toggle('text-teal-800', active);
    btn.classList.toggle('border-transparent', !active);
    btn.classList.toggle('text-zinc-500', !active);
  });
}

function rankChangeCell(r) {
  if (r.prev_rank === null || r.prev_rank === undefined) {
    return '<span class="text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">NEW</span>';
  }
  const was = `<span class="text-[11px] text-zinc-500"> was #${r.prev_rank}</span>`;
  if (r.rank_change > 0) return `<span class="font-semibold text-teal-700">▲${r.rank_change}</span>${was}`;
  if (r.rank_change < 0) return `<span class="font-semibold text-rose-700">▼${-r.rank_change}</span>${was}`;
  return `<span class="text-zinc-400">—</span>${was}`;
}

function signedCell(x) {
  if (x === null || x === undefined) return '<span class="text-zinc-400">—</span>';
  return `<span class="${x >= 0 ? 'text-teal-700' : 'text-rose-700'}">${fmtPct(x, 0)}</span>`;
}

function renderTop20(data) {
  const board = data.top20 || {};
  const rows = board.rows || [];
  document.getElementById('top20-label').textContent = rows.length
    ? `ranked for the ${fmtDay(board.rank_date)} rebalance · prices through ${fmtDay(board.as_of)}`
    : 'no ranking available';
  document.getElementById('top20-body').innerHTML = rows.map(r => `
    <tr class="${r.held ? 'bg-teal-50' : ''}">
      <td class="px-3 py-2 text-right tabular-nums text-zinc-500">${r.rank}</td>
      <td class="px-3 py-2">
        <div class="flex items-center gap-2">
          <span class="w-1 h-5 rounded" style="background:${tickerColor(r.ticker)}"></span>
          <span class="font-bold text-zinc-950">${r.ticker}</span>
          ${r.held ? '<span class="text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded bg-teal-700 text-white">HELD</span>' : ''}
        </div>
        <div class="text-[11px] text-zinc-500">${r.company || ''}</div>
      </td>
      <td class="hidden sm:table-cell px-3 py-2 text-zinc-700">${r.sector || ''}</td>
      <td class="px-3 py-2 text-right tabular-nums">${r.score != null ? r.score.toFixed(2) : '—'}</td>
      <td class="px-3 py-2 tabular-nums whitespace-nowrap">${rankChangeCell(r)}</td>
      <td class="px-3 py-2 text-right tabular-nums">${signedCell(r.ret_1m)}</td>
      <td class="px-3 py-2 text-right tabular-nums">${signedCell(r.off_6m_high)}</td>
      <td class="hidden sm:table-cell px-3 py-2 text-right tabular-nums">${r.latest_price != null ? '$' + r.latest_price.toFixed(2) : '—'}</td>
    </tr>
  `).join('');
}

function renderHistory(data) {
  const recent = data.recent || [];
  document.getElementById('history-count').textContent = recent.length;
  const allPicks = recent.flatMap(r => r.picks || []);
  const maxAbs = Math.max(...allPicks.map(p => Math.abs(p.stock_return || 0)), 0.1);
  document.getElementById('history-list').innerHTML = recent.slice().reverse().map(row => {
    const retColor = row.portfolio_return >= 0 ? 'text-teal-700' : 'text-rose-700';
    return `
      <div class="rounded-lg bg-white border border-stone-300 px-3 py-2 flex items-center gap-3">
        <div class="w-28 flex-shrink-0 flex items-baseline gap-2">
          <div class="text-xs font-semibold text-zinc-700 leading-tight">${row.label}</div>
          <div class="text-xs font-bold ${retColor} leading-tight">${fmtPct(row.portfolio_return)}</div>
        </div>
        <div class="flex-1">
          ${row.excluded ? `<div class="mb-1 text-[10px] text-zinc-500">Excluded: ${row.excluded.join(', ') || 'none'}</div>` : ''}
          <div class="grid grid-cols-3 gap-2">
          ${row.picks.map(p => pickCard(p, { compact: true, maxAbs })).join('')}
          </div>
        </div>
      </div>
    `;
  }).join('');

  const w = data.window || {};
  const u = universeInfo(data);
  document.getElementById('window-cum').innerHTML =
    `${u.excludes_sister ? 'Adjusted' : 'Strategy'} <span class="font-semibold text-teal-700">${fmtPct(w.strategy_return, 1)}</span>
     · ${u.benchmark} <span class="font-medium text-zinc-700">${fmtPct(w.spy_return, 1)}</span>`;
}

function renderUpdated(data) {
  const dt = new Date(data.computed_at);
  document.getElementById('last-updated').innerHTML = `
    <div>updated ${dt.toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })}</div>
    <div class="text-[10px] text-zinc-500">prices through ${fmtDay(data.data_freshness)}</div>
  `;
}

async function load() {
  const refreshBtn = document.getElementById('refresh-btn');
  const refreshLabel = document.getElementById('refresh-label');
  const refreshIcon = document.getElementById('refresh-icon');
  const err = document.getElementById('error');
  err.classList.add('hidden');
  refreshBtn.disabled = true;
  refreshLabel.textContent = 'Loading…';
  refreshIcon.classList.add('animate-spin');
  const requested = activeUniverse;
  renderTabs();
  try {
    const fetchJson = async (url) => {
      const resp = await fetch(url, { cache: 'no-store' });
      const text = await resp.text();
      if (!resp.ok) throw new Error(`HTTP ${resp.status} from ${url}`);
      try {
        return JSON.parse(text);
      } catch (e) {
        throw new Error(`Non-JSON response from ${url}`);
      }
    };

    let data;
    try {
      // A single-file report embeds its snapshot; no server to ask.
      if (window.DASHBOARD_DATA) data = window.DASHBOARD_DATA;
      else data = await fetchJson(`/api/dashboard?universe=${requested}`);
    } catch (e) {
      // The static export only carries the S&P 500 tab.
      if (requested !== 'sp500') throw e;
      data = await fetchJson('/dashboard.json');
    }
    if (requested !== activeUniverse) return;  // a newer tab click won
    renderUniverse(data);
    renderStats(data);
    renderOverlay(data);
    renderNext(data);
    renderTop20(data);
    renderHistory(data);
    renderUpdated(data);
  } catch (e) {
    err.textContent = `Failed to load dashboard: ${e.message}`;
    err.classList.remove('hidden');
  } finally {
    refreshBtn.disabled = false;
    refreshLabel.textContent = 'Refresh';
    refreshIcon.classList.remove('animate-spin');
  }
}

document.getElementById('refresh-btn').addEventListener('click', load);
document.querySelectorAll('.view-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    activeView = btn.dataset.viewTab;
    try { localStorage.setItem(VIEW_KEY, activeView); } catch (e) { /* storage unavailable */ }
    history.replaceState(null, '', `#${activeView}`);
    renderView();
  });
});
renderView();
document.querySelectorAll('.universe-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.universe === activeUniverse) return;
    activeUniverse = btn.dataset.universe;
    try { localStorage.setItem(UNIVERSE_KEY, activeUniverse); } catch (e) { /* storage unavailable */ }
    history.replaceState(null, '', `#${activeUniverse}`);
    load();
  });
});
window.addEventListener('hashchange', () => {
  const next = window.location.hash.replace('#', '');
  if (VIEW_IDS.includes(next)) {
    activeView = next;
    renderView();
    return;
  }
  if (UNIVERSE_IDS.includes(next) && next !== activeUniverse) {
    activeUniverse = next;
    load();
  }
});
load();

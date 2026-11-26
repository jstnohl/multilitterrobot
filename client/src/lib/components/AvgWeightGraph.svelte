<script>
	import { onMount, onDestroy } from 'svelte';
	import DateRangePicker from './DateRangePicker.svelte';
	import { computeTrends, downloadCSV } from '$lib/insights';

	// 7-day trailing average weight per cat — one line per cat, in the cat's
	// own color. Self-contained like CatGraphs: loads its own data and owns
	// its own date range (7d / 30d / All presets + sliders, minimum span 7 days).
	export let hiddenCats = {};

	let pets = [];
	let visits = [];
	let loading = true;
	let error = '';

	let fromISO = '';
	let toISO = '';

	let timer;
	let W = 800;
	let nowMs = Date.now();
	const H = 260;

	// Keep W at the wrapper's real pixel width (same ResizeObserver action
	// CatGraphs uses), so the viewBox coordinate space tracks the card.
	// With a viewBox the chart scales to the rendered size, so a stale W
	// can't misplace the dots the way raw pixel coordinates could.
	function observeSize(node) {
		const observer = new ResizeObserver((entries) => {
			const rect = entries[0].contentRect;
			if (rect.width > 100) {
				W = Math.round(rect.width);
			}
		});
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
	}

	const DAY = 86400000;
	const WINDOW_DAYS = 7;

	async function loadAll() {
		try {
			const [petsRes, visitsRes] = await Promise.all([
				fetch('/api/pets'),
				fetch('/api/visits?limit=500')
			]);
			if (!petsRes.ok || !visitsRes.ok) throw new Error('backend request failed');
			pets = await petsRes.json();
			visits = await visitsRes.json();
			error = '';
		} catch (e) {
			error = 'Could not load graph data — is the backend running?';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadAll();
		timer = setInterval(() => { loadAll(); nowMs = Date.now(); }, 30000);
	});

	onDestroy(() => clearInterval(timer));

	function msFor(iso) {
		if (!iso) return new Date().getTime();
		const [y, m, d] = iso.split('-').map(Number);
		return new Date(y, m - 1, d).getTime();
	}

	function fmtDay(ms) {
		return new Date(ms).toLocaleDateString([], { month: 'short', day: 'numeric' });
	}

	// X-axis labels: a single-day range shows clock times (HH:MM) — date
	// labels would all read the same day. Multi-day ranges show dates.
	function fmtX(ms) {
		if (plotMax - plotMin <= DAY) {
			return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		}
		return fmtDay(ms);
	}

	// Tooltip for a dot: when the trailing average at that point was
	// calculated. "12:11 PM 11/22" — time first, then date; no @ sign.
	function fmtTooltip(ms) {
		const d = new Date(ms);
		const hhmm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		const mmdd = d.toLocaleDateString([], { month: '2-digit', day: '2-digit' });
		return `${hhmm} ${mmdd}`;
	}

	function colorFor(name) {
		const pet = pets.find((p) => p.name === name);
		return pet?.color ?? '#9ca3af';
	}

	// Automatic visits only: manual visits just repeat the input weight, so
	// they are not scale readings and must not move the average.
	$: autoVisits = visits.filter((v) => v.pet && !v.manual && v.weight != null && !isNaN(Number(v.weight)));

	// How much history the trailing average has to work with. The graph stays
	// hidden until there are at least 7 days of visits behind it.
	$: historyDays = (() => {
		if (autoVisits.length === 0) return 0;
		let min = Infinity;
		let max = -Infinity;
		for (const v of autoVisits) {
			const t = new Date(v.timestamp).getTime();
			if (isNaN(t)) continue;
			if (t < min) min = t;
			if (t > max) max = t;
		}
		if (!isFinite(min)) return 0;
		return (max - min) / DAY;
	})();

	$: hasEnoughData = historyDays >= WINDOW_DAYS;

	// Per-pet series: at each visit, the mean of that pet's automatic visits
	// in the trailing 7 days (exclusive of exactly 7 days ago).
	$: series = (() => {
		const byPet = {};
		for (const v of autoVisits) {
			(byPet[v.pet] ??= []).push(v);
		}
		return Object.entries(byPet).map(([name, vs]) => {
			const sorted = [...vs].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
			const pts = [];
			for (const v of sorted) {
				const t = new Date(v.timestamp).getTime();
				const win = sorted.filter((w) => {
					const wt = new Date(w.timestamp).getTime();
					return wt <= t && wt > t - WINDOW_DAYS * DAY;
				});
				const avg = win.reduce((s, w) => s + Number(w.weight), 0) / win.length;
				pts.push({ t, avg: Math.round(avg * 100) / 100 });
			}
			return { name, color: colorFor(name), pts };
		});
	})();

	$: fromMs = msFor(fromISO);
	$: toMs = msFor(toISO) + DAY;

	$: visible = series.filter((s) => !hiddenCats[s.name]);
	$: ranged = visible.map((s) => ({ ...s, pts: s.pts.filter((p) => p.t >= fromMs && p.t < toMs) }));

	// X domain is the selected range: From midnight to the end of the range.
	// The end is "now" when the range runs to today, so the right edge is the
	// current time — not midnight, and not the last visit.
	$: plotMin = fromMs;
	$: plotMax = Math.max(plotMin + 1, Math.min(toMs - 1, nowMs));

	// Y scale from the plotted averages.
	$: yVals = ranged.flatMap((s) => s.pts.map((p) => p.avg));
	$: yMin = yVals.length ? Math.min(...yVals) : 0;
	$: yMax = yVals.length ? Math.max(...yVals) : 1;
	$: yPad = Math.max(0.2, (yMax - yMin) * 0.1);
	$: yLo = Math.floor((yMin - yPad) * 10) / 10;
	$: yHi = Math.ceil((yMax + yPad) * 10) / 10;

	function xFor(t) {
		return 34 + ((t - plotMin) / Math.max(1, plotMax - plotMin)) * (W - 34 - 12);
	}

	function yFor(v) {
		return 12 + (1 - (v - yLo) / Math.max(0.001, yHi - yLo)) * (H - 12 - 28);
	}

	function pointsFor(pts) {
		return pts.map((p) => `${xFor(p.t)},${yFor(p.avg)}`).join(' ');
	}

	$: yTicks = [0, 1, 2, 3, 4].map((i) => yLo + ((yHi - yLo) * i) / 4);
	// X ticks land on local midnights, exactly N days apart, so a dot's
	// position reads true against the labels. (Evenly-spaced ticks across
	// a non-integer-day span put labels 1.44 days apart, which made a
	// Nov 22 12:11 dot read as late Nov 21.)
	$: xTicks = (() => {
		const span = plotMax - plotMin;
		const stepDays = span <= 10 * DAY ? 1 : span <= 21 * DAY ? 2 : span <= 35 * DAY ? 5 : 7;
		const out = [];
		const d = new Date(plotMin);
		d.setHours(0, 0, 0, 0);
		if (d.getTime() < plotMin) d.setDate(d.getDate() + 1);
		while (d.getTime() <= plotMax) {
			out.push(d.getTime());
			d.setDate(d.getDate() + stepDays);
		}
		return out.length ? out : [plotMin];
	})();

	$: pointCount = ranged.reduce((s, r) => s + r.pts.length, 0);
	$: trends = computeTrends(pets, visits, nowMs);

	// Force a full re-render of the chart whenever the width, domain,
	// y-scale or data changes (same trick CatGraphs uses), so the
	// initial render can never get stuck with a stale width/domain.
	$: chartKey = `${W}|${plotMin}|${plotMax}|${yMin}|${yMax}|${ranged.map((s) => s.pts.map((p) => p.t).join(',')).join('|')}`;
	// v084: download the plotted trailing averages for the selected range.
	function exportAverages() {
		const rows = [['timestamp', 'pet', 'trailing_7d_avg_lbs']];
		const all = [];
		for (const s of ranged) {
			for (const p of s.pts) all.push({ t: p.t, name: s.name, avg: p.avg });
		}
		all.sort((a, b) => a.t - b.t);
		for (const r of all) rows.push([new Date(r.t).toISOString(), r.name, r.avg.toFixed(2)]);
		const csv = rows.map((r) => r.join(',')).join('\n') + '\n';
		const stamp = new Date().toISOString().slice(0, 10);
		downloadCSV(`multilitterrobot-averages-${stamp}.csv`, csv);
	}

</script>

<div>
	<!-- v084-avgtrend: trend row + panel CSV -->
	<div class="flex flex-wrap items-start justify-between gap-2">
		<div class="min-w-0 flex-1">
			<DateRangePicker bind:fromISO bind:toISO {visits} minSpanDays={7} />
		</div>
		<button class="btn btn-ghost btn-sm mt-1" on:click={exportAverages}>Export CSV</button>
	</div>
	{#if loading}
		<p class="text-sm opacity-70">Loading…</p>
	{:else if error}
		<p class="text-error text-sm">{error}</p>
	{:else if !hasEnoughData}
		<p class="text-sm opacity-70">
			Need at least 7 days of visits to draw the trailing average — {historyDays.toFixed(1)} days on
			record so far. Check back once the boxes have cycled for a week.
		</p>
	{:else if pointCount === 0}
		<p class="text-sm opacity-70">No averages in this range — slide it wider or pick All.</p>
	{:else}
		<div use:observeSize class="w-full">
			{#key chartKey}
			<svg viewBox="0 0 {W} {H}" class="w-full">
				{#each yTicks as y, i (i)}
					<line x1="34" x2={W - 12} y1={yFor(y)} y2={yFor(y)} stroke="currentColor" stroke-opacity="0.08" />
					<text x="28" y={yFor(y) + 4} text-anchor="end" font-size="11" fill="currentColor" opacity="0.6">{y.toFixed(1)}</text>
				{/each}
				{#each xTicks as t, i (i)}
					<line x1={xFor(t)} x2={xFor(t)} y1="12" y2={H - 28} stroke="currentColor" stroke-opacity="0.08" />
					<text x={xFor(t)} y={H - 12} text-anchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'} font-size="11" fill="currentColor" opacity="0.6">{fmtX(t)}</text>
				{/each}
				{#each ranged as s (s.name)}
					{#if s.pts.length > 0}
						<polyline points={pointsFor(s.pts)} fill="none" stroke={s.color} stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
						{#each s.pts as p (p.t)}
							<circle cx={xFor(p.t)} cy={yFor(p.avg)} r="4" fill={s.color}>
								<title>{fmtTooltip(p.t)}</title>
							</circle>
						{/each}
					{/if}
				{/each}
			</svg>
			{/key}
		</div>
		<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-base-300 pt-2 text-sm">
			{#each trends as t (t.name)}
			<span class="flex items-center gap-1.5">
				<span class="inline-block h-2.5 w-2.5 rounded-full" style="background:{t.color}"></span>
				{t.name}
				{#if t.pct != null}
					<span class={Math.abs(t.pct) >= 5 ? (t.pct < 0 ? 'font-semibold text-warning' : 'font-semibold text-success') : ''}>
						{t.dir === 'up' ? '▲' : t.dir === 'down' ? '▼' : '↔'} {Math.abs(t.pct).toFixed(1)}%
					</span>
				{:else}
					<span class="opacity-60">—</span>
				{/if}
			</span>
			{/each}
		</div>
		<p class="text-xs opacity-60 mt-2">
			{pointCount} average point{pointCount === 1 ? '' : 's'} in range · {fmtDay(fromMs)} – {fmtDay(toMs - DAY)} · trailing 7-day average
		</p>
	{/if}
</div>

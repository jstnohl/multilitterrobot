<script>
	import { onMount, onDestroy } from 'svelte';
	import DateRangePicker from './DateRangePicker.svelte';

	// Which kitties are hidden on the graph — owned by the Kitties cards
	// (left column), which act as the legend. Click a card to toggle.
	export let hiddenCats = {};

	let pets = [];
	let visits = [];
	let boxColors = {};
	let loading = true;
	let error = '';

	// Date range, bound to the shared picker (sliders + typed dates + presets).
	let fromISO = '';
	let toISO = '';

	let showLines = true;
	let showFill = true;

	let timer;

	const UNKNOWN = 'Unknown';
	const UNKNOWN_COLOR = '#9ca3af';
	const DAY = 86400000;

	async function loadAll() {
		try {
			const [petsRes, visitsRes, colorsRes] = await Promise.all([
				fetch('/api/pets'),
				fetch('/api/visits?limit=500'),
				fetch('/api/box-colors')
			]);
			if (!petsRes.ok || !visitsRes.ok) throw new Error('backend request failed');
			pets = await petsRes.json();
			visits = await visitsRes.json();
			if (colorsRes.ok) boxColors = await colorsRes.json();
			error = '';
		} catch (e) {
			error = 'Could not load graph data — is the backend running?';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadAll();
		timer = setInterval(loadAll, 30000);
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
		if (fromISO && fromISO === toISO) {
			return new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
		}
		return fmtDay(ms);
	}

	function fmtTime(iso) {
		if (!iso) return '—';
		return new Date(iso).toLocaleString([], {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	function colorFor(name) {
		const pet = pets.find((p) => p.name === name);
		return pet ? pet.color || '#888' : UNKNOWN_COLOR;
	}

	function boxColor(serial) {
		return boxColors[serial] || '#888';
	}

	// Hover tooltip state — follows the mouse, shows who / box / weight /
	// time as real text (replaces the slow native <title> tooltip).
	let hovered = null;
	let hoverX = 0;
	let hoverY = 0;
	let wrapEl;

	function whoFor(v) {
		return v.pet || (v.ambiguous && v.ambiguous.length ? v.ambiguous.join(' or ') : UNKNOWN);
	}

	function onDotEnter(v, e) {
		hovered = v;
		moveTip(e);
	}

	function moveTip(e) {
		if (!wrapEl) return;
		const rect = wrapEl.getBoundingClientRect();
		let x = e.clientX - rect.left + 14;
		let y = e.clientY - rect.top + 14;
		if (x > rect.width - 180) x = e.clientX - rect.left - 190;
		if (y > rect.height - 120) y = e.clientY - rect.top - 120;
		hoverX = Math.max(0, x);
		hoverY = Math.max(0, y);
	}

	function onDotLeave() {
		hovered = null;
	}

	$: fromMs = msFor(fromISO);
	$: toMs = msFor(toISO) + DAY; // exclusive end: through the end of the To day

	$: ranged = visits.filter((v) => {
		const t = new Date(v.timestamp).getTime();
		return !isNaN(t) && t >= fromMs && t < toMs;
	});

	$: plotted = ranged.filter(
		(v) => v.weight != null && !(v.pet ? hiddenCats[v.pet] : hiddenCats[UNKNOWN])
	);

	$: pointsByCat = (() => {
		const map = {};
		for (const v of plotted) {
			const key = v.pet || UNKNOWN;
			(map[key] = map[key] || []).push(v);
		}
		for (const key of Object.keys(map)) {
			map[key].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
		}
		return map;
	})();

	// ---- chart geometry (weight on Y, time on X) ----

	// Chart size follows the card: the card stretches to the kitties
	// column's height and the chart wrapper fills the card. This action
	// keeps the viewBox at the wrapper's real pixel size so the dots
	// stay round no matter how tall the chart gets.
	let W = 760;
	let H = 320;
	const PL = 46;
	const PR = 16;
	const PT = 14;
	const PB = 32;
	$: IW = W - PL - PR;
	$: IH = H - PT - PB;

	function observeSize(node) {
		const observer = new ResizeObserver((entries) => {
			const rect = entries[0].contentRect;
			if (rect.width > 100 && rect.height > 100) {
				W = Math.round(rect.width);
				H = Math.round(rect.height);
			}
		});
		observer.observe(node);
		return {
			destroy() {
				observer.disconnect();
			}
		};
	}

	// Y scale: ONE atomic derivation from `ranged` (ALL visits in range,
	// hidden or not), so the dots (which read yMin/yMax through y()) and
	// the labels (which read yTicks) can never desync. Deriving it from
	// `plotted` made every toggle a scale change, and the dots/labels kept
	// landing in different states. Now a toggle only hides/shows dots —
	// the axis, gridlines and visible dots never move, which is also what
	// makes cats comparable at a glance. The axis still hugs the data
	// (0.25 lb margin) and the scale stays linear with true labels.
	let yMin = 0;
	let yMax = 10;
	let yStep = 1;
	let yTicks = [];
	$: {
		const ws = ranged.map((v) => Number(v.weight)).filter((w) => !isNaN(w));
		const lo = ws.length ? Math.min(...ws) - 0.25 : 0;
		const hi = ws.length ? Math.max(...ws) + 0.25 : 10;
		const step = hi - lo <= 4 ? 0.5 : hi - lo <= 12 ? 1 : 2;
		const firstTick = Math.ceil(lo / step) * step;
		const ticks = [];
		for (let tick = firstTick; tick <= hi + 1e-9; tick += step) {
			ticks.push(Math.round(tick * 100) / 100);
		}
		yMin = lo;
		yMax = hi;
		yStep = step;
		yTicks = ticks;
	}

	$: xTicks = (() => {
		const ticks = [];
		const n = 6;
		for (let i = 0; i < n; i++) {
			ticks.push(fromMs + ((toMs - fromMs) * i) / (n - 1));
		}
		return ticks;
	})();

	function x(ms) {
		if (toMs <= fromMs) return PL;
		return PL + ((ms - fromMs) / (toMs - fromMs)) * IW;
	}

	function y(w) {
		if (yMax <= yMin) return PT + IH / 2;
		return PT + (1 - (w - yMin) / (yMax - yMin)) * IH;
	}

	// Filled area under one cat's line: along the points, down to the chart
	// floor, back along the floor. Same colour as the line, faint, so
	// overlapping cats stay readable.
	function areaPath(pts) {
		if (pts.length < 2) return '';
		const line = pts
			.map((v) => `${x(new Date(v.timestamp).getTime())},${y(v.weight)}`)
			.join(' ');
		const first = pts[0];
		const last = pts[pts.length - 1];
		const floor = PT + IH;
		return `M ${line} L ${x(new Date(last.timestamp).getTime())},${floor} L ${x(new Date(first.timestamp).getTime())},${floor} Z`;
	}
</script>

<section class="flex-1 min-h-0 flex flex-col">
	<div class="card bg-base-100 shadow flex-1 min-h-0 flex flex-col">
		<div class="card-body flex flex-col flex-1 min-h-0">
			<div class="flex flex-wrap justify-between items-center gap-2 mb-2">
				<h3 class="font-bold text-lg">Kitty graphs</h3>
				<div class="flex flex-wrap items-center gap-2">
					<label class="flex items-center gap-1.5 text-sm cursor-pointer">
						<input type="checkbox" class="toggle toggle-sm" bind:checked={showLines} />
						Trend lines
					</label>
					<label class="flex items-center gap-1.5 text-sm cursor-pointer">
						<input type="checkbox" class="toggle toggle-sm" bind:checked={showFill} />
						Fill
					</label>
				</div>
			</div>

			<DateRangePicker bind:fromISO bind:toISO {visits} />

			{#if loading}
				<p>Loading graphs…</p>
			{:else if error}
				<div class="alert alert-error">{error}</div>
			{:else if visits.length === 0}
				<p class="text-sm opacity-70">
					No visits logged yet — the graph fills in as the boxes cycle. Weight on the
					up-axis, date along the bottom; each dot is one visit, filled with the
					kitty's colour and ringed with the box's colour.
				</p>
			{:else if ranged.length === 0}
				<p class="text-sm opacity-70 py-8 text-center">
					No visits in this date range — slide it wider or pick All.
				</p>
			{:else if plotted.length === 0}
				<p class="text-sm opacity-70 py-8 text-center">
					Everything in this range is hidden — click a kitty card to show them
					again, or widen the range.
				</p>
			{:else}
				<div class="relative flex-1 min-h-[280px] flex" bind:this={wrapEl} use:observeSize>
				<!-- Keyed so the whole chart re-renders as one consistent unit:
				     dots and labels kept desyncing because Svelte doesn't track
				     the scale inside the y()/x() calls, so one half would
				     re-render and the other wouldn't. The key covers the scale,
				     size, range, visible dots and toggles. -->
				{#key `${yMin}|${yMax}|${W}|${H}|${fromMs}|${toMs}|${plotted.map((v) => v.id).join(',')}|${showLines}|${showFill}`}
				<svg viewBox="0 0 {W} {H}" class="flex-1 min-h-0 min-w-0" role="img">
					<!-- Y gridlines + labels (lbs) -->
					{#each yTicks as t (t)}
						<line
							x1={PL}
							y1={y(t)}
							x2={W - PR}
							y2={y(t)}
							stroke="currentColor"
							stroke-opacity="0.12"
						/>
						<text
							x={PL - 8}
							y={y(t) + 4}
							text-anchor="end"
							font-size="11"
							fill="currentColor"
							fill-opacity="0.6">{t}</text
						>
					{/each}
					<text
						x="14"
						y={PT + IH / 2}
						font-size="11"
						fill="currentColor"
						fill-opacity="0.6"
						transform="rotate(-90 14 {PT + IH / 2})"
						text-anchor="middle">lbs</text
					>

					<!-- X ticks (dates) -->
					{#each xTicks as t, i}
						<line
							x1={x(t)}
							y1={PT}
							x2={x(t)}
							y2={PT + IH}
							stroke="currentColor"
							stroke-opacity="0.08"
						/>
						<text
							x={x(t)}
							y={H - 10}
							text-anchor={i === xTicks.length - 1 ? 'end' : 'middle'}
							font-size="11"
							fill="currentColor"
							fill-opacity="0.6">{fmtX(t)}</text
						>
					{/each}

					<!-- Filled area under each kitty's line -->
					{#if showFill}
						{#each Object.entries(pointsByCat) as [key, pts] (key)}
							{#if key !== UNKNOWN && pts.length > 1}
								<path
									d={areaPath(pts)}
									fill={colorFor(key)}
									fill-opacity="0.12"
								/>
							{/if}
						{/each}
					{/if}

					<!-- Trend lines, one per kitty -->
					{#if showLines}
						{#each Object.entries(pointsByCat) as [key, pts] (key)}
							{#if key !== UNKNOWN && pts.length > 1}
								<polyline
									points={pts
										.map((v) => `${x(new Date(v.timestamp).getTime())},${y(v.weight)}`)
										.join(' ')}
									fill="none"
									stroke={colorFor(key)}
									stroke-width="2"
									stroke-opacity="0.7"
								/>
							{/if}
						{/each}
					{/if}

					<!-- Dots: fill = kitty, ring = box -->
					{#each plotted as v (v.id)}
						<circle
							cx={x(new Date(v.timestamp).getTime())}
							cy={y(v.weight)}
							r="9"
							fill={colorFor(v.pet || UNKNOWN)}
							stroke={boxColor(v.serial)}
							stroke-width="4.5"
							class="cursor-pointer"
							on:mouseenter={(e) => onDotEnter(v, e)}
							on:mousemove={moveTip}
							on:mouseleave={onDotLeave}
						/>
					{/each}
				</svg>
				{/key}
				{#if hovered}
					<div
						class="absolute z-10 pointer-events-none bg-neutral text-neutral-content text-xs rounded-lg shadow-lg px-3 py-2"
						style="left: {hoverX}px; top: {hoverY}px;"
					>
						<p><strong>{whoFor(hovered)}</strong></p>
						<p>Box: {hovered.robot}</p>
						<p>Weight: {hovered.weight} lbs</p>
						<p>{fmtTime(hovered.timestamp)}</p>
					</div>
				{/if}
				</div>
				<p class="text-xs opacity-60 mt-1" style="flex: 0 0 auto;">
					{ranged.length} visit{ranged.length === 1 ? '' : 's'} in range · {plotted.length}
					plotted · {fmtDay(fromMs)} – {fmtDay(msFor(toISO))}
				</p>
			{/if}
		</div>
	</div>
</section>

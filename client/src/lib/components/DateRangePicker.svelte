<script>
	// Shared date-range control: presets + typed date fields + sliders.
	// All three write the same range. The parent binds fromISO/toISO and
	// filters its own data by them.
	//   <DateRangePicker bind:fromISO bind:toISO {visits} />
	export let visits = [];
	export let fromISO = '';
	export let toISO = '';
	export let minSpanDays = 0;

	const DAY = 86400000;

	function todayMs() {
		const d = new Date();
		return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
	}

	function isoFor(ms) {
		const d = new Date(ms);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
			d.getDate()
		).padStart(2, '0')}`;
	}

	function msFor(iso) {
		if (!iso) return todayMs();
		const [y, m, d] = iso.split('-').map(Number);
		return new Date(y, m - 1, d).getTime();
	}

	// Earliest visit day (local midnight). No visits yet -> today.
	$: dataStartMs = (() => {
		if (visits.length === 0) return todayMs();
		let min = Infinity;
		for (const v of visits) {
			const t = new Date(v.timestamp).getTime();
			if (!isNaN(t) && t < min) min = t;
		}
		if (!isFinite(min)) return todayMs();
		const d = new Date(min);
		return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
	})();

	$: spanDays = Math.max(0, Math.round((todayMs() - dataStartMs) / DAY));
	// Minimum gap between the sliders, in whole days (7-day span = 6-day gap).
	$: minGap = Math.min(Math.max(0, minSpanDays - 1), spanDays);

	// First data: default to everything on record.
	$: if (visits.length > 0 && !fromISO) {
		fromISO = isoFor(dataStartMs);
		toISO = isoFor(todayMs());
	}

	// Keep From <= To, and keep at least minSpanDays between them.
	$: if (fromISO && toISO) {
		if (fromISO > toISO) toISO = fromISO;
		else if (minGap > 0 && msFor(toISO) - msFor(fromISO) < minGap * DAY) {
			const fwd = msFor(fromISO) + minGap * DAY;
			if (fwd <= dataStartMs + spanDays * DAY) toISO = isoFor(fwd);
			else fromISO = isoFor(msFor(toISO) - minGap * DAY);
		}
	}

	$: fromOffset = Math.max(
		0,
		Math.min(spanDays, Math.round((msFor(fromISO) - dataStartMs) / DAY))
	);
	$: toOffset = Math.max(
		0,
		Math.min(spanDays, Math.round((msFor(toISO) - dataStartMs) / DAY))
	);

	function setFromOffset(n) {
		n = Math.max(0, Math.min(n, toOffset - minGap));
		fromISO = isoFor(dataStartMs + n * DAY);
		if (fromISO > toISO) toISO = fromISO;
		if (minGap > 0 && msFor(toISO) - msFor(fromISO) < minGap * DAY)
			toISO = isoFor(Math.min(dataStartMs + spanDays * DAY, msFor(fromISO) + minGap * DAY));
	}

	function setToOffset(n) {
		n = Math.min(spanDays, Math.max(n, fromOffset + minGap));
		toISO = isoFor(dataStartMs + n * DAY);
		if (toISO < fromISO) fromISO = toISO;
		if (minGap > 0 && msFor(toISO) - msFor(fromISO) < minGap * DAY)
			fromISO = isoFor(Math.max(dataStartMs, msFor(toISO) - minGap * DAY));
	}

	function setPreset(kind) {
		const today = todayMs();
		toISO = isoFor(today);
		if (kind === '7d') fromISO = isoFor(today - 6 * DAY);
		else if (kind === '30d') fromISO = isoFor(today - 29 * DAY);
		else fromISO = isoFor(dataStartMs);
	}

	$: activePreset =
		!fromISO
			? ''
			: fromISO === isoFor(dataStartMs)
				? 'all'
				: fromISO === isoFor(todayMs() - 6 * DAY)
					? '7d'
					: fromISO === isoFor(todayMs() - 29 * DAY)
						? '30d'
						: '';
</script>

<div class="flex flex-col gap-1 mb-3">
	<div class="flex items-center gap-3">
		<span class="text-sm w-10 shrink-0 opacity-70">Range</span>
		<div class="join">
			<button
				class="btn btn-sm join-item"
				class:btn-active={activePreset === '7d'}
				disabled={visits.length === 0}
				on:click={() => setPreset('7d')}>7d</button
			>
			<button
				class="btn btn-sm join-item"
				class:btn-active={activePreset === '30d'}
				disabled={visits.length === 0}
				on:click={() => setPreset('30d')}>30d</button
			>
			<button
				class="btn btn-sm join-item"
				class:btn-active={activePreset === 'all'}
				disabled={visits.length === 0}
				on:click={() => setPreset('all')}>All</button
			>
		</div>
	</div>
	<div class="flex items-center gap-3">
		<span class="text-sm w-10 shrink-0 opacity-70">From</span>
		<input
			type="date"
			class="input input-bordered input-sm w-40"
			bind:value={fromISO}
			disabled={visits.length === 0}
		/>
		<input
			type="range"
			class="range range-primary range-xs flex-1"
			min="0"
			max={spanDays}
			step="1"
			value={fromOffset}
			disabled={visits.length === 0 || spanDays === 0}
			on:input={(e) => setFromOffset(+e.target.value)}
		/>
	</div>
	<div class="flex items-center gap-3">
		<span class="text-sm w-10 shrink-0 opacity-70">To</span>
		<input
			type="date"
			class="input input-bordered input-sm w-40"
			bind:value={toISO}
			disabled={visits.length === 0}
		/>
		<input
			type="range"
			class="range range-primary range-xs flex-1"
			min="0"
			max={spanDays}
			step="1"
			value={toOffset}
			disabled={visits.length === 0 || spanDays === 0}
			on:input={(e) => setToOffset(+e.target.value)}
		/>
	</div>
</div>

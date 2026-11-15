<script>
	import { onMount } from 'svelte';

	// Which colour this box's ring is on the graph (the dot's fill is the
	// cat, the ring is the box; the trend line stays the cat's colour).
	// Set from the gear on the robot card.
	export let serial;

	// Deliberately a different range from kitty colours (bright orange /
	// sky / violet / emerald / pink / yellow) — dark, muted tones, so a
	// ring never looks like a cat.
	const BOX_PALETTE = ['#1e40af', '#dc2626', '#065f46', '#92400e', '#4c1d95', '#334155'];

	let colors = {};
	let open = false;
	let saving = false;
	let error = '';

	async function load() {
		try {
			const res = await fetch('/api/box-colors');
			if (res.ok) colors = await res.json();
		} catch (e) {
			// no colours yet — the gear still opens, it just shows grey
		}
	}

	onMount(load);

	$: current = colors[serial] || '#888';

	async function setColor(color) {
		saving = true;
		error = '';
		const res = await fetch('/api/box-colors', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ serial, color })
		});
		if (res.ok) {
			const data = await res.json();
			colors = { ...colors, [data.serial]: data.color };
			open = false;
		} else {
			error = 'Could not save — try again.';
		}
		saving = false;
	}
</script>

<div class="mt-2 flex justify-start">
	<button
		class="btn btn-ghost btn-xs gap-1.5"
		title="Box colour — the ring around this box's dots on the graph"
		on:click={() => (open = !open)}
	>
		<span class="inline-block w-3 h-3 rounded-full" style="background: {current}"></span>
		⚙
	</button>
	{#if open}
		<div class="flex flex-wrap items-center gap-2 mt-1">
			{#each BOX_PALETTE as c (c)}
				<button
					type="button"
					class="w-6 h-6 rounded-full border"
					class:ring-2={current === c}
					class:ring-offset-1={current === c}
					style="background: {c}"
					title={c}
					disabled={saving}
					on:click={() => setColor(c)}
				/>
			{/each}
			<button class="btn btn-ghost btn-xs" disabled={saving} on:click={() => setColor(null)}>
				Reset
			</button>
		</div>
		{#if error}
			<p class="text-error text-xs mt-1">{error}</p>
		{/if}
	{/if}
</div>

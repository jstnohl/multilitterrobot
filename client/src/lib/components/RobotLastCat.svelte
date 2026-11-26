<script>
	import { onMount } from 'svelte';

	// Which cat last used this box — shown on the robot card, set by hand.
	// The backend uses it to break weight ties on the next visit, sets it
	// itself on every confident match, and updates it whenever you correct
	// a visit — so it keeps dialling itself in.
	export let serial;
	export let compact = false; // Dropdown only -- the card row supplies the "Last weight ... by" text.

	let pets = [];
	let current = null; // {pet_id, pet_name, updated_at}
	let saving = false;
	let error = '';

	async function load() {
		try {
			const [petsRes, lastRes] = await Promise.all([
				fetch('/api/pets'),
				fetch(`/api/robot/${encodeURIComponent(serial)}/last-cat`)
			]);
			if (petsRes.ok) pets = await petsRes.json();
			if (lastRes.ok) current = await lastRes.json();
		} catch (e) {
			error = 'Could not load last-cat info.';
		}
	}

	onMount(load);

	async function setCat(value) {
		if (value === '') return;
		saving = true;
		error = '';
		const res = await fetch(`/api/robot/${encodeURIComponent(serial)}/last-cat`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ pet_id: value === 'clear' ? null : value })
		});
		if (res.ok) {
			current = await res.json();
		} else {
			error = 'Could not save — try again.';
		}
		saving = false;
	}

	// Clock time (HH:MM) — when the cat last used this box, local time.
	function fmtClock(iso) {
		if (!iso) return '';
		return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}
</script>

<div class="flex flex-wrap items-center gap-2 text-sm">
	{#if !compact}
		<span class="opacity-70">Last used by:</span>
		{#if current?.pet_name}
			<strong>{current.pet_name}</strong>
			{#if current.updated_at}
				<span class="opacity-60">· {fmtClock(current.updated_at)}</span>
			{/if}
		{:else}
			<span class="opacity-60">not set</span>
		{/if}
	{/if}
	<select
		class="select select-bordered select-xs"
		value={current?.pet_id ?? ''}
		disabled={saving || pets.length === 0}
		on:change={(e) => setCat(e.target.value)}
		title="Assign this box's last cat — the next weight tie on this box goes to them"
	>
		<option value="" disabled>Assign…</option>
		{#each pets as pet (pet.id)}
			<option value={pet.id}>{pet.name}</option>
		{/each}
		<option value="clear">Unknown / clear</option>
	</select>
	{#if error}
		<span class="text-error text-xs">{error}</span>
	{/if}
</div>

<script>
	import { onMount, onDestroy } from 'svelte';
	import CatGraphs from './CatGraphs.svelte';
	import AvgWeightGraph from './AvgWeightGraph.svelte';
	import DateRangePicker from './DateRangePicker.svelte';

	let pets = [];
	let visits = [];
	let events = [];
	let photos = {};
	let robots = [];
	let loading = true;
	let error = '';
	let resolveError = '';

	let showForm = false;
	let newName = '';
	let newWeight = '';
	let newBirthdate = '';
	let newColor = '#f97316';
	let addError = '';

	let filterPet = 'all';

	// Anomaly tab (v071): 'visits' or 'anomalies'.
	let activeTab = 'average';

	// Graph visibility, owned here — the cards ARE the legend. Click a card
	// to hide/show that kitty on the graph (passed down to CatGraphs).
	let hiddenCats = {};

	// Which kitty's colour picker is open (the gear on a card), or null.
	let colorPickerFor = null;

	// The visits table has its own range, separate from the graph's.
	let visitFromISO = '';
	let visitToISO = '';

	let timer;

	// Anomaly tab (v071): unresolved events, newest first (GET /api/events
	// already returns newest first).
	$: unresolvedEvents = events.filter((e) => !e.resolution);

	const PRESET_COLORS = ['#f97316', '#38bdf8', '#a78bfa', '#34d399', '#f472b6', '#facc15'];
	const DAY = 86400000;

	async function loadAll() {
		try {
			const [petsRes, visitsRes, robotsRes, eventsRes] = await Promise.all([
				fetch('/api/pets'),
				fetch('/api/visits?limit=500'),
				fetch('/api/robots'),
				fetch('/api/events?limit=100')
			]);
			if (!petsRes.ok || !visitsRes.ok) throw new Error('backend request failed');
			pets = await petsRes.json();
			visits = await visitsRes.json();
			robots = robotsRes.ok ? await robotsRes.json() : [];
			events = eventsRes.ok ? await eventsRes.json() : [];
			error = '';
		} catch (e) {
			error = 'Could not load kitties data — is the backend running?';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadAll();
		loadPhotos();
		timer = setInterval(loadAll, 10000);
	});

	// Anomaly tab (v071): resolve one event. `choice` is a pet id (log it as
	// that cat's visit), or "refill" / "maintenance" / "dismiss".
	async function resolveEvent(ev, choice) {
		let body;
		if (choice === 'refill' || choice === 'maintenance' || choice === 'dismiss') {
			body = { resolution: choice };
		} else if (choice) {
			body = { resolution: 'cat_visit', pet_id: choice };
		} else {
			return;
		}
		try {
			const res = await fetch(`/api/events/${encodeURIComponent(ev.id)}/resolve`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) throw new Error('resolve failed');
			resolveError = '';
			// Drop the resolved event locally; a cat visit also reloads the
			// visits (and the graph) via a full reload.
			events = events.filter((e) => e.id !== ev.id);
			if (body.resolution === 'cat_visit') loadAll();
		} catch (e) {
			resolveError = 'Could not save — try again.';
		}
	}

	async function loadPhotos() {
		try {
			const res = await fetch('/api/pet-photos');
			if (res.ok) photos = await res.json();
		} catch (e) {
			// no photos yet -- the cards still render, they just show 📷
		}
	}

	async function uploadPhoto(pet, file) {
		if (!file) return;
		const body = new FormData();
		body.append('file', file);
		try {
			const res = await fetch(`/api/pets/${encodeURIComponent(pet.id)}/photo`, {
				method: 'POST',
				body
			});
			if (!res.ok) throw new Error('upload failed');
			const data = await res.json();
			photos = { ...photos, [pet.id]: data.photo };
		} catch (e) {
			error = 'Could not save the photo — try again.';
		}
	}

	async function removePhoto(pet) {
		try {
			const res = await fetch(`/api/pets/${encodeURIComponent(pet.id)}/photo`, { method: 'DELETE' });
			if (!res.ok) throw new Error('remove failed');
			const { [pet.id]: _, ...rest } = photos;
			photos = rest;
		} catch (e) {
			error = 'Could not remove the photo — try again.';
		}
	}

	const EVENT_LABELS = {
		unmatched_arrival: 'Unmatched arrival',
		ambiguous_arrival: 'Ambiguous',
		unmatched_weight_change: 'Weight change',
		interruption: 'Interrupted',
		back_to_back: 'Back-to-back',
		refill: 'Refill',
		auto_reset: 'Auto reset',
		two_cat_sum: 'Two cats?'
	};

	function eventLabel(ev) {
		return EVENT_LABELS[ev.type] || ev.type;
	}

	onDestroy(() => clearInterval(timer));

	// Age from birthdate, computed on every render — so it ticks up on its
	// own as the cat gets older, like the Whisker app. No stored age to go stale.
	function ageLabel(birthdate) {
		if (!birthdate) return '—';
		const born = new Date(birthdate + 'T00:00:00');
		if (isNaN(born)) return '—';
		const now = new Date();
		let months =
			(now.getFullYear() - born.getFullYear()) * 12 + (now.getMonth() - born.getMonth());
		if (now.getDate() < born.getDate()) months -= 1;
		if (months < 0) return '—';
		if (months < 12) return months === 1 ? '1 mo' : `${months} mos`;
		const years = Math.floor(months / 12);
		const rest = months % 12;
		return rest === 0
			? `${years} yr${years === 1 ? '' : 's'}`
			: `${years} yr${years === 1 ? '' : 's'} ${rest} mo${rest === 1 ? '' : 's'}`;
	}

	async function addPet() {
		addError = '';
		const weight = parseFloat(newWeight);
		if (!newName.trim()) {
			addError = 'Give the kitty a name.';
			return;
		}
		if (isNaN(weight) || weight <= 0) {
			addError = 'Weight needs to be a number, in lbs.';
			return;
		}
		const res = await fetch('/api/pets', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				name: newName.trim(),
				weight,
				birthdate: newBirthdate || null,
				color: newColor
			})
		});
		if (!res.ok) {
			addError = 'Could not add pet.';
			return;
		}
		newName = '';
		newWeight = '';
		newBirthdate = '';
		showForm = false;
		await loadAll();
	}

	async function deletePet(id, name) {
		if (!confirm(`Remove ${name}? Their past visits stay in the log as-is.`)) return;
		await fetch(`/api/pets?id=${encodeURIComponent(id)}`, { method: 'DELETE' });
		await loadAll();
	}

	async function changePetColor(pet, color) {
		const res = await fetch('/api/pets', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				id: pet.id,
				name: pet.name,
				weight: pet.weight,
				birthdate: pet.birthdate || null,
				color
			})
		});
		if (res.ok) {
			colorPickerFor = null;
			await loadAll();
		}
	}

	async function reassign(visit, petName) {
		await fetch('/api/visits/reassign', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ id: visit.id, pet: petName || null })
		});
		await loadAll();
	}

	function boxLabel(v) {
		if (!v.serial) return v.robot ?? '—';
		const r = robots.find((x) => x.serial === v.serial);
		if (r && r.name && r.name !== v.serial) return `${r.name} (${v.serial})`;
		return v.serial;
	}

	// Name only, never the serial — for the kitty cards (and tooltips).
	// Looks the box up by serial; falls back to matching the stored
	// `robot` value itself (old manual visits stored the serial there).
	function boxName(v) {
		if (!v) return '—';
		const r = robots.find((x) => x.serial === v.serial || x.serial === v.robot);
		if (r && r.name && r.name !== v.serial) return r.name;
		return v.robot ?? '—';
	}

	async function deleteVisit(visit) {
		if (!confirm(`Delete the ${visit.pet ?? 'Unknown'} visit (${visit.weight ?? '?'} lbs)? This cannot be undone.`)) return;
		await fetch(`/api/visits/${visit.id}`, { method: 'DELETE' });
		await loadAll();
	}

	function lastVisitFor(petName) {
		return visits.find((v) => v.pet === petName);
	}

	function fmtTime(iso) {
		if (!iso) return '—';
		return new Date(iso).toLocaleString([], {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit'
		});
	}

	// Short date for the kitty cards: "MM/DD @ h:mm AM". The full
	// "Mon, Nov 16, 11:30 AM" string was too long on a card.
	function fmtShort(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		if (isNaN(d.getTime())) return '—';
		let h = d.getHours();
		const ampm = h >= 12 ? 'PM' : 'AM';
		h = h % 12 || 12;
		const min = String(d.getMinutes()).padStart(2, '0');
		return `${d.getMonth() + 1}/${d.getDate()} @ ${h}:${min} ${ampm}`;
	}

	function matchLabel(v) {
		if (v.manual && v.pet) return v.pet + ' ✓';
		if (v.pet) return v.pet;
		if (v.ambiguous && v.ambiguous.length) return v.ambiguous.join(' or ');
		return 'Unknown';
	}

	// ---- graph toggles (the cards are the legend) ----

	function toggleCat(name) {
		hiddenCats = { ...hiddenCats, [name]: !hiddenCats[name] };
	}

	function showAll() {
		hiddenCats = {};
	}

	$: anyHidden = Object.values(hiddenCats).some(Boolean);
	$: sortedPets = [...pets].sort((a, b) => a.name.localeCompare(b.name));

	// ---- visits table range (its own, separate from the graph's) ----

	function msFor(iso) {
		if (!iso) return 0;
		const [y, m, d] = iso.split('-').map(Number);
		return new Date(y, m - 1, d).getTime();
	}

	$: rangedVisits = visits.filter((v) => {
		const t = new Date(v.timestamp).getTime();
		if (isNaN(t)) return false;
		if (visitFromISO && t < msFor(visitFromISO)) return false;
		if (visitToISO && t >= msFor(visitToISO) + DAY) return false;
		return true;
	});

	$: filteredVisits =
		filterPet === 'all' ? rangedVisits : rangedVisits.filter((v) => v.pet === filterPet);
</script>

<section class="mt-8">
	{#if loading}
		<p>Loading kitties…</p>
	{:else if error}
		<div class="alert alert-error mb-4">{error}</div>
	{:else}
		<div class="flex flex-col lg:flex-row gap-6 items-stretch">
			<!-- Left column: kitties stacked vertically. Click a card to
			     hide/show that kitty on the graph. -->
			<div class="w-full lg:w-80 shrink-0 flex items-start gap-2">
				<h2 class="shrink-0 text-2xl font-bold [writing-mode:vertical-rl] rotate-180">Kitties</h2>
				<div class="min-w-0 flex-1 flex flex-col gap-3">

				{#if pets.length === 0 && !showForm}
					<!-- Empty state: no cats yet, nothing hard-coded -->
					<div class="card bg-base-100 shadow">
						<div class="card-body items-center text-center">
							<p class="text-lg">No kitties yet — who uses these boxes?</p>
							<button class="btn btn-primary" on:click={() => (showForm = true)}>
								Add kitty?
							</button>
						</div>
					</div>
				{/if}

				{#if showForm}
					<!-- Add pet form -->
					<div class="card bg-base-100 shadow">
						<div class="card-body py-4">
							<h3 class="font-bold">Add a kitty</h3>
							<div class="flex flex-wrap gap-3 items-end">
								<label class="form-control">
									<span class="label-text">Name</span>
									<input
										class="input input-bordered input-sm"
										bind:value={newName}
										placeholder="e.g. Miso"
									/>
								</label>
								<label class="form-control">
									<span class="label-text">Usual weight (lbs)</span>
									<input
										class="input input-bordered input-sm w-28"
										bind:value={newWeight}
										inputmode="decimal"
										placeholder="e.g. 9.5"
									/>
								</label>
								<label class="form-control">
									<span class="label-text">Birthday (for age)</span>
									<input
										type="date"
										class="input input-bordered input-sm"
										bind:value={newBirthdate}
									/>
								</label>
								<label class="form-control">
									<span class="label-text">Colour</span>
									<span class="flex items-center gap-2">
										<input
											type="color"
											class="w-10 h-8 p-0 border-0 bg-transparent cursor-pointer"
											bind:value={newColor}
										/>
										<span class="flex gap-1">
											{#each PRESET_COLORS as c (c)}
												<button
													type="button"
													class="w-5 h-5 rounded-full border"
													class:ring-2={newColor === c}
													class:ring-offset-1={newColor === c}
													style="background: {c}"
													title={c}
													on:click={() => (newColor = c)}
												/>
											{/each}
										</span>
									</span>
								</label>
								<button class="btn btn-primary btn-sm" on:click={addPet}>Add kitty</button>
								<button class="btn btn-ghost btn-sm" on:click={() => (showForm = false)}>
									Cancel
								</button>
							</div>
							{#if addError}
								<p class="text-error text-sm mt-2">{addError}</p>
							{/if}
							<p class="text-xs opacity-60 mt-2">
								Birthday is optional — without it, age just shows as a dash. Colour is
								used on the card and on the graphs. Visits are matched to the
								closest-weight pet within 0.75 lbs; if two pets fit, the visit shows
								both names instead of a forced guess — correct it below and the fix sticks.
							</p>
						</div>
					</div>
				{/if}

				<!-- Per-cat cards, stacked — click to hide/show on the graph -->
				{#each sortedPets as pet (pet.id)}
					{@const last = lastVisitFor(pet.name)}
					<div
						class="card relative bg-base-100 shadow border-l-4 cursor-pointer select-none"
						class:opacity-40={hiddenCats[pet.name]}
						style="border-left-color: {pet.color || '#888'}"
						role="button"
						tabindex="0"
						title="Click to hide/show {pet.name} on the graph"
						on:click={() => toggleCat(pet.name)}
						on:keydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								toggleCat(pet.name);
							}
						}}
					>
						<div class="card-body">
							<div class="flex justify-between items-start">
								<h3 class="card-title">
									<span
										class="inline-block w-3 h-3 rounded"
										style="background: {pet.color || '#888'}"
									></span>
									<span class:line-through={hiddenCats[pet.name]}>{pet.name}</span>
								</h3>
								<div class="flex gap-1">
									<button
										class="btn btn-ghost btn-xs"
										title="Change {pet.name}'s colour"
										on:click|stopPropagation={() => (colorPickerFor = colorPickerFor === pet.id ? null : pet.id)}
									>⚙</button
									>
									<button
										class="btn btn-ghost btn-xs"
										title="Remove {pet.name}"
										on:click|stopPropagation={() => deletePet(pet.id, pet.name)}>✕</button
									>
								</div>
							</div>
							{#if colorPickerFor === pet.id}
								<div class="flex flex-wrap items-center gap-2 mt-1" on:click|stopPropagation>
									{#each PRESET_COLORS as c (c)}
										<button
											type="button"
											class="w-6 h-6 rounded-full border"
											class:ring-2={pet.color === c}
											class:ring-offset-1={pet.color === c}
											style="background: {c}"
											title={c}
											on:click|stopPropagation={() => changePetColor(pet, c)}
										/>
									{/each}
								</div>
							{/if}
							<p class="text-sm opacity-70">Average weight: {pet.average_weight ?? pet.weight} lbs</p>
							<p class="text-sm opacity-70">Age: {ageLabel(pet.birthdate)}</p>
							{#if last}
								<p class="relative z-10">
									Last weight: <strong>{last.weight != null ? last.weight + ' lbs' : '—'}</strong>
								</p>
								<p class="relative z-10">Last visit: {fmtShort(last.timestamp)}</p>
								<p class="relative z-10">Box used: {boxName(last)}</p>
							{:else}
								<p class="text-sm opacity-70 relative z-10">No visits logged yet.</p>
							{/if}
							{#if hiddenCats[pet.name]}
								<p class="relative z-10"><span class="badge badge-ghost badge-sm">Hidden from graph</span></p>
							{/if}
							{#if photos[pet.id]}
								<div class="absolute bottom-3 right-3">
									<label class="cursor-pointer" title="Change {pet.name}'s photo" on:click|stopPropagation>
										<img src="/api/pets/{pet.id}/photo" alt="{pet.name}" class="h-16 w-16 rounded-full object-cover ring-2 ring-base-300" />
										<input type="file" accept="image/*" class="hidden" on:change={(e) => uploadPhoto(pet, e.target.files[0])} />
									</label>
									<button class="btn btn-circle btn-xs absolute -top-1 -right-1" title="Remove {pet.name}'s photo" on:click|stopPropagation={() => removePhoto(pet)}>✕</button>
								</div>
							{:else}
								<label class="absolute bottom-3 right-3 btn btn-circle btn-sm btn-ghost cursor-pointer" title="Add a photo of {pet.name}" on:click|stopPropagation>
									📷
									<input type="file" accept="image/*" class="hidden" on:change={(e) => uploadPhoto(pet, e.target.files[0])} />
								</label>
							{/if}
						</div>
					</div>
				{/each}

				{#if pets.length > 0 && !showForm}
					<button
						class="btn btn-primary btn-sm self-start"
						on:click={() => (showForm = true)}
					>
						+ Add kitty
					</button>
				{/if}
				{#if anyHidden}
					<button class="btn btn-ghost btn-xs self-start" on:click={showAll}>
						Show all on graph
					</button>
				{/if}
				<p class="text-xs opacity-50">
					Click a kitty to hide or show them on the graph.
				</p>
				</div>
			</div>

			<!-- Right: the graph, using the horizontal space -->
			<div class="flex-1 min-w-0 w-full flex flex-col">
				<CatGraphs {hiddenCats} />
			</div>
		</div>

		<!-- Visit history, full width below the graph, with its own range -->
		<div class="card bg-base-100 shadow mt-6">
			<div class="card-body">
				<div class="flex flex-wrap justify-between items-center gap-2 mb-2">
					<div role="tablist" class="tabs tabs-boxed">
						<a role="tab" class="tab" class:tab-active={activeTab === 'average'} on:click={() => (activeTab = 'average')}>Average Weight</a>
						<a role="tab" class="tab" class:tab-active={activeTab === 'visits'} on:click={() => (activeTab = 'visits')}>Recent visits</a>
						<a role="tab" class="tab" class:tab-active={activeTab === 'anomalies'} on:click={() => (activeTab = 'anomalies')}>Anomalies{#if unresolvedEvents.length > 0} ({unresolvedEvents.length}){/if}</a>
					</div>
					{#if activeTab === 'visits'}
						<label class="flex items-center gap-2 text-sm">
							Show
							<select class="select select-bordered select-sm" bind:value={filterPet}>
								<option value="all">All kitties</option>
								{#each pets as pet (pet.id)}
									<option value={pet.name}>{pet.name}</option>
								{/each}
							</select>
						</label>
					{/if}
				</div>

				<!-- Average Weight tab: its own block so the visits/anomalies chain stays untouched. -->
				{#if activeTab === 'average'}
					<AvgWeightGraph {hiddenCats} />
				{/if}

				{#if activeTab === 'visits'}
				<DateRangePicker bind:fromISO={visitFromISO} bind:toISO={visitToISO} {visits} />

				{#if visits.length === 0}
					<p class="text-sm opacity-70">
						No visits yet — the log starts filling in as the boxes cycle. History builds
						from here.
					</p>
				{:else if filteredVisits.length === 0}
					<p class="text-sm opacity-70">
						No visits in this range — slide it wider or pick All.
					</p>
				{:else}
					<p class="text-xs opacity-60 mb-2">
						{filteredVisits.length} visit{filteredVisits.length === 1 ? '' : 's'} in
						range{filteredVisits.length > 50 ? ' — showing the newest 50' : ''}.
					</p>
					<div class="overflow-x-auto">
						<table class="table table-sm">
							<thead>
								<tr>
									<th>When</th>
									<th>Kitty</th>
									<th>Weight</th>
									<th>Box</th>
									<th>Type</th>
									<th>Correct it</th>
									<th>Delete</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredVisits.slice(0, 50) as v (v.id)}
									<tr>
										<td>{fmtTime(v.timestamp)}</td>
										<td>
											<span
												class="badge"
												class:badge-warning={!v.pet}
												class:badge-ghost={!!v.pet}>{matchLabel(v)}</span
											>
										</td>
										<td>{v.weight != null ? v.weight + ' lbs' : '—'}</td>
										<td>{boxLabel(v)}</td>
										<td>
											<select
												class="select select-bordered select-xs"
												value={v.type ?? ''}
												on:change={async (e) => {
													const t = e.target.value || null;
													const r = await fetch(`/api/visits/${v.id}/type`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: t }) });
													if (r.ok) { v.type = t; visits = visits; }
												}}
											>
												<option value="">—</option>
												<option value="pee">Pee</option>
												<option value="poop">Poop</option>
											</select>
										</td>
										<td>
											<select
												class="select select-bordered select-xs"
												value={v.pet ?? ''}
												on:change={(e) => reassign(v, e.target.value)}
											>
												<option value="" disabled={!!v.pet && !v.manual}
													>{v.pet ? '—' : 'Who was it?'}</option
												>
												{#each pets as pet (pet.id)}
													<option value={pet.name}>{pet.name}</option>
												{/each}
												<option value="">Unknown</option>
											</select>
										</td>
										<td>
											<button class="btn btn-ghost btn-xs text-error" on:click={() => deleteVisit(v)} title="Delete this visit">✕</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{:else if activeTab === 'anomalies'}
				{#if resolveError}
					<p class="text-error text-sm mb-2">{resolveError}</p>
				{/if}
				{#if unresolvedEvents.length === 0}
					<p class="text-sm opacity-70">No anomalies — every logged event is resolved. New ones land here as the boxes cycle.</p>
				{:else}
					<p class="text-xs opacity-60 mb-2">{unresolvedEvents.length} unresolved event{unresolvedEvents.length === 1 ? '' : 's'} — pick a cat to log it as their visit, or mark it refill / maintenance / dismiss.</p>
					<div class="overflow-x-auto">
						<table class="table table-sm">
							<thead>
								<tr>
									<th>When</th>
									<th>Weight</th>
									<th>Box</th>
									<th>Type</th>
									<th>Note</th>
									<th>Resolve</th>
								</tr>
							</thead>
							<tbody>
								{#each unresolvedEvents as ev (ev.id)}
									<tr>
										<td>{fmtTime(ev.timestamp)}</td>
										<td>{ev.weight != null ? ev.weight + ' lbs' : '—'}</td>
										<td>{ev.robot || ev.serial}</td>
										<td>{eventLabel(ev)}</td>
										<td class="text-xs opacity-70">{ev.note || ''}</td>
										<td>
											<select class="select select-bordered select-xs" value="" on:change={(e) => resolveEvent(ev, e.target.value)}>
												<option value="" disabled>Resolve…</option>
												{#each pets as pet (pet.id)}
													<option value={pet.id}>{pet.name} (visit)</option>
												{/each}
												<option value="refill">Refill</option>
												<option value="maintenance">Maintenance</option>
												<option value="dismiss">Dismiss</option>
											</select>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{/if}
			</div>
		</div>
	{/if}
</section>

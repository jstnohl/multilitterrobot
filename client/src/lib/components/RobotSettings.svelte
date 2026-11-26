<script>
	import { onMount } from 'svelte';
	import RobotBoxColor from './RobotBoxColor.svelte';

	// RobotSettings (v074, 0.6.13; badge trigger since the header merge):
	// settings menu for one robot card, opened from the Online badge.
	// Robot settings go to the robot (cycle delay, panel lock, sleep
	// toggle); filter date, litter type and floor surface are local
	// app-side settings kept in settings.json. Robot toggles update
	// optimistically -- the cloud queues commands, so a refresh right
	// after the call would show the old value.
	export let serial;
	export let isOnline = true;

	let open = false;
	let loading = false;
	let error = '';
	let settings = null;
	let firmware = null;
	let updating = false;
	let confirmUpdate = false;
	let refills = [];
	let showRefillForm = false;
	let refillLbs = '';
	let refillSaving = false;

	onMount(loadFirmware);
	let saving = {};

	function toggle() {
		open = !open;
		if (open && !settings) load();
		if (open && !firmware) loadFirmware();
		if (open) loadRefills();
		if (!open) confirmUpdate = false;
	}

	async function load() {
		loading = true;
		error = '';
		try {
			const res = await fetch(`/api/robot/${serial}/settings`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			settings = await res.json();
		} catch (e) {
			error = 'Could not load settings';
		} finally {
			loading = false;
		}
	}

	async function loadFirmware() {
		try {
			const res = await fetch(`/api/robot/${serial}/firmware`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			firmware = await res.json();
		} catch (e) {
			firmware = null;
		}
	}

	function fmtMD(iso) {
		if (!iso) return '—';
		const d = new Date(iso);
		if (isNaN(d.getTime())) return '—';
		return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
	}

	// v084: the three Litter lines, from the refills list (newest first).
	function computeLitterStats(list) {
		const out = { refillDate: '—', estimateRefill: '—', monthlyUse: '0.0 lbs' };
		if (!list || list.length === 0) return out;
		out.refillDate = fmtMD(list[0].timestamp);
		const ts = list
			.map((r) => new Date(r.timestamp).getTime())
			.filter((t) => !isNaN(t))
			.sort((a, b) => a - b);
		if (ts.length >= 2) {
			let gapSum = 0;
			for (let k = 1; k < ts.length; k++) gapSum += (ts[k] - ts[k - 1]) / 86400000;
			const avg = gapSum / (ts.length - 1);
			const last = new Date(list[0].timestamp);
			if (!isNaN(last.getTime())) out.estimateRefill = fmtMD(new Date(last.getTime() + avg * 86400000).toISOString());
		}
		const now = new Date();
		let sum = 0;
		for (const r of list) {
			if (r.weight_lbs == null || isNaN(r.weight_lbs)) continue;
			const d = new Date(r.timestamp);
			if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) sum += r.weight_lbs;
		}
		out.monthlyUse = sum.toFixed(1) + ' lbs';
		return out;
	}

	$: litterStats = computeLitterStats(refills);

	async function loadRefills() {
		try {
			const res = await fetch(`/api/refills?serial=${encodeURIComponent(serial)}&limit=100`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			refills = await res.json();
		} catch (e) {
			refills = [];
		}
	}

	async function saveRefill() {
		const lbs = parseFloat(refillLbs);
		if (isNaN(lbs) || lbs <= 0) {
			error = 'Enter the litter weight in lbs';
			return;
		}
		refillSaving = true;
		error = '';
		try {
			const res = await fetch('/api/refills', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ serial, weight_lbs: lbs })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			refillLbs = '';
			showRefillForm = false;
			await loadRefills();
		} catch (e) {
			error = 'Could not save the refill — try again';
		} finally {
			refillSaving = false;
		}
	}


	async function startUpdate() {
		if (!confirmUpdate) {
			confirmUpdate = true;
			return;
		}
		confirmUpdate = false;
		updating = true;
		try {
			const res = await fetch(`/api/robot/${serial}/firmware/update`, { method: 'POST' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			firmware = { ...firmware, update_triggered: true };
		} catch (e) {
			error = 'Could not start the update — try again';
		} finally {
			updating = false;
		}
	}

	async function postRobot(path, body, key, value) {
		const prev = settings[key];
		settings = { ...settings, [key]: value };
		saving = { ...saving, [key]: true };
		try {
			const res = await fetch(`/api/robot/${serial}/${path}`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch (e) {
			settings = { ...settings, [key]: prev };
			error = 'Could not save — try again';
		} finally {
			saving = { ...saving, [key]: false };
		}
	}

	async function postLocal(patch) {
		try {
			const res = await fetch(`/api/robot/${serial}/settings`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(patch)
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			settings = { ...settings, ...data.settings };
		} catch (e) {
			error = 'Could not save — try again';
		}
	}

	async function postLight(mode) {
		const prev = settings.night_light_mode;
		settings = { ...settings, night_light_mode: mode };
		saving = { ...saving, night_light_mode: true };
		try {
			const res = await fetch(`/api/robot/${serial}/light?mode=${mode}`, { method: 'POST' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch (e) {
			settings = { ...settings, night_light_mode: prev };
			error = 'Could not save — try again';
		} finally {
			saving = { ...saving, night_light_mode: false };
		}
	}

	async function postBrightness(level) {
		const brightness = { LOW: 25, MEDIUM: 50, HIGH: 100 }[level];
		if (brightness === undefined) return;
		const prev = settings.night_light_brightness;
		const prevLevel = settings.night_light_level;
		settings = { ...settings, night_light_brightness: brightness, night_light_level: level };
		saving = { ...saving, night_light_brightness: true };
		try {
			const res = await fetch(`/api/robot/${serial}/night-light-brightness`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ brightness })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch (e) {
			settings = { ...settings, night_light_brightness: prev, night_light_level: prevLevel };
			error = 'Could not save — try again';
		} finally {
			saving = { ...saving, night_light_brightness: false };
		}
	}

	async function postPanelBrightness(level) {
		const prev = settings.panel_brightness;
		settings = { ...settings, panel_brightness: level };
		saving = { ...saving, panel_brightness: true };
		try {
			const res = await fetch(`/api/robot/${serial}/panel-brightness`, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ level })
			});
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
		} catch (e) {
			settings = { ...settings, panel_brightness: prev };
			error = 'Could not save — try again';
		} finally {
			saving = { ...saving, panel_brightness: false };
		}
	}

	function filterAge() {
		if (!settings?.filter_replaced) return '';
		const d = new Date(settings.filter_replaced + 'T00:00:00');
		const days = Math.floor((Date.now() - d.getTime()) / 86400000);
		if (days < 0) return ' (in the future?)';
		if (days === 0) return ' (today)';
		if (days === 1) return ' (yesterday)';
		return ` (${days} days ago)`;
	}

	function markFilterToday() {
		const today = new Date().toISOString().slice(0, 10);
		settings = { ...settings, filter_replaced: today };
		postLocal({ filter_replaced: today });
	}
</script>

<div class="relative">
	<button
		class="badge gap-2 {firmware?.has_update ? 'badge-warning' : isOnline ? 'badge-success' : 'badge-error'}"
		on:click={toggle}
		aria-label="Robot settings"
		title="Robot settings"
	>
		{#if firmware?.has_update}↑ Update available{:else if isOnline}Online{:else}Offline{/if}
	</button>
	{#if open}
		<div
			class="absolute right-0 top-full z-50 mt-1 w-72 rounded-box border border-base-300 bg-base-100 p-4 shadow-xl"
		>
			{#if loading}
				<p class="text-sm opacity-70">Loading settings…</p>
			{:else if settings}
				<div class="divider mt-0 mb-3">Box colour</div>
				<RobotBoxColor {serial} inline />
				<div class="form-control mb-3">
					<label class="label py-0" for="wait-{serial}">
						<span class="label-text">Cycle delay</span>
					</label>
					<select
						id="wait-{serial}"
						class="select select-bordered select-sm w-full"
						disabled={saving.wait_time_minutes || settings.wait_time_minutes === null}
						value={settings.wait_time_minutes ?? ''}
						on:change={(e) => {
							const minutes = +e.target.value;
							postRobot('wait-time', { minutes }, 'wait_time_minutes', minutes);
						}}
					>
						{#each settings.valid_wait_times ?? [3, 7, 15, 30] as m}
							<option value={m}>{m} min</option>
						{/each}
					</select>
				</div>
				<div class="form-control mb-3">
					<label class="label cursor-pointer justify-start gap-3 py-0">
						<input
							type="checkbox"
							class="toggle toggle-sm"
							disabled={saving.panel_lock_enabled || settings.panel_lock_enabled === null}
							checked={settings.panel_lock_enabled ?? false}
							on:change={(e) =>
								postRobot(
									'panel-lock',
									{ enabled: e.target.checked },
									'panel_lock_enabled',
									e.target.checked
								)}
						/>
						<span class="label-text">Panel lock</span>
					</label>
				</div>
				<div class="form-control mb-3">
					<label class="label cursor-pointer justify-start gap-3 py-0">
						<input
							type="checkbox"
							class="toggle toggle-sm"
							disabled={saving.sleep_mode_enabled || settings.sleep_mode_enabled === null}
							checked={settings.sleep_mode_enabled ?? false}
							on:change={(e) =>
								postRobot(
									'sleep-mode',
									{ enabled: e.target.checked },
									'sleep_mode_enabled',
									e.target.checked
								)}
						/>
						<span class="label-text">Sleep mode</span>
					</label>
					<p class="text-xs opacity-60">Uses the schedule set in the Whisker app.</p>
				</div>
				<div class="form-control mb-3">
					<label class="label py-0" for="light-{serial}">
						<span class="label-text">Night light</span>
					</label>
					<select
						id="light-{serial}"
						class="select select-bordered select-sm w-full"
						disabled={saving.night_light_mode || settings.night_light_mode === null}
						value={settings.night_light_mode ?? 'AUTO'}
						on:change={(e) => postLight(e.target.value)}
					>
						<option value="ON">On</option>
						<option value="OFF">Off</option>
						<option value="AUTO">Auto</option>
					</select>
					<label class="label py-0 mt-2" for="brightness-{serial}">
						<span class="label-text">Brightness</span>
					</label>
					<select
						id="brightness-{serial}"
						class="select select-bordered select-sm w-full"
						disabled={saving.night_light_brightness || (settings.night_light_level === null && settings.night_light_brightness === null)}
						value={settings.night_light_level ?? ({ 25: 'LOW', 50: 'MEDIUM', 100: 'HIGH' }[settings.night_light_brightness] ?? 'HIGH')}
						on:change={(e) => postBrightness(e.target.value)}
					>
						<option value="LOW">Low</option>
						<option value="MEDIUM">Medium</option>
						<option value="HIGH">High</option>
					</select>
				</div>
				<div class="form-control mb-3">
					<label class="label py-0" for="panel-brightness-{serial}">
						<span class="label-text">Panel brightness</span>
					</label>
					<select
						id="panel-brightness-{serial}"
						class="select select-bordered select-sm w-full"
						disabled={saving.panel_brightness || settings.panel_brightness === null}
						value={settings.panel_brightness ?? 'HIGH'}
						on:change={(e) => postPanelBrightness(e.target.value)}
					>
						<option value="LOW">Low</option>
						<option value="MEDIUM">Medium</option>
						<option value="HIGH">High</option>
					</select>
				</div>
				<div class="form-control mb-3">
					<label class="label py-0" for="filter-{serial}">
						<span class="label-text">Carbon filter replaced{filterAge()}</span>
					</label>
					<div class="flex gap-2">
						<input
							id="filter-{serial}"
							type="date"
							class="input input-bordered input-sm w-full"
							value={settings.filter_replaced ?? ''}
							on:change={(e) => postLocal({ filter_replaced: e.target.value || null })}
						/>
						<button class="btn btn-sm" on:click={markFilterToday}>Today</button>
					</div>
				</div>
				<div class="form-control mb-3">
					<label class="label py-0" for="litter-{serial}">
						<span class="label-text">Litter type</span>
					</label>
					<input
						id="litter-{serial}"
						type="text"
						class="input input-bordered input-sm w-full"
						placeholder="e.g. clay"
						value={settings.litter_type ?? ''}
						on:change={(e) => postLocal({ litter_type: e.target.value || null })}
					/>
				</div>
				<div class="form-control">
					<label class="label py-0" for="floor-{serial}">
						<span class="label-text">Floor surface</span>
					</label>
					<input
						id="floor-{serial}"
						type="text"
						class="input input-bordered input-sm w-full"
						placeholder="e.g. hardwood"
						value={settings.floor_surface ?? ''}
						on:change={(e) => postLocal({ floor_surface: e.target.value || null })}
					/>
				</div>
				<!-- v084-refill-ui: Litter section -->
				<div class="divider my-3">Litter</div>
				<div class="text-sm leading-relaxed">
					Refill date: {litterStats.refillDate}<br />
					Estimate refill: {litterStats.estimateRefill}<br />
					Monthly litter use: {litterStats.monthlyUse}
				</div>
				{#if showRefillForm}
					<div class="mt-2 flex gap-2">
						<input type="number" min="0" step="0.1" class="input input-bordered input-sm w-24" placeholder="lbs" bind:value={refillLbs} />
						<button class="btn btn-primary btn-sm" disabled={refillSaving} on:click={saveRefill}>Save refill</button>
						<button class="btn btn-ghost btn-sm" on:click={() => (showRefillForm = false)}>Cancel</button>
					</div>
				{:else}
					<button class="btn btn-primary btn-sm mt-2" on:click={() => (showRefillForm = true)}>Log refill today</button>
				{/if}
				<div class="divider my-3">Firmware</div>
				{#if firmware}
					<p class="text-sm">Installed: {firmware.installed ?? 'unknown'}</p>
					{#if firmware.has_update}
						<p class="text-sm">Latest: {firmware.latest ?? 'unknown'}</p>
						{#if firmware.update_triggered}
							<p class="mt-1 text-sm text-warning">Update in progress — up to 15 minutes. Do not unplug the box.</p>
						{:else}
							<button class="btn btn-warning btn-sm mt-2" disabled={updating} on:click={startUpdate}>
								{confirmUpdate ? 'Tap again to confirm' : 'Update firmware'}
							</button>
						{/if}
					{:else if firmware.has_update === false}
						<p class="text-sm opacity-60">Up to date.</p>
					{:else}
						<p class="text-sm opacity-60">Update status unknown.</p>
					{/if}
				{:else}
					<p class="text-sm opacity-60">Firmware info unavailable.</p>
				{/if}
			{/if}
			{#if error}
				<p class="mt-2 text-sm text-error">{error}</p>
			{/if}
		</div>
	{/if}
</div>

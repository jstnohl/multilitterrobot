<script lang="ts">
	import daisyuiColors from 'daisyui/src/theming/themes';
	import Icon from '@iconify/svelte';
	import { selectedTheme } from '$lib/store';
	import { onMount } from 'svelte';
	import { computeAlerts, buildExportCSV, downloadCSV } from '$lib/insights';

	let themes = Object.keys(daisyuiColors);

	// Read the selected theme from local storage or cookies when the component mounts
	onMount(() => {
		const storedTheme = localStorage.getItem('selectedTheme');
		if (storedTheme && themes.includes(storedTheme)) {
			selectedTheme.set(storedTheme);
			document.documentElement.setAttribute('data-theme', storedTheme);
		}
	});

	// Function to handle theme selection
	function handleThemeChange(event: any) {
		const theme = event.target.value;
		selectedTheme.set(theme);
		// Save the selected theme to local storage or cookies
		localStorage.setItem('selectedTheme', theme);
	}
	// --- v084: alerts bell + export (right of the credits) ---
	let pets: any[] = [];
	let alerts: any[] = [];
	let dismissed: string[] = [];
	let showAlerts = false;
	let showExport = false;
	let exportCat = '';
	let incVisits = true;
	let incWeights = true;
	let incAverages = true;
	let incEvents = true;
	let alertTimer: any;

	function loadDismissed() {
		try {
			dismissed = JSON.parse(localStorage.getItem('dismissedAlerts') || '[]');
		} catch {
			dismissed = [];
		}
	}

	function visibleAlerts() {
		return alerts.filter((a) => !dismissed.includes(a.key));
	}

	async function loadAlerts() {
		try {
			const [pr, vr] = await Promise.all([fetch('/api/pets'), fetch('/api/visits?limit=500')]);
			if (!pr.ok || !vr.ok) return;
			pets = await pr.json();
			const visits = await vr.json();
			alerts = computeAlerts(pets, visits, Date.now());
		} catch {
			/* alerts stay as-is on failure */
		}
	}

	function toggleAlerts() {
		showAlerts = !showAlerts;
		if (showAlerts) {
			showExport = false;
			loadAlerts();
		}
	}

	function toggleExport() {
		showExport = !showExport;
		if (showExport) showAlerts = false;
	}

	function dismissAlert(key: string) {
		dismissed = [...dismissed, key];
		try {
			localStorage.setItem('dismissedAlerts', JSON.stringify(dismissed));
		} catch {}
	}

	function clearAllAlerts() {
		for (const a of visibleAlerts()) dismissAlert(a.key);
	}

	async function doExport() {
		try {
			const [pr, vr, er] = await Promise.all([
				fetch('/api/pets'),
				fetch('/api/visits?limit=500'),
				fetch('/api/events?limit=500')
			]);
			const epets = pr.ok ? await pr.json() : pets;
			const visits = vr.ok ? await vr.json() : [];
			const events = er.ok ? await er.json() : [];
			const csv = buildExportCSV({
				pets: epets,
				visits,
				events,
				cat: exportCat,
				includeVisits: incVisits,
				includeWeights: incWeights,
				includeAverages: incAverages,
				includeEvents: incEvents
			});
			const stamp = new Date().toISOString().slice(0, 10);
			const name = exportCat
				? `multilitterrobot-${exportCat.toLowerCase()}-${stamp}.csv`
				: `multilitterrobot-export-${stamp}.csv`;
			downloadCSV(name, csv);
		} catch {
			/* export stays open on failure so the user can retry */
			return;
		}
		showExport = false;
	}

	loadDismissed();
	onMount(() => {
		loadAlerts();
		alertTimer = setInterval(loadAlerts, 60000);
		return () => clearInterval(alertTimer);
	});

</script>

<div class="bg-base-300 sticky top-0 -z-[-1] shadow">
	<div class="navbar bg-base-300 mx-auto flex max-w-6xl justify-between gap-2">
		<div class="flex items-center gap-2">
			<a href="/" class="btn btn-primary flex items-center text-xl">
				<Icon icon="fa6-solid:cat" class="h-7 w-7" />
				<div class="flex items-start gap-1">
					<div>multilitterrobot</div>
				</div>
			</a>

			<div class="dropdown dropdown-end">
				<div tabindex="0" role="button">
					<div class="lg:tooltip lg:tooltip-left" data-tip="Theme Selector">
						<button class="btn btn-ghost">
							<div class="font-normal lowercase">
								<Icon icon="gridicons-themes" class="h-7 w-7" />
							</div>
						</button>
					</div>
				</div>
				<ul
					tabindex="-1"
					class="dropdown-content dropdown-end rounded-box border-primary bg-base-100 -z-[-1] mt-3 h-96 w-52 overflow-auto border p-2 shadow"
				>
					{#each themes.sort() as theme}
						<li>
							<input
								type="radio"
								name="theme-dropdown"
								class="theme-controller btn btn-ghost btn-sm btn-block justify-start font-medium"
								aria-label={theme}
								value={theme}
								on:change={handleThemeChange}
							/>
						</li>
					{/each}
				</ul>
			</div>
		</div>

		<!-- v084-nav: bell + export -->
		<div class="flex items-center gap-2">
					<div class="text-right text-xs leading-tight opacity-70">
			<p>
				Made with ❤️ by
				<a href="https://github.com/jstnohl" class="link">Justin Ohl</a>
			&nbsp;
			</p>
			<p>
				Built with inspiration and code from:
				<a href="https://github.com/natekspencer/pylitterbot" class="link">pylitterbot</a>
				·
				<a href="https://github.com/engageintellect/litterbot" class="link">litterbot</a>
				·
				<a href="https://github.com/jstnohl/multilitterrobot" class="link">multilitterrobot</a>
			</p>
			</div>
			<div class="relative">
				<div class="lg:tooltip lg:tooltip-bottom" data-tip="Export Data as .CSV">
					<button class="btn btn-ghost" on:click={toggleExport} aria-label="Export data">
						<Icon icon="fa6-solid:download" class="h-6 w-6" />
					</button>
				</div>
				{#if showExport}
				<div class="absolute right-0 top-full z-50 mt-2 w-72 rounded-box border border-base-300 bg-base-100 p-3 shadow-xl">
					<div class="mb-2 text-sm font-bold">Export data</div>
					<label class="label py-1"><span class="label-text">Cat</span></label>
					<select class="select select-bordered select-sm w-full" bind:value={exportCat}>
						<option value="">All cats</option>
						{#each pets as p}<option value={p.name}>{p.name}</option>{/each}
					</select>
					<div class="label py-1"><span class="label-text">Include</span></div>
					<div class="flex flex-wrap gap-x-3 gap-y-1 text-sm">
						<label class="label cursor-pointer gap-1 py-0"><input type="checkbox" class="checkbox checkbox-sm" bind:checked={incVisits} /><span class="label-text">Visits</span></label>
						<label class="label cursor-pointer gap-1 py-0"><input type="checkbox" class="checkbox checkbox-sm" bind:checked={incWeights} /><span class="label-text">Weights</span></label>
						<label class="label cursor-pointer gap-1 py-0"><input type="checkbox" class="checkbox checkbox-sm" bind:checked={incAverages} /><span class="label-text">Rolling averages</span></label>
						<label class="label cursor-pointer gap-1 py-0"><input type="checkbox" class="checkbox checkbox-sm" bind:checked={incEvents} /><span class="label-text">Events</span></label>
					</div>
					<button class="btn btn-primary btn-sm mt-3 w-full" on:click={doExport}>Export</button>
				</div>
				{/if}
			</div>
			<div class="relative">
				<div class="lg:tooltip lg:tooltip-bottom" data-tip="Notifications">
					<button class="btn btn-ghost relative" on:click={toggleAlerts} aria-label="Notifications">
						<Icon icon="fa6-solid:bell" class="h-6 w-6" />
						{#if visibleAlerts().length > 0}
						<span class="badge badge-error badge-sm absolute -right-1 -top-1">{visibleAlerts().length}</span>
						{/if}
					</button>
				</div>
				{#if showAlerts}
				<div class="absolute right-0 top-full z-50 mt-2 w-80 rounded-box border border-base-300 bg-base-100 p-2 shadow-xl">
					{#if visibleAlerts().length === 0}
					<div class="p-2 text-sm opacity-70">No alerts — all clear.</div>
					{:else}
					{#each visibleAlerts() as a (a.key)}
					<div class="flex items-start gap-2 rounded-lg p-2 hover:bg-base-200">
						<span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-warning"></span>
						<div class="min-w-0 flex-1">
							<div class="text-sm font-semibold">{a.title}</div>
							<div class="text-xs opacity-70">{a.detail}</div>
						</div>
						<button class="btn btn-ghost btn-xs" on:click={() => dismissAlert(a.key)} aria-label="Dismiss">×</button>
					</div>
					{/each}
					<div class="flex items-center justify-between border-t border-base-300 px-2 pt-2 text-xs opacity-70">
						<span>{visibleAlerts().length} alert{visibleAlerts().length === 1 ? '' : 's'}</span>
						<button class="link" on:click={clearAllAlerts}>Clear all</button>
					</div>
					{/if}
				</div>
				{/if}
			</div>
		</div>
	</div>
</div>

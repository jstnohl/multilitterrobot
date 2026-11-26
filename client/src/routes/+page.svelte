<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fade } from 'svelte/transition';
	import Icon from '@iconify/svelte';
	import { PUBLIC_WEB_SOCKET_URL } from '$env/static/public';
	import Kitties from '$lib/components/Kitties.svelte';
	import RobotLastCat from '$lib/components/RobotLastCat.svelte';
import RobotSettings from '$lib/components/RobotSettings.svelte';

		
	

	let robots: any[] = [];
	let ws: WebSocket;
	let loading = true;
	let visits: any[] = [];
	let boxColors: any = {};
	let visitsTimer: ReturnType<typeof setInterval> | undefined;

	// Last logged visit for a box -- the live cat_weight is sticky (it holds
	// the last cat's weight with the box empty), so the card shows the most
	// recent LOGGED visit instead (v070).
	const fmtTime = (ts: string) =>
		new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

	// Plain-English status words for the card grid (locked card design).
	const STATUS_LABELS: Record<string, string> = {
		ROBOT_IDLE: 'Idle',
		READY: 'Idle',
		ROBOT_CLEAN: 'Cleaning',
		ROBOT_CAT_DETECT: 'Occupied',
		CAT_DETECTED: 'Occupied',
		CAT_SENSOR_TIMING: 'Waiting',
		OFFLINE: 'Offline',
		OFF: 'Offline',
		PAUSED: 'Paused',
		DRAWER_FULL: 'Full',
		BONNET_REMOVED: 'Bonnet',
		EMPTY_CYCLE: 'Emptying',
		POWER_DOWN: 'Off',
		POWER_UP: 'Starting'
	};
	const statusLabel = (s: string) =>
		STATUS_LABELS[s] ?? (s || '—').replace(/^ROBOT_/, '').toLowerCase().replace(/(^|_)(\w)/g, (_, p, c) => (p ? ' ' : '') + c.toUpperCase());

	const refreshVisits = async () => {
		try {
			const r = await fetch('/api/visits');
			if (r.ok) visits = await r.json();
		} catch {
			// Keep the previous visits on a failed refresh.
		}
	};

	const refreshBoxColors = async () => {
		try {
			const r = await fetch('/api/box-colors');
			if (r.ok) boxColors = await r.json();
		} catch {
			// Keep the previous colours on a failed refresh.
		}
	};

	const lastVisitFor = (serial: string) => {
		let best: any = null;
		for (const v of visits) {
			if (v.serial !== serial) continue;
			if (!best || new Date(v.timestamp) > new Date(best.timestamp)) best = v;
		}
		return best;
	};

	const startClean = async (serial: string) => {
		await fetch(`/api/robot/${serial}/clean`, { method: 'POST' });
	};

	const setLightMode = async (serial: string, mode: string) => {
    		await fetch(`/api/robot/${serial}/light?mode=${mode.toLowerCase()}`, { method: 'POST' });
	};

	const resetDrawer = async (serial: string) => {
		await fetch(`/api/robot/${serial}/reset`, { method: 'POST' });
	};


onMount(() => {
		// Initial load
		refreshVisits();
		refreshBoxColors();
		visitsTimer = setInterval(() => { refreshVisits(); refreshBoxColors(); }, 30000);
		fetch('/api/robots')
			.then((r) => r.json())
			.then((data) => {
				robots = data;
				loading = false;
			});

		// WebSocket for live updates
		setTimeout(() => {
			ws = new WebSocket(PUBLIC_WEB_SOCKET_URL);
			ws.onmessage = (event) => {
				const msg = JSON.parse(event.data);
				if (msg.robots) {
					robots = msg.robots;
					loading = false;
				}
			};
		}, 1000);
	});

onDestroy(() => {
		if (ws) ws.close();
		if (visitsTimer) clearInterval(visitsTimer);
	});
</script>

<div class="min-h-screen bg-base-200 px-4 py-8">
	<div class="mx-auto max-w-6xl">
		<div class="flex items-start gap-3">
			<h1 class="shrink-0 text-4xl font-bold [writing-mode:vertical-rl] rotate-180">Litter Robots</h1>
			<div class="min-w-0 flex-1">
{#if loading}
			<div class="flex justify-center py-20">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if robots.length === 0}
			<div class="text-center text-xl opacity-60">No robots found</div>
		{:else}
			<div class="grid gap-6 md:grid-cols-2">
				{#each robots as robot (robot.serial)}
					<div
						class="card bg-base-100 shadow-xl relative border-l-4" style="border-left-color: {boxColors[robot.serial] || '#888'}"
						transition:fade={{ duration: 300 }}
					>

<div class="card-body">
							<!-- Header -->
							<div class="flex flex-wrap items-start justify-between">
								<div class="flex items-baseline gap-2">
									<h2 class="card-title text-2xl">{robot.name}</h2>
									<span class="text-sm opacity-60">{robot.serial}</span>
								</div>
								<div class="flex items-center gap-2">
									{#if robot.wifi_rssi != null}
										<div class="tooltip" data-tip={`${robot.wifi_rssi} dBm`}>
											<Icon icon="akar-icons:wifi" class="h-5 w-5 {robot.wifi_rssi >= -60 ? '' : robot.wifi_rssi >= -70 ? 'opacity-70' : 'opacity-40'}" />
										</div>
									{/if}
									<RobotSettings serial={robot.serial} isOnline={robot.is_online} />
								</div>
							</div>

<!-- Status -->
							<div class="mt-4 grid grid-cols-3 gap-3 text-sm">
								<div class="rounded-lg bg-base-200 p-3 text-center">
									<div class="opacity-60">Status</div>
									<div class="font-semibold">{statusLabel(robot.status)}</div>
								</div>
								<div class="rounded-lg bg-base-200 p-3 text-center">
									<div class="opacity-60">Litter</div>
									<div class="font-semibold">
										{robot.litter_level_state ? robot.litter_level_state.charAt(0) + robot.litter_level_state.slice(1).toLowerCase() : '—'}
									</div>
								</div>

<div class="rounded-lg bg-base-200 p-3 text-center">
									<div class="opacity-60">Scoops Saved</div>
									<div class="font-semibold">{robot.scoops_saved ?? '—'}</div>
								</div>
							</div>

							<div class="mt-3 flex flex-nowrap items-center gap-2 overflow-hidden whitespace-nowrap rounded-lg bg-base-200 p-3 text-sm">
								<span class="min-w-0 flex-1 truncate"><span class="opacity-60">Last weight:</span> {#if lastVisitFor(robot.serial)}<span class="font-semibold">{lastVisitFor(robot.serial).weight} lbs @ {fmtTime(lastVisitFor(robot.serial).timestamp)}</span>{:else}<span class="font-semibold">no visits yet</span>{/if} by</span>
								<span class="shrink-0"><RobotLastCat serial={robot.serial} compact /></span>
							</div>
							{#if robot.is_full}
								<div class="alert alert-warning mt-4 text-sm">
									<span>Litter drawer is full</span>
								</div>
							{/if}

								<!-- Drawer level -->
								<div class="mt-4">
									<div class="flex items-center justify-between text-sm">
										<span class="opacity-60">Waste drawer</span>
										<!-- v084-card: drawer estimate -->
										{#if robot.drawer_full_in_days != null}
											<span class="opacity-70 text-xs">Full in ~{robot.drawer_full_in_days} day{robot.drawer_full_in_days === 1 ? '' : 's'}</span>
										{/if}
										<span class="font-semibold">{robot.drawer_level != null ? robot.drawer_level + '%' : '—'}</span>
									</div>
									<div class="mt-1 h-2.5 w-full overflow-hidden rounded-full bg-base-200">
										<div
											class="h-full rounded-full {robot.drawer_level != null && robot.drawer_level >= 80 ? 'bg-error' : robot.drawer_level != null && robot.drawer_level >= 50 ? 'bg-warning' : 'bg-success'}"
											style="width: {robot.drawer_level ?? 0}%"
										></div>
									</div>
								</div>

							<!-- Actions -->
							<div class="mt-6 flex items-center justify-between gap-2">
								<button
									class="btn btn-primary"
									on:click={() => startClean(robot.serial)}
									disabled={!robot.is_online}
								>
									<Icon icon="akar-icons:arrow-cycle" class="h-5 w-5" />
									Clean
								</button>

										<button
											class="btn btn-warning"
											on:click={() => resetDrawer(robot.serial)}
											disabled={!robot.is_online}
										>
											<Icon icon="akar-icons:arrow-clockwise" class="h-5 w-5" />
											Reset
										</button>

							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
			</div>
		</div>
		<Kitties />
	</div>
</div>

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { fade } from 'svelte/transition';
	import Icon from '@iconify/svelte';
	import { PUBLIC_WEB_SOCKET_URL } from '$env/static/public';
	import Kitties from '$lib/components/Kitties.svelte';
	import RobotLastCat from '$lib/components/RobotLastCat.svelte';
import RobotBoxColor from '$lib/components/RobotBoxColor.svelte';

		
	

	let robots: any[] = [];
	let ws: WebSocket;
	let loading = true;

	const startClean = async (serial: string) => {
		await fetch(`/api/robot/${serial}/clean`, { method: 'POST' });
	};

	const setLightMode = async (serial: string, mode: string) => {
    		await fetch(`/api/robot/${serial}/light?mode=${mode.toLowerCase()}`, { method: 'POST' });
	};


onMount(() => {
		// Initial load
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
	});
</script>

<div class="min-h-screen bg-base-200 px-4 py-8">
	<div class="mx-auto max-w-6xl">
		<h1 class="mb-8 text-center text-4xl font-bold">Litter Robots</h1>

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
						class="card bg-base-100 shadow-xl relative"
						transition:fade={{ duration: 300 }}
					>

<div class="card-body">
							<!-- Header -->
							<div class="flex items-start justify-between">
								<div>
									<h2 class="card-title text-2xl">{robot.name}</h2>
									<div class="text-sm opacity-60">{robot.serial}</div>
								</div>
								{#if robot.is_online}
									<div class="badge badge-success gap-2">Online</div>
								{:else}
									<div class="badge badge-error gap-2">Offline</div>
								{/if}
							</div>

<!-- Status -->
							<div class="mt-4 grid grid-cols-2 gap-3 text-sm">
								<div class="rounded-lg bg-base-200 p-3">
									<div class="opacity-60">Status</div>
									<div class="font-semibold">{robot.status || '—'}</div>
								</div>
								<div class="rounded-lg bg-base-200 p-3">
									<div class="opacity-60">Litter Level</div>
									<div class="font-semibold">
										{robot.litter_level != null ? robot.litter_level + '%' : '—'}
									</div>
								</div>
<div class="rounded-lg bg-base-200 p-3">
									<div class="opacity-60">Cat Weight</div>
									<div class="font-semibold">
										{robot.cat_weight != null ? robot.cat_weight + ' lbs' : '—'}
									</div>
								</div>
<div class="rounded-lg bg-base-200 p-3">
									<div class="opacity-60">Scoops Saved</div>
									<div class="font-semibold">{robot.scoops_saved ?? '—'}</div>
								</div>
							</div>

							{#if robot.is_full}
								<div class="alert alert-warning mt-4 text-sm">
									<span>Litter drawer is full</span>
								</div>
							{/if}

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

								<select
								    class="select select-bordered select-sm"
								    value={robot.night_light_mode ?? 'AUTO'}
								    on:change={(e) => setLightMode(robot.serial, (e.target as HTMLSelectElement).value)}
    									disabled={!robot.is_online}
								>
								    <option value="ON">Light: On</option>
								    <option value="OFF">Light: Off</option>
								    <option value="AUTO">Light: Auto</option>
								</select>
							</div>
							<div class="mt-2 flex flex-wrap items-center gap-2">
								<RobotLastCat serial={robot.serial} />
<RobotBoxColor serial={robot.serial} />

								
							</div>
						</div>
					</div>
				{/each}
			</div>
		{/if}
		<Kitties />
	</div>
</div>

<script lang="ts">
	import daisyuiColors from 'daisyui/src/theming/themes';
	import Icon from '@iconify/svelte';
	import { selectedTheme } from '$lib/store';
	import { onMount } from 'svelte';

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
	</div>
</div>

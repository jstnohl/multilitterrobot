import { SERVER_ENDPOINT } from '$env/static/private';

import type { RequestHandler } from './$types';


export const POST: RequestHandler = async ({ params, url }) => {
	const mode = url.searchParams.get('mode') ?? 'auto';
	const res = await fetch(
		`${SERVER_ENDPOINT}/api/robot/${params.serial}/light?mode=${mode}`,
		{ method: 'POST' }
	);

	const data = await res.json();

	if (!res.ok) {
		throw new Error(data.detail ?? data.message ?? 'Light failed');
	} else {
		return new Response(JSON.stringify(data), {
			headers: { 'content-type': 'application/json' }
		});
	}
};

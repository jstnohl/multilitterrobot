import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend for sleep mode.
// POST /api/robot/{serial}/sleep-mode — v074.

export async function POST({ params, request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/sleep-mode`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

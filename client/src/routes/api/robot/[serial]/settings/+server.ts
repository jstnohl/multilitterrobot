import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend for per-robot settings
// (live robot state + local settings.json fields).
// GET/POST /api/robot/{serial}/settings — v074.

export async function GET({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/settings`);
	return json(await res.json(), { status: res.status });
}

export async function POST({ params, request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/settings`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

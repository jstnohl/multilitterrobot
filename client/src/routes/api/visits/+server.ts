import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend for the visit log.
// GET /api/visits?limit=100 — newest first.
// POST /api/visits {id, pet} — correct a visit's cat by hand.

export async function GET({ url }) {
	const limit = url.searchParams.get('limit') ?? '100';
	const res = await fetch(`${SERVER_ENDPOINT}/api/visits?limit=${encodeURIComponent(limit)}`);
	return json(await res.json(), { status: res.status });
}

export async function POST({ request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/visits/reassign`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend so the graph legend can read/set
// each box's ring colour without talking to the backend host directly.

export async function GET() {
	const res = await fetch(`${SERVER_ENDPOINT}/api/box-colors`);
	return json(await res.json(), { status: res.status });
}

export async function POST({ request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/box-colors`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

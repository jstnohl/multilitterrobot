import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend so the robot card can read/set
// which cat last used a box without talking to the backend host directly.

export async function GET({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/last-cat`);
	return json(await res.json(), { status: res.status });
}

export async function POST({ params, request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/last-cat`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

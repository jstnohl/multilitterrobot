import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend so the robot card can reset
// the waste drawer gauge without talking to the backend host directly.

export async function POST({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/reset`, {
		method: 'POST'
	});
	return json(await res.json(), { status: res.status });
}

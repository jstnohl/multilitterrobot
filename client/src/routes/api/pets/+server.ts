import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend so the page can manage pets
// without talking to the backend host directly.

export async function GET() {
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets`);
	return json(await res.json(), { status: res.status });
}

export async function POST({ request }) {
	const body = await request.json();
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
	return json(await res.json(), { status: res.status });
}

export async function DELETE({ url }) {
	const id = url.searchParams.get('id');
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets?id=${encodeURIComponent(id ?? '')}`, {
		method: 'DELETE'
	});
	return json(await res.json(), { status: res.status });
}

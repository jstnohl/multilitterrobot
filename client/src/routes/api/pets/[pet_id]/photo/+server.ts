import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

export async function GET({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets/${params.pet_id}/photo`);
	if (!res.ok) return json({ detail: 'No photo' }, { status: res.status });
	return new Response(await res.arrayBuffer(), {
		headers: { 'content-type': res.headers.get('content-type') ?? 'image/jpeg' }
	});
}

export async function POST({ params, request }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets/${params.pet_id}/photo`, {
		method: 'POST',
		headers: { 'content-type': request.headers.get('content-type') ?? '' },
		body: await request.arrayBuffer()
	});
	return json(await res.json(), { status: res.status });
}

export async function DELETE({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/pets/${params.pet_id}/photo`, { method: 'DELETE' });
	return json(await res.json(), { status: res.status });
}

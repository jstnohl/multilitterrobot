import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

export async function POST({ params, request }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/panel-brightness`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(await request.json())
	});
	return json(await res.json(), { status: res.status });
}

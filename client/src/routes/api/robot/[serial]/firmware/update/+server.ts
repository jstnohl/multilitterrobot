import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

export async function POST({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/firmware/update`, { method: 'POST' });
	return json(await res.json(), { status: res.status });
}

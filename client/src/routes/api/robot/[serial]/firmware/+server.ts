import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

export async function GET({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robot/${params.serial}/firmware`);
	return json(await res.json(), { status: res.status });
}

import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

export async function GET() {
	const res = await fetch(`${SERVER_ENDPOINT}/api/pet-photos`);
	return json(await res.json(), { status: res.status });
}

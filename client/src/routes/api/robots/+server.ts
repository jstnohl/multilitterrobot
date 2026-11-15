import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend for the robot list (names + serials).
// GET /api/robots — used by the visits table to show "LR4.1 (LR4Cxxxxxx)".

export async function GET() {
	const res = await fetch(`${SERVER_ENDPOINT}/api/robots`);
	return json(await res.json(), { status: res.status });
}

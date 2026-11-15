import { json } from '@sveltejs/kit';
import { SERVER_ENDPOINT } from '$env/static/private';

// Pass-through to the FastAPI backend for a single visit.
// DELETE /api/visits/{id} — remove an erroneous visit from the log.

export async function DELETE({ params }) {
	const res = await fetch(`${SERVER_ENDPOINT}/api/visits/${params.id}`, {
		method: 'DELETE'
	});
	return json(await res.json(), { status: res.status });
}

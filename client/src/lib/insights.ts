// $lib/insights.ts — shared helpers for alerts, weight trends, and CSV export.
// Used by Nav (bell + export icon) and AvgWeightGraph (trend row + panel CSV).
// Pure functions over the /api/pets + /api/visits (+ /api/events) payloads.
// No backend changes needed: everything here runs in the browser.

export const DAY = 86400000;

export function msOf(ts: any): number | null {
	if (!ts) return null;
	const m = new Date(ts).getTime();
	return isNaN(m) ? null : m;
}

export function isAutoVisit(v: any): boolean {
	return !!v && !!v.pet && !v.manual && v.weight != null && !isNaN(v.weight) && msOf(v.timestamp) != null;
}

/** Mean of a pet's automatic visit weights with t in (now - days*DAY, now]. Null when none. */
export function trailingAvg(visits: any[], petName: string, days: number, nowMs: number): number | null {
	const cutoff = nowMs - days * DAY;
	const ws: number[] = [];
	for (const v of visits || []) {
		if (!isAutoVisit(v) || v.pet !== petName) continue;
		const t = msOf(v.timestamp)!;
		if (t > cutoff && t <= nowMs) ws.push(v.weight);
	}
	if (ws.length === 0) return null;
	return ws.reduce((a, b) => a + b, 0) / ws.length;
}

/** Per-cat trend: 7-day trailing avg vs 30-day trailing avg. pct is null when either side is missing. */
export function computeTrends(pets: any[], visits: any[], nowMs: number) {
	const out: { name: string; color: string; avg7: number | null; avg30: number | null; pct: number | null; dir: 'up' | 'down' | 'flat' }[] = [];
	for (const p of pets || []) {
		const avg7 = trailingAvg(visits, p.name, 7, nowMs);
		const avg30 = trailingAvg(visits, p.name, 30, nowMs);
		let pct: number | null = null;
		let dir: 'up' | 'down' | 'flat' = 'flat';
		if (avg7 != null && avg30 != null && avg30 !== 0) {
			pct = ((avg7 - avg30) / avg30) * 100;
			dir = pct >= 0.5 ? 'up' : pct <= -0.5 ? 'down' : 'flat';
		}
		out.push({ name: p.name, color: p.color || '#888', avg7, avg30, pct, dir });
	}
	return out;
}

/** Active alerts. Key is stable while the underlying condition is unchanged, so a dismissed alert stays dismissed until the condition clears and re-triggers. */
export function computeAlerts(pets: any[], visits: any[], nowMs: number) {
	const alerts: { key: string; type: string; pet: string; title: string; detail: string; severity: 'warn' | 'info' }[] = [];
	const autos = (visits || []).filter(isAutoVisit);

	for (const p of pets || []) {
		const mine = autos.filter((v) => v.pet === p.name);
		if (mine.length === 0) continue;
		const times = mine.map((v) => msOf(v.timestamp)!);
		const last = Math.max(...times);
		const hours = Math.floor((nowMs - last) / 3600000);
		if (hours >= 24) {
			const d = new Date(last);
			alerts.push({
				key: `no_visit:${p.name}:${last}`,
				type: 'no_visit',
				pet: p.name,
				title: `${p.name} — no visit in ${hours}h`,
				detail: `last ${d.toLocaleDateString([], { month: '2-digit', day: '2-digit' })} @ ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
				severity: 'warn'
			});
		}

		// visits today vs usual daily rate (over the days on record)
		const earliest = Math.min(...times);
		const spanDays = Math.max(1, (nowMs - earliest) / DAY);
		const avgDaily = mine.length / spanDays;
		const todayStart = new Date(nowMs);
		todayStart.setHours(0, 0, 0, 0);
		const todayCount = mine.filter((v) => msOf(v.timestamp)! >= todayStart.getTime()).length;
		if (avgDaily >= 1 && todayCount >= 2 * avgDaily && todayCount >= 4) {
			alerts.push({
				key: `high_freq:${p.name}:${todayStart.toISOString().slice(0, 10)}`,
				type: 'high_frequency',
				pet: p.name,
				title: `${p.name} — ${todayCount} visits today vs ${avgDaily.toFixed(1)} usual (2× rate)`,
				detail: 'visiting much more than normal',
				severity: 'warn'
			});
		}
	}

	for (const t of computeTrends(pets, visits, nowMs)) {
		if (t.pct != null && Math.abs(t.pct) >= 5) {
			const dirWord = t.pct < 0 ? 'down' : 'up';
			alerts.push({
				key: `trend:${t.name}:${Math.round(t.pct * 10) / 10}`,
				type: 'weight_trend',
				pet: t.name,
				title: `${t.name} — 7-day avg ${dirWord} ${Math.abs(t.pct).toFixed(1)}% vs 30d`,
				detail: `Avg ${t.avg7!.toFixed(1)}, was ${t.avg30!.toFixed(1)} · trailing 7-day`,
				severity: 'warn'
			});
		}
	}
	return alerts;
}

function csvCell(v: any): string {
	if (v == null) return '';
	const s = String(v);
	return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/**
 * Build a CSV for export. One row per visit (filtered by cat when given),
 * each carrying its trailing 7-day average as of that visit. Events are
 * appended as rows when included. Columns:
 * timestamp, pet, weight_lbs, trailing_7d_avg_lbs, robot, visit_type, manual, record
 */
export function buildExportCSV(opts: {
	pets: any[];
	visits: any[];
	events: any[];
	cat: string; // '' = all cats, else a pet name
	includeVisits: boolean;
	includeWeights: boolean;
	includeAverages: boolean;
	includeEvents: boolean;
}): string {
	const { pets, visits, events, cat, includeVisits, includeWeights, includeAverages, includeEvents } = opts;
	const rows: string[][] = [];
	rows.push(['timestamp', 'pet', 'weight_lbs', 'trailing_7d_avg_lbs', 'robot', 'visit_type', 'manual', 'record']);
	const sorted = [...(visits || [])].sort((a, b) => (msOf(a.timestamp) ?? 0) - (msOf(b.timestamp) ?? 0));
	for (const v of sorted) {
		if (!v || !v.pet) continue;
		if (cat && v.pet !== cat) continue;
		if (!includeVisits && !includeWeights && !includeAverages) continue;
		// a visit row is included when any of visits/weights/averages is ticked
		const t = msOf(v.timestamp);
		let avg: number | null = null;
		if (includeAverages && t != null) {
			avg = trailingAvg(visits, v.pet, 7, t);
		}
		rows.push([
			v.timestamp ?? '',
			v.pet ?? '',
			includeWeights && v.weight != null ? String(v.weight) : '',
			avg != null ? avg.toFixed(2) : '',
			v.robot ?? v.serial ?? '',
			v.type ?? '',
			v.manual ? 'yes' : 'no',
			'visit'
		]);
	}
	if (includeEvents) {
		const evSorted = [...(events || [])].sort((a, b) => (msOf(a.timestamp) ?? 0) - (msOf(b.timestamp) ?? 0));
		for (const e of evSorted) {
			if (!e) continue;
			if (cat && e.resolved_pet && e.resolved_pet !== cat) continue;
			rows.push([
				e.timestamp ?? '',
				e.resolved_pet ?? e.pet ?? '',
				e.weight != null ? String(e.weight) : '',
				'',
				e.robot ?? e.serial ?? '',
				`event: ${e.type ?? ''}${e.resolution ? ` (${e.resolution})` : ''}`,
				'',
				'event'
			]);
		}
	}
	return rows.map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
}

/** Trigger a browser download of CSV text. */
export function downloadCSV(filename: string, csv: string) {
	const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

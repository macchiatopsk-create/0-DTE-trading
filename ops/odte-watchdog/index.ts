// odte 연쇄 감시 (Supabase Edge Function, pg_cron이 장중 1분마다 호출)
// 왜: GitHub Actions 연쇄는 다음 실행이 러너를 못 받으면 백업 cron 말고는 살릴 수단이 없다.
//   2026-11-09 2h25m, 11-11 45분(startup_failure), 11-16 67분·40분(러너 대기) 공백.
// 하는 일: 장중(뉴욕 09:28~16:02, 휴장일 제외)에 odte_log.json 마지막 커밋이 7분 넘게 묵었으면
//   ① 4분 넘게 묵은 진행/대기 중 odte 실행을 취소(러너 대기에 걸린 실행이 concurrency 그룹을 붙잡고 있으므로)
//   ② workflow_dispatch로 새 실행 발사. 4분 안쪽 실행이 있으면(막 발사된 것) 한 번 더 기다린다.
// 필요한 시크릿: GH_WATCHDOG_TOKEN (fine-grained PAT, 이 저장소만, Actions: Read and write)
//   선택: NTFY_TOPIC (살렸을 때 휴대폰 알림)
const REPO = "macchiatopsk-create/0-dte-trading";
const WF = "odte.yml";
const STALE_S = 7 * 60;
const FRESH_S = 4 * 60;
// NYSE 휴장일 / 13:00 조기 마감
const HOLIDAYS = new Set([
  "2026-11-26", "2026-12-25",
  "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
  "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]);
const EARLY = new Set(["2026-11-27", "2026-12-24", "2027-11-26"]);

function nyNow() {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false,
  }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hm: Number(p.hour) % 24 * 100 + Number(p.minute), wd: p.weekday };
}

Deno.serve(async (req) => {
  const out = (o: unknown, status = 200) =>
    new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });
  const token = Deno.env.get("GH_WATCHDOG_TOKEN");
  if (!token) return out({ ok: false, error: "GH_WATCHDOG_TOKEN 미설정" }, 503);
  const force = new URL(req.url).searchParams.get("dry") === "1" ? "dry" : "";
  const ny = nyNow();
  const end = EARLY.has(ny.date) ? 1302 : 1602;
  if (["Sat", "Sun"].includes(ny.wd) || HOLIDAYS.has(ny.date) || ny.hm < 928 || ny.hm > end) {
    return out({ ok: true, act: "장외", ny });
  }
  const gh = (path: string, init: RequestInit = {}) =>
    fetch(`https://api.github.com/repos/${REPO}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", ...(init.headers || {}) },
      signal: AbortSignal.timeout(10000),
    });
  const now = Date.now();
  const c = await gh(`/commits?sha=main&path=odte_log.json&per_page=1`);
  if (!c.ok) return out({ ok: false, error: `commits ${c.status}` }, 502);
  const last = Date.parse((await c.json())[0]?.commit?.committer?.date ?? 0);
  const age = Math.round((now - last) / 1000);
  if (age <= STALE_S) return out({ ok: true, act: "정상", age });

  const runs: any[] = [];
  for (const st of ["in_progress", "queued", "waiting", "pending", "requested"]) {
    const r = await gh(`/actions/workflows/${WF}/runs?status=${st}&per_page=20`);
    if (r.ok) runs.push(...((await r.json()).workflow_runs ?? []));
  }
  const fresh = runs.filter((r) => (now - Date.parse(r.created_at)) / 1000 < FRESH_S);
  if (fresh.length) return out({ ok: true, act: "대기(막 발사된 실행 있음)", age, fresh: fresh.map((r) => r.run_number) });
  if (force === "dry") return out({ ok: true, act: "dry", age, stuck: runs.map((r) => [r.run_number, r.status]) });

  const cancelled: number[] = [];
  for (const r of runs) {
    let x = await gh(`/actions/runs/${r.id}/cancel`, { method: "POST" });
    if (!x.ok) x = await gh(`/actions/runs/${r.id}/force-cancel`, { method: "POST" });
    if (x.ok) cancelled.push(r.run_number);
  }
  const d = await gh(`/actions/workflows/${WF}/dispatches`, { method: "POST", body: JSON.stringify({ ref: "main" }) });
  const msg = `odte 연쇄 끊김 감지(마지막 커밋 ${Math.round(age / 60)}분 전) → 취소 ${cancelled.join(",") || "없음"}, 재발사 ${d.status === 204 ? "OK" : "실패 " + d.status}`;
  const topic = Deno.env.get("NTFY_TOPIC");
  if (topic) await fetch(`https://ntfy.sh/${topic}`, { method: "POST", body: msg }).catch(() => {});
  return out({ ok: d.status === 204, act: "재발사", age, cancelled, dispatch: d.status, msg });
});

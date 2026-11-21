# odte-watchdog

GitHub Actions 연쇄가 끊겼을 때(러너 대기·startup_failure) 밖에서 살리는 감시.
Supabase 프로젝트 `nutfgkxaddvidqrcnvyj`의 Edge Function `odte-watchdog`으로 배포, pg_cron이 장중 매분 호출.

- 판단: 뉴욕 09:28~16:02(조기 마감일 13:02), 휴장일 제외. `odte_log.json` 마지막 커밋이 7분 넘게 묵으면
  4분 넘은 진행/대기 실행을 취소하고 `odte.yml`을 dispatch. 막 발사된(4분 안) 실행이 있으면 기다림.
- 시크릿(Supabase → Edge Functions → Secrets): `GH_WATCHDOG_TOKEN` = fine-grained PAT
  (Repository access: 이 저장소만, Permissions: Actions Read and write). 없으면 503만 내고 아무것도 안 함.
  선택: `NTFY_TOPIC` (살렸을 때 알림).
- 점검: `.../functions/v1/odte-watchdog?dry=1` 은 취소·발사 없이 판단만 돌려줌.
- 휴장일 목록은 index.ts의 HOLIDAYS/EARLY — 2028년분은 연말에 추가.
- cron 정의: `ops/odte-watchdog/cron.sql`

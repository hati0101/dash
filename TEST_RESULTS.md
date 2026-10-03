# r4 검증 결과

운영 미적용 / REVIEW-4 후속 후보 / 개발컴 독립 REVIEW-5 필요.

- Python 단위·통합: 67개 중66 PASS / 1 SKIP(서버컴 Windows symlink 생성 권한 없음). 하드링크 실제 생성 거부 시험 PASS.
- REVIEW-2 재현: ★4 반려 → 사령탑 초기화 → 재시험 → 새 ★4, ★4 → ★5 → ★7, 신규 command_mode 재시작 제외, 시험 3회 후 초기화, 백업·기준 보존 잠금 승계 뒤 실제 파일 편집, 양쪽 부재 알림 31주제 한 장, 담당 작업자 부재, 배정 잠금 대행 금지, 오래된 스냅샷 거부.
- 경로/검사: conf/import 및 map_athena 설정 create 거부, sql replace 거부, 끝 점·공백 거부, 검사기 SECRET_RES 누락 실패, 작업 재시도 한도.
- 실제 Playwright + headless Edge: 화면32항목 및 검수 집계 추가 assertion. 오류0, 1440×1000 한 화면·390px 가로 넘침 없음. ui-r3 보관 주제의 보류 수·목록 제외, 재개 숨김 및 대행 검수 표시.
- 기존 회귀6종 및 최종 APPLY/VERIFY -Browser 결과는 제출 폴더 applied-verify.log와 ui-result.json이 실제 실행 근거다.
- 실제 두 PC/운영 DB/서비스/게임/iOS 시험은 미실행. 서버컴 설정은 server-astra/server-claude 모두 dev 없음(읽기 전용 확인). 검수는 작업물 근거를 사용하며 서버컴에 개발 트리 편집 권한을 추가하지 않는다.
- 바이너리 공인 IP 오탐은 보수적 차단 유지. 별도 판정 규격은 미구현이며 성공 처리로 숨기지 않는다.

- REVIEW-3: ★5 수정 시 사령탑 재시험 경로, diff 없음/본문 변조/최종 SHA 불일치 원복 거부(force 포함), 유효 diff만 원복, 승계 보류·삭제 보호, 반쪽 목적 파일+임시 파일 쓰기 중단 복구, 한 주제 승계 오류 후 다른 주제 정리, 노드 없음+온라인 대행자 알림 구분 시험 추가.

- REVIEW-4 실제 경로(command.apply_action → node 기록 → merged_topics → 실행기 담당 판정): ★40 메모 → work → amend → 추가 조사 제출/수락 → 새 ★40, 브라우저 시계 +10분/-10분에서 ★4 반려 → reset → 재시험 → 새 ★4 통과.

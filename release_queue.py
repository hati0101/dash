"""검증된 작업물을 서버에서 수신 확인하고 배포 묶음 ZIP으로 만든다.

운영 파일 교체/DB/서비스 제어는 하지 않는다. 최종 Astra 대화는 이 CLI로
묶음 전체를 직접 읽으므로 아키텍트가 개발 대화와 파일을 중계할 필요가 없다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from command import safe_file, verify_evidence

HASH = re.compile(r"^[0-9a-f]{64}$")


def require_pin(package, digest):
    if not digest or digest != package['manifest_sha256']:
        raise ValueError('제출된 배포 계약과 다릅니다. 배포본 작성·승인부터 다시 확인하세요')


def load_topic_package(work_root, topic):
    package = load_package(work_root, topic.get('work_id'), topic['id'])
    require_pin(package, (topic.get('package_receipts') or {}).get('prep'))
    return package


def scan_sources(work_root, paths):
    """ZIP으로 감싸기 전 기존 공유 검사기로 원문 하나씩 검사한다."""
    tool = Path(work_root) / "work.py"
    if not tool.is_file():
        raise ValueError("작업물 공유 검사기(work.py)가 없습니다")
    spec = importlib.util.spec_from_file_location("release_work_scanner", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not getattr(module, 'SECRET_RES', None) or not callable(getattr(module, 'scan_file', None)):
        raise ValueError('공유 검사기 규칙 SECRET_RES 또는 scan_file이 없습니다')
    for p in paths:
        problems = module.scan_file(p)
        # 기존 검사기의 NUL/UTF-16/크기 잘림 우회를 막는다.
        raw = p.read_bytes()
        texts = [raw.decode('utf-8', errors='ignore').replace('\x00', '')]
        for enc in ('utf-16-le', 'utf-16-be', 'cp949'):
            texts.append(raw.decode(enc, errors='ignore').replace('\x00', ''))
        for label, rx in module.SECRET_RES:
            if any(rx.search(value) for value in texts):
                problems.append(label + ' 의심: ' + p.name)
        if problems:
            raise ValueError("공유 검사 실패: " + "; ".join(problems))


def relative(value):
    if not isinstance(value, str) or not value or ":" in value or "\\" in value:
        raise ValueError("대상은 server/ 또는 client/ 같은 논리 루트의 상대 경로여야 합니다")
    p = PurePosixPath(value)
    if any(part.endswith((".", " ")) for part in p.parts):
        raise ValueError("Windows 끝 점·공백 경로는 허용하지 않습니다")
    if p.is_absolute() or any(x in ("..", ".git", ".local") for x in p.parts) or len(p.parts) < 2:
        raise ValueError("배포 대상 경로 오류")
    return p.as_posix()


def load_package(work_root, work_id, topic):
    work_root = Path(work_root).resolve()
    if not re.fullmatch(r"[A-Z]{2,6}-\d{8}-[A-Za-z0-9]{1,12}", str(work_id)):
        raise ValueError("작업물 ID 오류")
    folder = Path(work_root) / "work" / work_id
    candidates = sorted(folder.glob("dev-*/PACKAGE.json"))
    if len(candidates) != 1:
        raise ValueError("개발 작업자의 PACKAGE.json이 정확히 하나 필요합니다")
    p = safe_file(work_root, candidates[0].relative_to(work_root).as_posix())
    package = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(package, dict):
        raise ValueError("배포 계약은 JSON 객체여야 합니다")
    if package.get("version") != 1 or package.get("topic") != topic:
        raise ValueError("배포 계약 버전·주제 불일치")
    for key in ("summary", "apply_steps", "rollback_steps", "verify_steps"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            raise ValueError("배포 계약 누락: " + key)
    changes = package.get("changes")
    if not isinstance(changes, list) or not 1 <= len(changes) <= 500:
        raise ValueError("배포 변경 목록이 필요합니다")
    seen = set()
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("배포 변경 항목은 객체여야 합니다")
        target = relative(change.get("target"))
        if re.search(r'(?i)(conf/import/|map_athena.*\.conf|inter_athena.*\.conf|char_athena.*\.conf|login_athena.*\.conf|\.env(?:\.|$)|\.(?:pem|key|pfx)$|id_rsa)', target):
            raise ValueError("비밀 설정·키 대상은 배포 묶음에 넣을 수 없습니다. 운영 설정은 아키텍트 대화 배포로 처리하세요")
        key = target.casefold()
        if key in seen:
            raise ValueError("중복 배포 대상: " + target)
        seen.add(key)
        if change.get("operation") not in ("create", "replace", "patch", "delete"):
            raise ValueError("지원하지 않는 파일 작업")
        for h in ("before_sha256", "after_sha256", "source_sha256"):
            if change.get(h) is not None and not HASH.fullmatch(str(change[h])):
                raise ValueError("해시 형식 오류: " + h)
        op = change["operation"]
        if (op == "create") != (change.get("before_sha256") is None):
            raise ValueError("신규 파일은 이전 해시 null, 수정·삭제는 이전 해시가 필요합니다")
        if op == "delete":
            if change.get("source") or change.get("after_sha256") is not None:
                raise ValueError("삭제 항목에는 새 파일이 없어야 합니다")
        else:
            source = change.get("source")
            if not isinstance(source, str) or not source.startswith(f"work/{work_id}/dev-"):
                raise ValueError("같은 작업의 개발 결과물만 포함할 수 있습니다")
            data = safe_file(work_root, source).read_bytes()
            digest = change.get("source_sha256") if op == "patch" else change.get("after_sha256")
            if not HASH.fullmatch(str(change.get("after_sha256") or "")):
                raise ValueError("적용 결과 해시가 필요합니다")
            if op == "patch" and not source.endswith(".diff"):
                raise ValueError("patch는 검토된 .diff 파일이어야 합니다")
            if op == "replace" and Path(target).suffix.lower() in (".cpp", ".hpp", ".c", ".h", ".yml", ".yaml", ".txt", ".lua", ".conf", ".ini", ".json", ".sql"):
                raise ValueError("기존 소스·데이터 전체 대신 최소 diff를 전달하세요(operation=patch)")
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("배포 파일 SHA256 불일치: " + source)
    checks = package.get("evidence")
    if not isinstance(checks, list) or not checks:
        raise ValueError("실제로 읽을 수 있는 검증 근거가 필요합니다")
    for row in checks:
        if not isinstance(row, dict):
            raise ValueError("검증 근거 항목은 객체여야 합니다")
        if not str(row.get("path", "")).startswith(f"work/{work_id}/"):
            raise ValueError("다른 작업의 검증 근거를 사용할 수 없습니다")
    verify_evidence(work_root, checks)
    scan_sources(work_root, [p, *[safe_file(work_root, c["source"]) for c in changes if c.get("source")],
                             *[safe_file(work_root, e["path"]) for e in checks]])
    package = {**package, "work_id": work_id, "manifest_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
               "manifest_path": p.relative_to(work_root).as_posix()}
    return package


def check_targets(packages, roots, work_root=None):
    """서버컴에서 실행 직전 파일 기준 대조. 읽기 전용, 모든 항목을 먼저 확인."""
    for p in packages:
        for c in p["changes"]:
            target = PurePosixPath(relative(c["target"]))
            logical, *rest = target.parts
            if logical not in roots:
                raise ValueError("실제 경로 매핑 없음: " + logical)
            root = Path(roots[logical]).resolve()
            dest = root.joinpath(*rest).resolve()
            if not dest.is_relative_to(root):
                raise ValueError("대상 경로 범위 이탈")
            before = c.get("before_sha256")
            if before is None:
                if dest.exists():
                    raise ValueError("신규 대상이 이미 존재함: " + c["target"])
            elif not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest() != before:
                raise ValueError("실서버 기준 변경: " + c["target"])
            if c['operation'] == 'patch':
                if work_root is None:
                    raise ValueError('diff 검증용 작업물 경로가 필요합니다')
                diff=safe_file(work_root,c['source']).read_bytes()
                # 임시 사본에만 적용한다. diff의 대상이 계약의 단일 파일과 일치해야 한다.
                with tempfile.TemporaryDirectory(prefix='real-patch-') as tmp:
                    probe=Path(tmp)/c['target'];probe.parent.mkdir(parents=True,exist_ok=True)
                    probe.write_bytes(dest.read_bytes())
                    stat=subprocess.run(['git','-c','core.autocrlf=false','apply','--numstat','-z','-'],input=diff,cwd=tmp,capture_output=True)
                    entries=[x.split(b'\t',2)[-1].decode('utf8') for x in stat.stdout.split(b'\0') if x]
                    if stat.returncode or entries != [c['target']]:
                        raise ValueError('diff 대상과 배포 계약 불일치: '+c['target'])
                    applied=subprocess.run(['git','-c','core.autocrlf=false','apply','--whitespace=nowarn','-'],input=diff,cwd=tmp,capture_output=True)
                    if applied.returncode or not probe.is_file() or hashlib.sha256(probe.read_bytes()).hexdigest()!=c['after_sha256']:
                        raise ValueError('격리 diff 적용·결과 해시 검증 실패: '+c['target'])


def export_packages(packages, work_root, destination, batch, roots=None):
    targets = {}
    for p in packages:
        # 이전에 로드한 dict도 파일이 바뀌었으면 거부한다.
        fresh = load_package(work_root, p["work_id"], p["topic"])
        if fresh != p:
            raise ValueError("수신 후 배포 계약이 바뀌었습니다")
        for c in p["changes"]:
            key = relative(c["target"]).casefold()
            if key in targets:
                raise ValueError(f"묶음 충돌: {c['target']} ({targets[key]} / {p['topic']}) — 개발컴에서 통합·재검증 필요")
            targets[key] = p["topic"]
    if roots is not None:
        check_targets(packages, roots, work_root)
    manifest = {"version": 1, "batch": batch, "operating_applied": False,
                "baseline_checked": roots is not None, "packages": packages}
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".zip.tmp", delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            lines = [f"# {batch} 배포 검토 묶음", "운영 미적용. 파일 수신 검증은 실게임 검증과 다릅니다.",
                     "실제 적용은 서버컴 Astra 대화에서 승인 범위·서비스 종료/기동·백업·기준 재확인 후 진행합니다."]
            for p in packages:
                lines += ["", "## " + p["topic"], p["summary"], "### 적용", p["apply_steps"],
                          "### 복구", p["rollback_steps"], "### 사후 확인", p["verify_steps"]]
                for c in p["changes"]:
                    if c["operation"] != "delete":
                        data = safe_file(work_root, c["source"]).read_bytes()
                        digest = c.get("source_sha256") if c["operation"] == "patch" else c["after_sha256"]
                        if hashlib.sha256(data).hexdigest() != digest:
                            raise ValueError("묶음 작성 중 파일 변경")
                        entry = "patches/" + relative(c["target"]) + ".diff" if c["operation"] == "patch" else "files/" + relative(c["target"])
                        z.writestr(entry, data)
                for i, row in enumerate(p["evidence"]):
                    data = safe_file(work_root, row["path"]).read_bytes()
                    if hashlib.sha256(data).hexdigest() != row["sha256"]:
                        raise ValueError("묶음 작성 중 근거 변경")
                    z.writestr(f"evidence/{p['topic']}/{i}-{Path(row['path']).name}", data)
            z.writestr("DEPLOY.md", "\n\n".join(lines))
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
    return {"path": str(dest), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "topics": [p["topic"] for p in packages], "baseline_checked": roots is not None,
            "operating_applied": False}


def select_batch(data, batch):
    rows = [t for t in data.get("topics", []) if (t.get("deploy_batch") or {}).get("id") == batch
            and t.get("stage") == "deploy" and t.get("status") == "active" and not t.get("archived")]
    if not rows:
        raise ValueError("실행 대기 중인 배포 묶음이 없습니다")
    return rows


def main():
    import node
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--snapshot", help="격리 시험용 대시보드 JSON. 생략하면 이 PC 암호문을 직접 읽음")
    ap.add_argument("--work-root")
    ap.add_argument("--output", required=True)
    ap.add_argument("--roots", help="논리 루트 → 실제 운영 경로 JSON(로컬 전용, 읽기 확인만)")
    args = ap.parse_args()
    cfg = node.load_cfg()
    if args.snapshot:
        data = json.loads(Path(args.snapshot).read_text(encoding="utf-8-sig"))
    else:
        pw = os.environ.get("REAL_OPS_PASSWORD") or node.saved_password()
        if not pw:
            raise ValueError("이 PC 대시보드 인증을 확인하세요")
        data = node.decrypt_main(cfg, pw)
    work = Path(args.work_root or cfg.get("work_repo") or "D:/real-work")
    rows = select_batch(data, args.batch)
    packages = [load_topic_package(work, t) for t in rows]
    roots = json.loads(Path(args.roots).read_text(encoding="utf-8-sig")) if args.roots else None
    result = export_packages(packages, work, args.output, args.batch, roots)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit("배포 묶음 준비 실패: " + str(exc))

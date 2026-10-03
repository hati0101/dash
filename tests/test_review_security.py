"""REVIEW-1의 파일 경계와 계약 형식 우회 재현. 격리 임시 파일만 사용."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import command
import release_queue


class ReviewSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'work.py').write_text("import re\nSECRET_RES=[('secret',re.compile(r'credential_marker=forbidden'))]\ndef scan_file(p): return []\n", encoding='utf8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_full_file_and_encodings(self):
        for raw in (b'\x00credential_marker=forbidden', 'credential_marker=forbidden'.encode('utf-16'),
                    b'x' * 5_000_001 + b'credential_marker=forbidden'):
            with self.subTest(size=len(raw)):
                p = self.root / 'payload.bin'; p.write_bytes(raw)
                with self.assertRaises(ValueError):
                    release_queue.scan_sources(self.root, [p])

    def test_symlink_file_and_directory_rejected(self):
        outside = self.root / 'other'; outside.mkdir()
        (outside / 'proof').write_text('proof')
        link = self.root / 'alias'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest('symlink privilege unavailable: ' + str(exc))
        with self.assertRaises(ValueError):
            command.safe_file(self.root, 'alias/proof')
        link.unlink()

    def test_bad_contract_shapes_and_secret_target(self):
        folder = self.root / 'work/FT-20261003-test/dev-claude'; folder.mkdir(parents=True)
        manifest = folder / 'PACKAGE.json'
        base = dict(version=1, topic='T-test', summary='fix', apply_steps='apply', rollback_steps='undo', verify_steps='check')
        for value in ([], dict(base, changes=['invalid']), dict(base, changes=[dict(target='server/conf/inter_athena.conf')])):
            manifest.write_text(json.dumps(value), encoding='utf8')
            with self.subTest(value=value), self.assertRaises(ValueError):
                release_queue.load_package(self.root, 'FT-20261003-test', 'T-test')


if __name__ == '__main__': unittest.main()

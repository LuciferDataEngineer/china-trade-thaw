import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_hashes_match_the_files():
    manifest = json.loads((ROOT / "data" / "snapshot" / "manifest.json").read_text())
    assert manifest["row_counts"]["merch_month"] > 100_000
    assert manifest["row_counts"]["au_states"] >= 7
    for record in manifest["files"]:
        blob = (ROOT / record["path"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == record["sha256"]
        assert len(blob) == record["bytes"]

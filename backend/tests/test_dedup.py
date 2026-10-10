import os

from tests.conftest import HEADERS, import_dir, pattern, wait_job


def test_visual_dedup_end_to_end(client, tmp_path):
    src = tmp_path / "src"
    os.makedirs(src)
    base = pattern(400, 300)
    base.save(src / "master.png", "PNG")
    base.resize((200, 150)).save(src / "export.jpg", "JPEG", quality=80)
    pattern(400, 300, "v").save(src / "different.png", "PNG")
    counts = import_dir(client, src)
    assert counts["imported"] == 3

    assert client.post("/api/dedup/scan", json={"threshold": 57}, headers=HEADERS).status_code == 422

    job = client.post("/api/dedup/scan", json={}, headers=HEADERS).json()["job_id"]
    state = wait_job(client, job)
    assert state["counts"]["visual_sets"] == 1
    assert state["counts"]["exact_sets"] == 0

    sets = client.get("/api/dedup/sets").json()["sets"]
    assert len(sets) == 1
    vset = sets[0]
    assert vset["match_kind"] == "visual"
    assert vset["keeper"]["name"] == "master.png"
    assert len(vset["members"]) == 1
    assert vset["members"][0]["pair_sim"] >= 94

    result = client.post(f"/api/dedup/sets/{vset['id']}/resolve", json={}, headers=HEADERS).json()
    assert result["trashed"] == 1
    remaining = [m["name"] for m in client.get("/api/media").json()["items"]]
    assert "master.png" in remaining and "export.jpg" not in remaining
    assert client.get("/api/dedup/sets").json()["sets"] == []

    token = client.post("/api/vault/setup", json={"passkey": "vaultkey"}, headers=HEADERS).json()["token"]
    trash = client.get("/api/trash", headers={**HEADERS, "x-dam-vault": token}).json()["items"]
    assert trash[0]["trash_reason"].startswith("duplicate:")

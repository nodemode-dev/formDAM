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


def near_set(client, tmp_path):
    src = tmp_path / "near"
    os.makedirs(src)
    base = pattern(400, 300)
    base.save(src / "master.png", "PNG")
    base.save(src / "resaved.jpg", "JPEG", quality=40)
    base.resize((200, 150)).save(src / "small.jpg", "JPEG", quality=80)
    assert import_dir(client, src)["imported"] == 3
    state = wait_job(client, client.post("/api/dedup/scan", json={}, headers=HEADERS).json()["job_id"])
    assert state["counts"]["visual_sets"] == 1
    vset = client.get("/api/dedup/sets").json()["sets"][0]
    ids = {m["name"]: m["id"] for m in [vset["keeper"], *vset["members"]]}
    assert len(ids) == 3 and vset["keeper"]["name"] != "small.jpg"
    keeper = vset["keeper"]["id"]
    full = next(i for name, i in ids.items() if name != "small.jpg" and i != keeper)
    return vset["id"], keeper, full, ids["small.jpg"]


def live_ids(client, ids):
    return sorted(i for i in ids if client.get(f"/api/media/{i}").status_code == 200)


def test_trashing_every_member_after_the_keeper_was_trashed_is_refused(client, tmp_path):
    set_id, keeper, full, small = near_set(client, tmp_path)
    assert client.post(f"/api/media/{keeper}/trash", headers=HEADERS).status_code == 200
    first = client.post(f"/api/dedup/sets/{set_id}/members/{small}/trash", headers=HEADERS)
    assert first.status_code == 200 and first.json()["trashed"] == 1
    last = client.post(f"/api/dedup/sets/{set_id}/members/{full}/trash", headers=HEADERS)
    assert last.status_code == 409
    assert "last copy" in last.json()["detail"]
    assert live_ids(client, [keeper, full, small]) == [full]


def test_a_set_whose_keeper_is_trashed_lists_the_best_live_copy_as_keeper(client, tmp_path):
    set_id, keeper, full, small = near_set(client, tmp_path)
    client.post(f"/api/media/{keeper}/trash", headers=HEADERS)
    sets = client.get("/api/dedup/sets").json()["sets"]
    assert len(sets) == 1
    assert sets[0]["keeper"]["id"] == full
    assert sets[0]["keeper"]["trashed_ts"] is None
    assert [m["id"] for m in sets[0]["members"]] == [small]
    result = client.post(f"/api/dedup/sets/{set_id}/resolve", json={}, headers=HEADERS)
    assert result.status_code == 200 and result.json()["trashed"] == 1
    assert live_ids(client, [keeper, full, small]) == [full]


def test_a_set_left_with_one_live_copy_is_not_listed(client, tmp_path):
    _, keeper, _, small = near_set(client, tmp_path)
    client.post(f"/api/media/{keeper}/trash", headers=HEADERS)
    client.post(f"/api/media/{small}/trash", headers=HEADERS)
    assert client.get("/api/dedup/sets").json()["sets"] == []


def test_two_concurrent_trashes_never_take_the_last_two_live_copies(client, tmp_path, monkeypatch):
    import threading

    from app.db import reset_thread_conn
    from app.services import dedupsvc

    set_id, keeper, full, small = near_set(client, tmp_path)
    assert client.post(f"/api/media/{keeper}/trash", headers=HEADERS).status_code == 200
    gate = threading.Barrier(2, timeout=2)
    real_live = dedupsvc._live

    waited = threading.local()

    def slow_live(ids):
        rows = real_live(ids)
        if not getattr(waited, "done", False):
            waited.done = True
            try:
                gate.wait()
            except threading.BrokenBarrierError:
                pass
        return rows

    monkeypatch.setattr(dedupsvc, "_live", slow_live)
    results = {}

    def trash(media_id):
        try:
            results[media_id] = dedupsvc.trash_member(set_id, media_id)
        finally:
            reset_thread_conn()

    workers = [threading.Thread(target=trash, args=(m,)) for m in (full, small)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
    assert sorted(r["trashed"] for r in results.values()) == [0, 1]
    assert len(live_ids(client, [keeper, full, small])) == 1


def test_the_stored_keeper_is_not_trashed_through_the_member_route(client, tmp_path):
    set_id, keeper, full, small = near_set(client, tmp_path)
    result = client.post(f"/api/dedup/sets/{set_id}/members/{keeper}/trash", headers=HEADERS)
    assert result.status_code == 200 and result.json()["trashed"] == 0
    assert live_ids(client, [keeper, full, small]) == sorted([keeper, full, small])


def test_listing_sets_reads_media_in_a_fixed_number_of_queries(client, tmp_path):
    from app.db import connect
    from app.services import dedupsvc

    from app.db import ex, exmany

    _, keeper, full, small = near_set(client, tmp_path)
    for kept, others in ((full, (keeper, small)), (small, (full,)), (keeper, (small,)), (full, (small,))):
        set_id = ex("INSERT INTO dup_sets(job_ts, match_kind, similarity, keeper_media_id) VALUES(1, 'visual', 90, ?)", (kept,))
        exmany("INSERT INTO dup_members(set_id, media_id, similarity) VALUES(?,?,?)", [(set_id, o, 91) for o in others])
    before = dedupsvc.list_sets()
    assert len(before) == 5
    seen = []
    conn = connect()
    conn.set_trace_callback(seen.append)
    try:
        again = dedupsvc.list_sets()
    finally:
        conn.set_trace_callback(None)
    assert again == before
    assert len([s for s in seen if "FROM media" in s]) <= 2
    assert len(seen) <= 6

"""Attachments: images and documents up to 1 MB on incidents, problems, defects, changes and releases."""
from conftest import IDS, as_user

API = "/api/v1"
MB = 1024 * 1024

PNG = b"\x89PNG\r\n\x1a\n" + b"fake image data " * 8
PDF = b"%PDF-1.4\n" + b"fake document " * 8


def upload(client, who, kind, rid, name="shot.png", data=PNG, ctype="image/png"):
    return client.post(f"{API}/{kind}/{rid}/attachments", files={"file": (name, data, ctype)}, headers=as_user(who))


def attachments(client, who, kind, rid):
    return client.get(f"{API}/{kind}/{rid}/attachments", headers=as_user(who))


def new_incident(client, who="devemp"):
    r = client.post(f"{API}/incidents", json={"short_description": "Posting is slow"}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def new_problem(client, who="devemp"):
    return client.post(f"{API}/problems", json={"title": "Recurring failures"}, headers=as_user(who)).json()


def new_defect(client, who="devemp"):
    return client.post(f"{API}/defects", json={"title": "Totals are wrong"}, headers=as_user(who)).json()


def new_change(client, who="devmgr"):
    body = {"title": "Upgrade ERP patch", "implementation_plan": "x", "backout_plan": "y",
            "planned_start": "2026-11-01T09:00:00Z"}
    r = client.post(f"{API}/changes", json=body, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


def new_release(client, who="devmgr"):
    r = client.post(f"{API}/releases", json={"name": "Q4 release"}, headers=as_user(who))
    assert r.status_code == 201, r.text
    return r.json()


# ---- the happy path ------------------------------------------------------------------------

def test_upload_list_and_download_roundtrip(client, app):
    inc = new_incident(client)
    r = upload(client, "devemp", "incidents", inc["id"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["file_name"] == "shot.png" and a["content_type"] == "image/png" and a["size_bytes"] == len(PNG)
    assert a["uploaded_by_name"] == "Devemp" and a["can_delete"] is True

    listing = attachments(client, "devemp", "incidents", inc["id"]).json()
    assert [x["file_name"] for x in listing["items"]] == ["shot.png"]
    assert listing["can_upload"] is True and listing["max_bytes"] == MB and "pdf" in listing["allowed_extensions"]

    d = client.get(f"{API}/attachments/{a['id']}/download", headers=as_user("devemp"))
    assert d.status_code == 200 and d.content == PNG
    assert d.headers["content-type"] == "image/png"
    assert d.headers["content-disposition"].startswith("attachment;") and "shot.png" in d.headers["content-disposition"]
    assert d.headers["x-content-type-options"] == "nosniff"
    paths = list(app.state.fake_file_store.files)
    assert paths == [f"incident/{inc['id']}/{a['id']}.png"]                      # the path never uses the uploaded name


def test_a_pdf_and_a_text_file(client):
    inc = new_incident(client)
    assert upload(client, "devemp", "incidents", inc["id"], "report.pdf", PDF, "application/pdf").status_code == 201
    assert upload(client, "devemp", "incidents", inc["id"], "notes.txt", b"some notes", "text/plain").status_code == 201
    assert upload(client, "devemp", "incidents", inc["id"], "SHOT.PNG", PNG, "image/png").status_code == 201   # any case
    names = [x["file_name"] for x in attachments(client, "devemp", "incidents", inc["id"]).json()["items"]]
    assert sorted(names) == ["SHOT.PNG", "notes.txt", "report.pdf"]


# ---- the 1 MB limit ------------------------------------------------------------------------

def test_exactly_one_megabyte_is_accepted_and_one_byte_more_is_refused(client):
    inc = new_incident(client)
    ok = upload(client, "devemp", "incidents", inc["id"], "exact.txt", b"a" * MB, "text/plain")
    assert ok.status_code == 201 and ok.json()["size_bytes"] == MB
    too_big = upload(client, "devemp", "incidents", inc["id"], "big.txt", b"a" * (MB + 1), "text/plain")
    assert too_big.status_code == 413 and too_big.json()["error"]["code"] == "file_too_large"
    assert "1 MB" in too_big.json()["error"]["message"]
    assert len(attachments(client, "devemp", "incidents", inc["id"]).json()["items"]) == 1


def test_a_huge_upload_is_refused_before_it_is_read(client):
    inc = new_incident(client)
    r = upload(client, "devemp", "incidents", inc["id"], "huge.txt", b"a" * (3 * MB), "text/plain")
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert attachments(client, "devemp", "incidents", inc["id"]).json()["items"] == []


# ---- what may be attached ------------------------------------------------------------------

def test_file_type_rules(client, app):
    inc = new_incident(client)
    iid = inc["id"]
    for name in ("run.exe", "page.html", "image.svg", "script.js", "archive.zip", "noextension", "macro.docm"):
        r = upload(client, "devemp", "incidents", iid, name, b"data", "application/octet-stream")
        assert r.status_code == 415 and r.json()["error"]["code"] == "file_type_not_allowed", name
    fake = upload(client, "devemp", "incidents", iid, "fake.png", b"<html>not an image</html>", "image/png")
    assert fake.status_code == 415 and fake.json()["error"]["code"] == "file_type_mismatch"
    empty = upload(client, "devemp", "incidents", iid, "empty.txt", b"", "text/plain")
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "empty_file"
    assert app.state.fake_file_store.files == {}                                   # nothing was stored


def test_the_uploaded_name_is_cleaned_and_cannot_change_the_storage_path(client, app):
    inc = new_incident(client)
    r = upload(client, "devemp", "incidents", inc["id"], "../../etc/passwd.txt", b"hello", "text/plain")
    assert r.status_code == 201 and r.json()["file_name"] == "passwd.txt"
    assert all(p.startswith(f"incident/{inc['id']}/") and ".." not in p for p in app.state.fake_file_store.files)


# ---- who can see and add files on incidents, problems and defects --------------------------

def test_scoping_follows_the_record(client):
    inc = new_incident(client, "devemp")
    iid = inc["id"]
    a = upload(client, "devemp", "incidents", iid).json()
    for who in ("devemp2", "supemp", "supmgr"):                                       # cannot see the incident
        assert attachments(client, who, "incidents", iid).status_code == 404, who
        assert upload(client, who, "incidents", iid).status_code == 404, who
        assert client.get(f"{API}/attachments/{a['id']}/download", headers=as_user(who)).status_code == 404, who
        assert client.delete(f"{API}/attachments/{a['id']}", headers=as_user(who)).status_code == 404, who
    for who in ("devmgr", "admin"):
        assert attachments(client, who, "incidents", iid).status_code == 200
        assert client.get(f"{API}/attachments/{a['id']}/download", headers=as_user(who)).status_code == 200
    assert upload(client, "devmgr", "incidents", iid, "log.txt", b"trace", "text/plain").status_code == 201
    assert client.get(f"{API}/attachments/00000000-0000-0000-0000-0000000000ff/download",
                      headers=as_user("admin")).status_code == 404


def test_problems_and_defects_work_the_same_way(client):
    prob, dfct = new_problem(client, "devemp"), new_defect(client, "devemp")
    for kind, rec in (("problems", prob), ("defects", dfct)):
        assert upload(client, "devemp", kind, rec["id"]).status_code == 201, kind
        assert attachments(client, "devemp2", kind, rec["id"]).status_code == 404, kind
        assert upload(client, "devmgr", kind, rec["id"], "doc.pdf", PDF, "application/pdf").status_code == 201, kind
        assert len(attachments(client, "admin", kind, rec["id"]).json()["items"]) == 2, kind


def test_removing_files(client, app):
    inc = new_incident(client, "devemp")
    iid = inc["id"]
    mine = upload(client, "devemp", "incidents", iid).json()
    staffs = upload(client, "devmgr", "incidents", iid, "log.txt", b"trace", "text/plain").json()
    listing = {x["file_name"]: x for x in attachments(client, "devemp", "incidents", iid).json()["items"]}
    assert listing["shot.png"]["can_delete"] is True and listing["log.txt"]["can_delete"] is False
    assert client.delete(f"{API}/attachments/{staffs['id']}", headers=as_user("devemp")).status_code == 403
    assert client.delete(f"{API}/attachments/{mine['id']}", headers=as_user("devemp")).status_code == 204   # the uploader
    assert len(app.state.fake_file_store.files) == 1                                  # also gone from storage
    assert client.delete(f"{API}/attachments/{staffs['id']}", headers=as_user("admin")).status_code == 204
    assert client.delete(f"{API}/attachments/{staffs['id']}", headers=as_user("admin")).status_code == 404
    assert app.state.fake_file_store.files == {}
    other = upload(client, "devemp", "incidents", iid).json()
    assert client.delete(f"{API}/attachments/{other['id']}", headers=as_user("devmgr")).status_code == 204   # works the record


def test_no_files_can_be_added_to_a_closed_record(client):
    inc = new_incident(client)
    iid = inc["id"]
    client.post(f"{API}/incidents/{iid}/assign", json={"assignee_id": str(IDS["devmgr"])}, headers=as_user("admin"))
    for to, extra in (("In Progress", {}), ("Resolved", {"resolution_notes": "Fixed"}), ("Closed", {})):
        assert client.post(f"{API}/incidents/{iid}/transition", json={"to_status": to, **extra},
                           headers=as_user("devmgr")).status_code == 200
    r = upload(client, "devmgr", "incidents", iid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_closed"
    assert attachments(client, "devemp", "incidents", iid).json()["can_upload"] is False


# ---- changes and releases: everyone reads, only staff add ---------------------------------

def test_changes_and_releases_are_read_only_for_customers(client):
    chg, rel = new_change(client), new_release(client)
    for kind, rec in (("changes", chg), ("releases", rel)):
        a = upload(client, "devmgr", kind, rec["id"], "plan.pdf", PDF, "application/pdf")
        assert a.status_code == 201, (kind, a.text)
        for who in ("devemp", "supemp", "supmgr"):                                   # can read, cannot add
            listing = attachments(client, who, kind, rec["id"])
            assert listing.status_code == 200 and listing.json()["can_upload"] is False, (kind, who)
            assert len(listing.json()["items"]) == 1
            assert client.get(f"{API}/attachments/{a.json()['id']}/download", headers=as_user(who)).status_code == 200
            denied = upload(client, who, kind, rec["id"])
            assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden", (kind, who)
            assert client.delete(f"{API}/attachments/{a.json()['id']}", headers=as_user(who)).status_code == 403
        assert upload(client, "admin", kind, rec["id"], "extra.txt", b"more", "text/plain").status_code == 201
        assert attachments(client, "devmgr", kind, rec["id"]).json()["can_upload"] is True


# ---- storage problems ----------------------------------------------------------------------

def test_a_storage_failure_leaves_no_half_saved_attachment(client, app):
    inc = new_incident(client)
    app.state.fake_file_store.fail_puts = True
    r = upload(client, "devemp", "incidents", inc["id"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    app.state.fake_file_store.fail_puts = False
    assert attachments(client, "devemp", "incidents", inc["id"]).json()["items"] == []
    assert upload(client, "devemp", "incidents", inc["id"]).status_code == 201     # and it works again


def test_a_file_missing_from_storage_is_reported_clearly(client, app):
    inc = new_incident(client)
    a = upload(client, "devemp", "incidents", inc["id"]).json()
    app.state.fake_file_store.files.clear()
    r = client.get(f"{API}/attachments/{a['id']}/download", headers=as_user("devemp"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "file_missing"


def test_login_and_valid_kind_are_required(client):
    inc = new_incident(client)
    assert client.get(f"{API}/incidents/{inc['id']}/attachments").status_code == 401
    assert client.post(f"{API}/incidents/{inc['id']}/attachments", files={"file": ("a.txt", b"x", "text/plain")}
                       ).status_code == 401
    assert client.get(f"{API}/users/{inc['id']}/attachments", headers=as_user("admin")).status_code == 422
    assert client.post(f"{API}/incidents/{inc['id']}/attachments", headers=as_user("devemp")).status_code == 422  # no file


# ---- attached files show up in the activity timeline ---------------------------------------

def test_attached_files_appear_in_the_activity_timeline_of_every_record_type(client):
    records = {"incidents": new_incident(client), "problems": new_problem(client), "defects": new_defect(client),
               "changes": new_change(client), "releases": new_release(client)}
    uploader = {"incidents": "devemp", "problems": "devemp", "defects": "devemp", "changes": "devmgr", "releases": "devmgr"}
    for kind, rec in records.items():
        up = upload(client, uploader[kind], kind, rec["id"], "screen.png")
        assert up.status_code == 201, (kind, up.text)
        events = client.get(f"{API}/{kind}/{rec['id']}/activity", headers=as_user(uploader[kind])).json()
        found = [e for e in events if e["type"] == "attachment"]
        assert len(found) == 1, kind
        e = found[0]
        assert e["text"] == "Attached screen.png" and e["attachment"]["id"] == up.json()["id"], kind
        assert e["attachment"]["file_name"] == "screen.png" and e["attachment"]["size_bytes"] == len(PNG)
        assert e["attachment"]["can_delete"] is True
        assert [x["at"] for x in events] == sorted((x["at"] for x in events), reverse=True), kind   # newest first
    # a read-only viewer sees the file in the timeline but cannot remove it
    chg = records["changes"]
    viewer = client.get(f"{API}/changes/{chg['id']}/activity", headers=as_user("supmgr")).json()
    assert [e["attachment"]["can_delete"] for e in viewer if e["type"] == "attachment"] == [False]
    emp = client.get(f"{API}/changes/{chg['id']}/activity", headers=as_user("devemp")).json()
    assert [e["attachment"]["can_delete"] for e in emp if e["type"] == "attachment"] == [False]
    # removing the file removes it from the timeline
    aid = [e for e in viewer if e["type"] == "attachment"][0]["attachment"]["id"]
    assert client.delete(f"{API}/attachments/{aid}", headers=as_user("devmgr")).status_code == 204
    after = client.get(f"{API}/changes/{chg['id']}/activity", headers=as_user("devmgr")).json()
    assert not any(e["type"] == "attachment" for e in after)


def test_activity_does_not_leak_files_of_records_you_cannot_see(client):
    inc = new_incident(client, "devemp")
    upload(client, "devemp", "incidents", inc["id"])
    assert client.get(f"{API}/incidents/{inc['id']}/activity", headers=as_user("supmgr")).status_code == 404
    assert client.get(f"{API}/incidents/{inc['id']}/activity", headers=as_user("devemp2")).status_code == 404

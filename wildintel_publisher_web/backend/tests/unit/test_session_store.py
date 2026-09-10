"""Unit tests for services.session_store — the phase-agnostic session-
directory primitives shared by the fetch-task services (trapper_service.py/
software_service.py/camtrapdp_source_service.py), the generate-metadata
router, and services.publish_orchestrator."""
from services import session_store


def test_new_task_id_returns_a_distinct_uuid_each_time():
    assert session_store.new_task_id() != session_store.new_task_id()


def test_session_dir_is_a_subdirectory_of_the_sessions_root():
    task_id = "task-1"
    assert session_store.session_dir(task_id).name == task_id


def test_read_manifest_returns_none_when_no_session_exists():
    assert session_store.read_manifest("does-not-exist") is None


def test_write_and_read_manifest_round_trips():
    task_id = session_store.new_task_id()
    session_store.write_manifest(task_id, {"task_id": task_id, "phase": "fetching"})

    assert session_store.read_manifest(task_id) == {"task_id": task_id, "phase": "fetching"}


def test_write_manifest_is_atomic_and_leaves_no_tmp_file():
    task_id = session_store.new_task_id()
    session_store.write_manifest(task_id, {"task_id": task_id})

    files = {p.name for p in session_store.session_dir(task_id).iterdir()}
    assert files == {"session.json"}


def test_scrub_secrets_removes_only_the_given_keys():
    cfg = {"repo": "hfh", "token": "hf_x", "output_dir": "/tmp/out"}
    assert session_store.scrub_secrets(cfg, {"token", "password"}) == {"repo": "hfh", "output_dir": "/tmp/out"}


def test_write_fetch_phase_creates_a_session_with_fetching_phase_while_running():
    task_id = session_store.new_task_id()
    fetch = {"source_type": "trapper", "params": {"project_id": 1}, "output_dir": "/x", "input_dir": None}

    session_store.write_fetch_phase(
        task_id, product_type="camtrapdp", source_type="trapper", fetch=fetch, status="running", error=None,
    )

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "fetching"
    assert manifest["status"] == "running"
    assert manifest["product_type"] == "camtrapdp"
    assert manifest["source_type"] == "trapper"
    assert manifest["fetch"] == fetch
    assert manifest["created_at"]


def test_write_fetch_phase_transitions_to_fetched_on_success_without_losing_created_at():
    task_id = session_store.new_task_id()
    fetch = {"source_type": "archive", "params": {"url": "https://example.org/x.zip"}, "output_dir": "/x", "input_dir": None}
    session_store.write_fetch_phase(task_id, product_type="camtrapdp", source_type="archive", fetch=fetch, status="running", error=None)
    first_created_at = session_store.read_manifest(task_id)["created_at"]

    fetch["input_dir"] = "/x/camtrapdp-remote"
    session_store.write_fetch_phase(task_id, product_type="camtrapdp", source_type="archive", fetch=fetch, status="done", error=None)

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "fetched"
    assert manifest["status"] == "done"
    assert manifest["fetch"]["input_dir"] == "/x/camtrapdp-remote"
    assert manifest["created_at"] == first_created_at


def test_write_fetch_phase_never_persists_trapper_credentials():
    """Regression test for the security policy confirmed with the user:
    resuming a session always requires re-entering credentials — callers
    must scrub them before building `fetch`, but this asserts the module
    itself never adds them back in, and that a caller that (by mistake)
    left them in `fetch["params"]` would be immediately visible in the
    manifest text — nothing here silently strips a caller's own mistake."""
    task_id = session_store.new_task_id()
    fetch = {"source_type": "trapper", "params": {"project_id": 1, "deployment_id": "d1"}, "output_dir": "/x", "input_dir": None}

    session_store.write_fetch_phase(task_id, product_type="camtrapdp", source_type="trapper", fetch=fetch, status="running", error=None)

    manifest_text = (session_store.session_dir(task_id) / "session.json").read_text(encoding="utf-8")
    assert "username" not in manifest_text
    assert "password" not in manifest_text


def test_write_preprocessing_phase_is_a_noop_when_no_session_exists():
    task_id = session_store.new_task_id()

    session_store.write_preprocessing_phase(task_id, status="done", error=None, choices={"anonymize_coordinates": True})

    assert session_store.read_manifest(task_id) is None


def test_write_preprocessing_phase_updates_an_existing_fetch_session():
    task_id = session_store.new_task_id()
    fetch = {"source_type": "git", "params": {"url": "https://example.org/repo.git"}, "output_dir": "/x", "input_dir": "/x/repo"}
    session_store.write_fetch_phase(task_id, product_type="software", source_type="git", fetch=fetch, status="done", error=None)

    session_store.write_preprocessing_phase(
        task_id, status="done", error=None,
        choices={"anonymize_coordinates": False, "coordinate_decimals": 2, "randomize_media_ids": True, "media_id_domain": "example.org"},
    )

    manifest = session_store.read_manifest(task_id)
    assert manifest["phase"] == "preprocessed"
    assert manifest["preprocessing"] == {
        "status": "done", "anonymize_coordinates": False, "coordinate_decimals": 2,
        "randomize_media_ids": True, "media_id_domain": "example.org",
    }
    # The fetch phase's own section survives untouched.
    assert manifest["fetch"] == fetch
    assert manifest["source_type"] == "git"


def test_list_sessions_returns_sessions_of_any_phase_and_skips_done_ones():
    fetching_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        fetching_id, product_type="camtrapdp", source_type="trapper",
        fetch={"source_type": "trapper", "params": {}, "output_dir": "/x", "input_dir": None},
        status="running", error=None,
    )
    done_id = session_store.new_task_id()
    session_store.write_manifest(done_id, {"task_id": done_id, "phase": "done", "status": "done"})

    sessions = session_store.list_sessions()

    task_ids = {s["task_id"] for s in sessions}
    assert fetching_id in task_ids
    assert done_id not in task_ids
    assert not session_store.session_dir(done_id).exists()  # cleaned up defensively


def test_list_sessions_keeps_a_session_whose_fetch_or_preprocessing_phase_merely_succeeded():
    """Regression test: write_fetch_phase/write_preprocessing_phase set the
    manifest's own "status" to "done" as soon as THEIR OWN step succeeds
    (see test_write_fetch_phase_transitions_to_fetched_on_success_without_losing_created_at
    above) — long before the whole run is finished. list_sessions must key
    off "phase" (only ever "done" once publish_orchestrator's own run
    completes), not "status", or every session would vanish the moment its
    fetch/preprocessing step succeeded, even though there's nothing left to
    resume yet — it just hasn't been picked up by the next phase."""
    fetched_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        fetched_id, product_type="camtrapdp", source_type="archive",
        fetch={"source_type": "archive", "params": {"url": "https://example.org/x.zip"}, "output_dir": "/x", "input_dir": "/x/camtrapdp"},
        status="done", error=None,
    )
    preprocessed_id = session_store.new_task_id()
    session_store.write_fetch_phase(
        preprocessed_id, product_type="camtrapdp", source_type="git",
        fetch={"source_type": "git", "params": {"url": "https://example.org/repo.git"}, "output_dir": "/y", "input_dir": "/y/repo"},
        status="done", error=None,
    )
    session_store.write_preprocessing_phase(
        preprocessed_id, status="done", error=None,
        choices={"anonymize_coordinates": False, "coordinate_decimals": 2, "randomize_media_ids": False, "media_id_domain": "localhost"},
    )

    task_ids = {s["task_id"] for s in session_store.list_sessions()}

    assert fetched_id in task_ids
    assert preprocessed_id in task_ids
    assert session_store.session_dir(fetched_id).exists()
    assert session_store.session_dir(preprocessed_id).exists()


def test_discard_session_removes_the_whole_directory():
    task_id = session_store.new_task_id()
    session_store.write_manifest(task_id, {"task_id": task_id})
    assert session_store.session_dir(task_id).exists()

    session_store.discard_session(task_id)

    assert not session_store.session_dir(task_id).exists()


def test_discard_session_on_a_nonexistent_session_does_not_raise():
    session_store.discard_session("never-existed")

"""common.check_repository_limits — the size/file-count limits Zenodo and B2SHARE enforce on a record."""


def _limits_dir(tmp_path, sizes):
    directory = tmp_path / "record"
    directory.mkdir()
    for index, size in enumerate(sizes):
        (directory / f"f{index}.bin").write_bytes(b"x" * size)
    (directory / "metadata.json").write_text("x" * 1000, encoding="utf-8")  # bookkeeping: never counted
    return directory


def test_repository_limits_accept_a_record_within_them(tmp_path):
    from wildintel_publisher.core.services import common

    common.check_repository_limits(
        _limits_dir(tmp_path, [10, 10]), repository="Zenodo", max_record_bytes=100, max_files=2, max_file_bytes=10,
    )


def test_repository_limits_reject_too_many_files(tmp_path):
    import pytest
    from wildintel_publisher.core.services import common

    with pytest.raises(RuntimeError, match="3 files, over its limit of 2"):
        common.check_repository_limits(
            _limits_dir(tmp_path, [1, 1, 1]), repository="Zenodo", max_record_bytes=None, max_files=2, max_file_bytes=None,
        )


def test_repository_limits_reject_a_file_that_is_too_big(tmp_path):
    import pytest
    from wildintel_publisher.core.services import common

    with pytest.raises(RuntimeError, match="f1.bin.*per file"):
        common.check_repository_limits(
            _limits_dir(tmp_path, [1, 50]), repository="B2SHARE", max_record_bytes=None, max_files=None, max_file_bytes=10,
        )


def test_repository_limits_reject_a_record_that_is_too_big(tmp_path):
    import pytest
    from wildintel_publisher.core.services import common

    with pytest.raises(RuntimeError, match="per record"):
        common.check_repository_limits(
            _limits_dir(tmp_path, [30, 30]), repository="Zenodo", max_record_bytes=50, max_files=None, max_file_bytes=None,
        )

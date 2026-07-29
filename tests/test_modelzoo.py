"""Model provisioning: layout detection, manual zip import, mirror fallback."""

import io
import zipfile

import pytest

from facesort.core import modelzoo


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point INSIGHTFACE_HOME at a temp dir so nothing touches the real cache."""
    monkeypatch.setenv("INSIGHTFACE_HOME", str(tmp_path / "insightface"))
    monkeypatch.delenv("FACESORT_MODEL_DIR", raising=False)
    monkeypatch.delenv("FACESORT_MODEL_URL", raising=False)
    return tmp_path


def _make_zip(path, prefix=""):
    with zipfile.ZipFile(path, "w") as zf:
        for name in modelzoo.REQUIRED_FILES:
            zf.writestr(f"{prefix}{name}", b"onnx-bytes" * 100)
        zf.writestr(f"{prefix}1k3d68.onnx", b"extra")
    return path


def test_not_installed_on_a_clean_machine(home):
    assert modelzoo.is_installed() is False
    assert modelzoo.status()["installed"] is False


def test_install_from_flat_zip(home, tmp_path):
    zip_path = _make_zip(tmp_path / "buffalo_l.zip")

    modelzoo.install_from_zip(zip_path)

    assert modelzoo.is_installed()
    for name in modelzoo.REQUIRED_FILES:
        assert (modelzoo.model_dir() / name).is_file()


def test_install_from_nested_zip(home, tmp_path):
    """Some copies of the asset wrap the files in a buffalo_l/ directory."""
    zip_path = _make_zip(tmp_path / "nested.zip", prefix="buffalo_l/")

    modelzoo.install_from_zip(zip_path)

    assert modelzoo.is_installed()
    assert (modelzoo.model_dir() / "det_10g.onnx").is_file()


def test_install_replaces_an_existing_broken_install(home, tmp_path):
    d = modelzoo.model_dir()
    d.mkdir(parents=True)
    (d / "det_10g.onnx").write_bytes(b"truncated")  # w600k_r50 missing
    assert not modelzoo.is_installed()

    modelzoo.install_from_zip(_make_zip(tmp_path / "b.zip"))

    assert modelzoo.is_installed()


def test_zip_without_model_files_is_rejected(home, tmp_path):
    bad = tmp_path / "wrong.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("readme.txt", b"nope")

    with pytest.raises(modelzoo.ModelError) as e:
        modelzoo.install_from_zip(bad)
    assert "buffalo_l" in str(e.value)
    assert not modelzoo.is_installed()


def test_corrupt_zip_is_rejected(home, tmp_path):
    bad = tmp_path / "corrupt.zip"
    bad.write_bytes(b"not a zip at all")

    with pytest.raises(modelzoo.ModelError):
        modelzoo.install_from_zip(bad)


def test_missing_file_is_reported(home, tmp_path):
    with pytest.raises(modelzoo.ModelError):
        modelzoo.install_from_zip(tmp_path / "does-not-exist.zip")


def test_bundled_copy_is_used_before_downloading(home, tmp_path, monkeypatch):
    bundled = tmp_path / "bundled" / "buffalo_l"
    bundled.mkdir(parents=True)
    for name in modelzoo.REQUIRED_FILES:
        (bundled / name).write_bytes(b"x")
    monkeypatch.setenv("FACESORT_MODEL_DIR", str(bundled))

    def fail(*a, **k):
        raise AssertionError("must not hit the network when a copy is bundled")

    monkeypatch.setattr(modelzoo, "download", fail)

    modelzoo.ensure_model()

    assert modelzoo.is_installed()


def test_ensure_model_is_a_no_op_when_already_installed(home, tmp_path, monkeypatch):
    modelzoo.install_from_zip(_make_zip(tmp_path / "b.zip"))
    monkeypatch.setattr(modelzoo, "download",
                        lambda *a, **k: pytest.fail("should not download"))

    assert modelzoo.ensure_model() == modelzoo.model_dir()


def test_custom_url_takes_priority(home, monkeypatch):
    monkeypatch.setenv("FACESORT_MODEL_URL", "https://example.invalid/b.zip")
    ids = [s["id"] for s in modelzoo.sources()]
    assert ids[0] == "custom"
    assert "github" in ids  # official source stays as a fallback


def test_download_falls_back_to_the_next_mirror(home, tmp_path, monkeypatch):
    """First mirror times out, second serves the zip — the user sees neither."""
    payload = _make_zip(tmp_path / "src.zip").read_bytes()
    calls = []

    class FakeResponse(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise TimeoutError("connection timed out")
        return FakeResponse(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    modelzoo.download()

    assert len(calls) == 2
    assert modelzoo.is_installed()


def test_download_error_lists_every_failed_source(home, monkeypatch):
    def always_fail(req, timeout=None):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr("urllib.request.urlopen", always_fail)

    with pytest.raises(modelzoo.ModelError) as e:
        modelzoo.download()

    msg = str(e.value)
    for src in modelzoo.SOURCES:
        assert src["label"] in msg
    # Points at the escape hatch rather than dead-ending.
    assert "手动导入" in msg


def test_download_reports_progress(home, tmp_path, monkeypatch):
    payload = _make_zip(tmp_path / "src.zip").read_bytes()

    class FakeResponse(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: FakeResponse(payload))
    events = []

    modelzoo.download(on_progress=events.append)

    assert any(e.get("phase") == "download" for e in events)
    assert events[-1]["phase"] in ("download", "extract")


# ---- progress detail & cancellation -----------------------------------
#
# The download used to run deep inside analyze() with neither a progress
# callback nor a cancel token wired up, so the UI sat on a blank "preparing"
# state for a 289MB transfer that no button could stop.


class _SlowResponse(io.RawIOBase):
    """Streams forever in small chunks so cancellation can be observed."""

    headers = {"Content-Length": str(modelzoo.ZIP_SIZE)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        import time
        time.sleep(0.01)
        return b"\0" * (1 << 18)


def test_download_progress_reports_percent_speed_and_eta(home, tmp_path, monkeypatch):
    payload = _make_zip(tmp_path / "src.zip").read_bytes()

    class Resp(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n=-1):  # force several chunks so progress is emitted
            return super().read(min(n, 4096) if n and n > 0 else n)

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: Resp(payload))
    events = []
    modelzoo.download(on_progress=events.append)

    downloads = [e for e in events if e.get("phase") == "download"]
    assert downloads, "no download progress emitted"
    last = downloads[-1]
    for key in ("percent", "done", "total", "bytesPerSec", "etaSeconds"):
        assert key in last, key
    assert last["percent"] == pytest.approx(100.0, abs=0.01)
    assert 0 <= downloads[0]["percent"] <= 100
    # The mirror being used is named, and which attempt it is.
    assert last["source"] and last["attempt"] == 1 and last["attempts"] >= 1
    assert events[0]["phase"] == "connect"


def test_download_is_cancellable_mid_transfer(home, monkeypatch):
    import threading
    import time

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: _SlowResponse())
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()

    t0 = time.monotonic()
    with pytest.raises(modelzoo.ModelCancelled):
        modelzoo.download(cancel=cancel)
    elapsed = time.monotonic() - t0

    assert elapsed < 5, f"cancel was not honored promptly ({elapsed:.1f}s)"
    assert not modelzoo.is_installed()


def test_cancel_before_start_short_circuits(home, monkeypatch):
    import threading

    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: pytest.fail("should not connect"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(modelzoo.ModelCancelled):
        modelzoo.download(cancel=cancel)


def test_ensure_model_forwards_cancel(home, monkeypatch):
    """The engine passes its cancel token down; make sure it is not dropped."""
    import threading

    seen = {}

    def fake_download(source_id=None, on_progress=None, cancel=None):
        seen["cancel"] = cancel
        raise modelzoo.ModelCancelled("已取消下载")

    monkeypatch.setattr(modelzoo, "download", fake_download)
    token = threading.Event()
    with pytest.raises(modelzoo.ModelCancelled):
        modelzoo.ensure_model(cancel=token)
    assert seen["cancel"] is token

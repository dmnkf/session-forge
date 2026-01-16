from sf.core.locks import lock_path, wrap_with_lock


def test_lock_path_and_wrapper():
    path = lock_path("core/demo")
    assert path.startswith("/tmp/sf.lock.")
    command = wrap_with_lock("core/demo", "echo hello")
    assert "flock" in command
    assert "echo hello" in command

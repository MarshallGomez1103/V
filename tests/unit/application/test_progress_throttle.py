from voz.application.progress_throttle import ProgressThrottle


def test_allows_the_first_call_then_at_most_one_per_interval() -> None:
    now = {"t": 100.0}
    throttle = ProgressThrottle(0.5, lambda: now["t"])

    assert throttle.ready()
    now["t"] += 0.4
    assert not throttle.ready()
    now["t"] += 0.1  # 0.5 s since the last allowed call
    assert throttle.ready()
    assert not throttle.ready()

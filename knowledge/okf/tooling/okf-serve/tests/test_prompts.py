from okfserve import prompts


def test_investigate_grounds_and_tracks():
    p = prompts.investigate("slow waves")
    assert "slow waves" in p
    assert "sources:" in p
    assert "start_objective" in p and "investigate" in p


def test_implementation_advisor():
    p = prompts.implementation_advisor("configure replen")
    assert "configure replen" in p
    assert "sources:" in p and "implement" in p


def test_guided_learning():
    p = prompts.guided_learning("wave/replen")
    assert "wave/replen" in p
    assert "record_quiz_result" in p and "learn" in p and "sources:" in p

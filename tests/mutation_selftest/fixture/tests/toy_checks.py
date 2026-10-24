from toy import add


def test_add_weak():
    # Deliberately weak: a - b also gives 0 here, so the a - b mutant survives.
    assert add(0, 0) == 0

from orbit.goal.verifier import ExecutorVerifier, VerificationResult
def test_result():
    r = VerificationResult()
    assert r.all_passed is True
def test_verifier():
    assert ExecutorVerifier() is not None

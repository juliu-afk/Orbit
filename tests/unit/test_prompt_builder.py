from orbit.prompt.builder import PromptBuilder
def test_init():
    p = PromptBuilder()
    assert p is not None

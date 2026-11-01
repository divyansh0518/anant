from anant.jetson.llm import split_expression
from anant.jetson.memory import Memory


def test_memory_learns_and_recalls():
    m = Memory(":memory:")
    m.add_turn("asha", "user", "Hi, my name is Asha and I love robotics.")
    m.add_turn("asha", "assistant", "Nice to meet you!")
    assert m.facts("asha")["name"] == ["Asha"]
    assert "robotics" in m.facts("asha")["likes"][0]
    assert [t["role"] for t in m.recent("asha")] == ["user", "assistant"]
    assert m.recent("bob") == []


def test_expression_tag_parsing():
    valid = ["neutral", "happy", "pain"]
    assert split_expression("[Happy] Hello there", valid) == ("happy", "Hello there")
    assert split_expression("[angry] hi", valid) == ("neutral", "hi")
    assert split_expression("plain", valid) == ("neutral", "plain")

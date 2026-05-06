import pytest
from ranker.db import SelectionDB


@pytest.fixture
def db(tmp_path):
    return SelectionDB(tmp_path / "test.db")


def test_record_selection(db):
    db.record_selection("nihao", "你", "你好", ["你好", "泥号", "拟好"], 0)
    assert db.get_selection_count() == 1


def test_unigram_frequency(db):
    db.record_selection("nihao", "", "你好", ["你好", "泥号"], 0)
    db.record_selection("nihao", "", "你好", ["你好", "泥号"], 0)
    db.record_selection("nihao", "", "泥号", ["你好", "泥号"], 1)
    assert db.get_unigram_freq("你好") == 2
    assert db.get_unigram_freq("泥号") == 1
    assert db.get_unigram_freq("不存在") == 0


def test_bigram_frequency(db):
    db.record_selection("nihao", "你", "你好", ["你好"], 0)
    db.record_selection("nihao", "你", "你好", ["你好"], 0)
    db.record_selection("nihao", "我", "你好", ["你好"], 0)
    assert db.get_bigram_freq("你", "你好") == 2
    assert db.get_bigram_freq("我", "你好") == 1
    assert db.get_bigram_freq("他", "你好") == 0


def test_last_used_timestamp(db):
    db.record_selection("nihao", "", "你好", ["你好"], 0)
    ts = db.get_last_used("你好")
    assert ts is not None and ts > 0


def test_get_all_selections(db):
    db.record_selection("ni", "", "你", ["你", "尼"], 0)
    db.record_selection("hao", "你", "好", ["好", "号"], 0)
    rows = db.get_all_selections()
    assert len(rows) == 2
    assert rows[0]["pinyin"] == "ni"
    assert rows[1]["context"] == "你"

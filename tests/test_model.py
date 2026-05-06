import pytest
from ranker.db import SelectionDB
from ranker.model import RankingModel


@pytest.fixture
def db(tmp_path):
    return SelectionDB(tmp_path / "test.db")


@pytest.fixture
def model(db, tmp_path):
    return RankingModel(db, model_path=tmp_path / "model.pkl")


def test_rank_no_history(model):
    ranked = model.rank("nihao", "", ["你好", "泥号", "拟好"])
    assert set(ranked) == {"你好", "泥号", "拟好"}
    assert len(ranked) == 3


def test_rank_with_unigram_history(model, db):
    db.record_selection("nihao", "", "泥号", ["你好", "泥号"], 1)
    db.record_selection("nihao", "", "泥号", ["你好", "泥号"], 1)
    db.record_selection("nihao", "", "你好", ["你好", "泥号"], 0)
    ranked = model.rank("nihao", "", ["你好", "泥号", "拟好"])
    assert ranked[0] == "泥号"


def test_rank_with_bigram_boost(model, db):
    db.record_selection("hao", "你", "好", ["好", "号", "毫"], 0)
    db.record_selection("hao", "你", "好", ["好", "号", "毫"], 0)
    db.record_selection("hao", "你", "好", ["好", "号", "毫"], 0)
    db.record_selection("hao", "", "号", ["好", "号", "毫"], 1)
    db.record_selection("hao", "", "号", ["好", "号", "毫"], 1)
    db.record_selection("hao", "", "号", ["好", "号", "毫"], 1)
    db.record_selection("hao", "", "号", ["好", "号", "毫"], 1)
    ranked = model.rank("hao", "你", ["好", "号", "毫"])
    assert ranked[0] == "好"


def test_record_and_rerank(model, db):
    model.record("nihao", "", "拟好", ["你好", "泥号", "拟好"], 2)
    model.record("nihao", "", "拟好", ["你好", "泥号", "拟好"], 2)
    ranked = model.rank("nihao", "", ["你好", "泥号", "拟好"])
    assert ranked[0] == "拟好"


def test_phase1_active_by_default(model):
    assert model.current_phase() == 1


def test_phase2_activates_after_threshold(db, tmp_path):
    model = RankingModel(db, model_path=tmp_path / "model.pkl")
    candidates = ["好", "号", "毫"]
    for i in range(500):
        db.record_selection("hao", "你" if i % 2 == 0 else "我", "好", candidates, 0)
    model.maybe_train_phase2()
    assert model.current_phase() == 2


def test_phase2_ranking(db, tmp_path):
    model = RankingModel(db, model_path=tmp_path / "model.pkl")
    for _ in range(300):
        db.record_selection("hao", "你", "好", ["好", "号", "毫"], 0)
    for _ in range(100):
        db.record_selection("hao", "你", "好", ["毫", "好", "号"], 1)
    for _ in range(100):
        db.record_selection("hao", "你", "号", ["号", "好", "毫"], 0)
    model.maybe_train_phase2()
    ranked = model.rank("hao", "你", ["好", "号", "毫"])
    assert ranked[0] == "好"


def test_phase2_model_persistence(db, tmp_path):
    model_path = tmp_path / "model.pkl"
    model = RankingModel(db, model_path=model_path)
    candidates = ["好", "号"]
    for _ in range(500):
        db.record_selection("hao", "", "好", candidates, 0)
    model.maybe_train_phase2()
    assert model_path.exists()
    model2 = RankingModel(db, model_path=model_path)
    model2.load_phase2()
    assert model2.current_phase() == 2

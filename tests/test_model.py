import pytest
from ranker.db import SelectionDB
from ranker.model import RankingModel
from ranker.local_ranker import MIN_SAMPLES


@pytest.fixture
def db(tmp_path):
    return SelectionDB(tmp_path / "test.db")


@pytest.fixture
def model(db, tmp_path):
    return RankingModel(db, ftrl_weights_path=tmp_path / "ftrl_test.json")


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


def test_ftrl_phase2_blend(db):
    """FTRL should activate after MIN_SAMPLES selections and improve ranking."""
    model = RankingModel(db)
    cands = ["好", "号", "毫"]

    # Feed enough selections to activate FTRL (Phase 1 handles cold start)
    for _ in range(MIN_SAMPLES):
        model.record("hao", "你", "好", cands, 0)

    assert model.current_phase() == 2

    # After training, "好" should rank first with context "你"
    ranked = model.rank("hao", "你", cands)
    assert ranked[0] == "好"


def test_ftrl_persistence(db, tmp_path):
    """FTRL weights survive a model reload."""
    from ranker.local_ranker import FTRLRanker, FTRL_WEIGHTS_PATH
    import os

    # Use a temp path to avoid clobbering real weights
    weights_path = tmp_path / "ftrl_test.json"

    model1 = RankingModel(db)
    model1._ftrl = FTRLRanker(weights_path=weights_path)
    cands = ["好", "号"]
    for _ in range(MIN_SAMPLES):
        model1.record("hao", "", "好", cands, 0)

    assert weights_path.exists()

    model2 = RankingModel(db)
    model2._ftrl = FTRLRanker(weights_path=weights_path)
    assert model2._ftrl.ready
    assert model2.current_phase() == 2

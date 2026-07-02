"""Tier-1: policy document lifecycle — a corpus update must fully replace stale
values, not accumulate them alongside the new ones.

The golden dataset already covers superseded amounts within a single static
corpus (amendments.md overriding gold.md, see ctrl-gold-oop-amendment). This
module instead simulates the corpus itself changing between two points in
time — a real policy version bump, not just an amendment note — and asserts
retrieval reflects only the current version.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import PolicyRetriever
from verity.config import RetrievalConfig

pytestmark = pytest.mark.deterministic

_V1_GOLD = """\
# Gold Plan

## §2. Deductible

The Gold plan individual annual deductible is $750. This applies before
coinsurance on most services.

## §4. Out-of-Pocket Maximum

The Gold plan individual out-of-pocket maximum is $4,000 per plan year.
"""

_V2_GOLD = """\
# Gold Plan

## §2. Deductible

The Gold plan individual annual deductible is $900, effective the new plan
year. This applies before coinsurance on most services.

## §4. Out-of-Pocket Maximum

The Gold plan individual out-of-pocket maximum is $3,500 per plan year,
reduced from the prior year's figure.
"""


@pytest.fixture
def retriever(tmp_path: Path) -> PolicyRetriever:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "gold.md").write_text(_V1_GOLD)
    config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir, top_k=10)
    r = PolicyRetriever(config)
    r.index_corpus()
    return r


def _combined_text(retriever: PolicyRetriever, query: str) -> str:
    return "\n".join(c.text for c in retriever.retrieve(query))


class TestPolicyVersionLifecycle:
    def test_v1_deductible_is_retrievable_before_update(self, retriever: PolicyRetriever) -> None:
        text = _combined_text(retriever, "Gold plan deductible")
        assert "$750" in text

    def test_v2_deductible_replaces_v1_after_corpus_update(
        self, retriever: PolicyRetriever, tmp_path: Path
    ) -> None:
        (tmp_path / "corpus" / "gold.md").write_text(_V2_GOLD)
        retriever.index_corpus()

        text = _combined_text(retriever, "Gold plan deductible")
        assert "$900" in text
        assert "$750" not in text, "stale v1 deductible value still retrievable after update"

    def test_v2_oop_max_replaces_v1_after_corpus_update(
        self, retriever: PolicyRetriever, tmp_path: Path
    ) -> None:
        (tmp_path / "corpus" / "gold.md").write_text(_V2_GOLD)
        retriever.index_corpus()

        text = _combined_text(retriever, "Gold plan out-of-pocket maximum")
        assert "$3,500" in text
        assert "$4,000" not in text, "stale v1 OOP max value still retrievable after update"

    def test_reverting_to_v1_content_restores_v1_and_drops_v2(
        self, retriever: PolicyRetriever, tmp_path: Path
    ) -> None:
        """A version rollback (e.g. a corrected amendment retracted) must behave
        the same as a forward update: full replacement, not accumulation."""
        gold_path = tmp_path / "corpus" / "gold.md"
        gold_path.write_text(_V2_GOLD)
        retriever.index_corpus()

        gold_path.write_text(_V1_GOLD)
        retriever.index_corpus()

        text = _combined_text(retriever, "Gold plan deductible")
        assert "$750" in text
        assert "$900" not in text

    def test_no_op_reindex_does_not_duplicate_chunks(self, retriever: PolicyRetriever) -> None:
        """Indexing the same unchanged corpus twice must not double the stored
        chunk count — a version check that only compares fingerprints, not
        content, could otherwise silently accumulate duplicates."""
        collection = retriever._get_collection()
        count_after_first_index = collection.count()

        added = retriever.index_corpus()

        assert added == 0
        assert collection.count() == count_after_first_index

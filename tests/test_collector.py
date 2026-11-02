"""네트워크 없이 돌아가는 테스트. 실제 API 응답 형식을 본뜬 가짜 데이터를 사용합니다.

실행: python -m pytest -q
"""
import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import yaml

from collector.filter import KeywordFilter
from collector.main import run
from collector.models import Paper
from collector.sources.biorxiv import PreprintSource, to_paper
from collector.sources.pubmed import parse_article
from collector.storage import LocalJSONStorage

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text("utf-8"))

PUBMED_XML = """<PubmedArticleSet><PubmedArticle>
<MedlineCitation><PMID>41000001</PMID><Article>
<Journal><Title>Scientific Reports</Title></Journal>
<ArticleTitle>Chloroquine modulates <i>Foxp3</i> induction through Nurr1 in experimental colitis</ArticleTitle>
<Abstract><AbstractText Label="BACKGROUND">Nurr1 regulates T cell differentiation.</AbstractText>
<AbstractText Label="METHODS">We treated naive CD4 T cells with CQ and measured Foxp3 and Th17 markers.</AbstractText></Abstract>
<AuthorList><Author><LastName>Kim</LastName><ForeName>Jisoo</ForeName></Author><Author><CollectiveName>Treg Consortium</CollectiveName></Author></AuthorList>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
</Article></MedlineCitation>
<PubmedData><History><PubMedPubDate PubStatus="entrez"><Year>2026</Year><Month>10</Month><Day>15</Day></PubMedPubDate></History>
<ArticleIdList><ArticleId IdType="pubmed">41000001</ArticleId><ArticleId IdType="doi">10.1000/HEP.2026.1</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""

BIORXIV_ITEM = {
    "title": "PGE1 enhances iTreg development via the EP4 receptor and cAMP signaling",
    "authors": "Lee, A.; Park, B.",
    "doi": "10.1101/2026.10.01.000001", "date": "2026-10-14", "version": "2",
    "category": "immunology",
    "abstract": "Prostaglandin E1 raised Foxp3 and CD25 in regulatory T cells through cAMP, and TSDR demethylation was sustained.",
    "published": "NA", "server": "bioRxiv",
}


def kf():
    return KeywordFilter.from_config(CFG)


def test_pubmed_parse_and_filter():
    art = ET.fromstring(PUBMED_XML).find("PubmedArticle")
    p = parse_article(art)
    assert p.id == "doi:10.1000/hep.2026.1"
    assert p.date == "2026-10-15"
    assert p.authors == ["Jisoo Kim", "Treg Consortium"]
    assert "Foxp3" in p.title and "METHODS:" in p.abstract
    assert kf().apply(p)
    assert set(p.matched_compound) == {"quinoline", "nr4a"}
    assert set(p.matched_topics) >= {"treg", "t_helper", "autoimmune_model"}


def test_biorxiv_parse_and_filter():
    p = to_paper(BIORXIV_ITEM, "biorxiv")
    assert p.is_preprint and p.version == "2" and p.published_doi is None
    assert p.url.endswith("v2")
    assert kf().apply(p)
    assert p.matched_compound == ["prostaglandin"]
    assert set(p.matched_topics) >= {"treg", "stability"}


def test_filter_rejects_and_abbreviation_rules():
    f = kf()
    off_compound = Paper(id="x", source="pubmed", title="Rapamycin expands regulatory T cells",
                         abstract="mTOR inhibition raises Foxp3", authors=[], date="", url="")
    assert not f.apply(off_compound)   # 면역 주제만 맞고 관심 물질이 아님
    off_topic = Paper(id="w", source="pubmed", title="Chloroquine inhibits autophagy in hepatocytes",
                      abstract="Lysosomal pH rises after treatment.", authors=[], date="", url="")
    assert not f.apply(off_topic)      # 물질만 맞고 면역/Treg 맥락이 없음 (require_topics)
    acq = Paper(id="y", source="pubmed", title="Acquired tolerance in grafts",
                abstract="acquired and acquisition of Foxp3", authors=[], date="", url="")
    assert not f.apply(acq)            # "CQ"/"AQ" 약어가 일반 단어에 걸리면 안 됨
    nurr = Paper(id="z", source="pubmed", title="NR4A2 drives Treg stability",
                 abstract="TSDR demethylation was measured.", authors=[], date="", url="")
    assert f.apply(nurr) and nurr.matched_compound == ["nr4a"]
    assert "stability" in nurr.matched_topics


def test_preprint_keeps_latest_version(monkeypatch):
    src = PreprintSource("biorxiv", {})
    v1 = dict(BIORXIV_ITEM, version="1")
    monkeypatch.setattr(src, "fetch_raw", lambda s, e: [v1, BIORXIV_ITEM])
    out = src.collect(date(2026, 10, 14), date(2026, 10, 15))
    assert len(out) == 1 and out[0].version == "2"


def test_storage_dedup_and_classification(tmp_path):
    st = LocalJSONStorage(tmp_path)
    p = to_paper(BIORXIV_ITEM, "biorxiv")
    assert st.save_papers([p], "2026-10-15") == 1
    assert st.save_papers([p], "2026-10-16") == 0          # 다음 날 다시 걸려도 중복 저장 안 함
    assert [x.id for x in st.iter_papers(only_unclassified=True)] == [p.id]
    st.set_classification(p.id, {"by": "agent", "labels": ["CAF"]})
    assert list(LocalJSONStorage(tmp_path).iter_papers(only_unclassified=True)) == []
    line = (tmp_path / "papers/2026-10-15.jsonl").read_text().strip()
    assert json.loads(line)["classification"]["labels"] == ["CAF"]


def test_run_end_to_end_with_fake_sources(tmp_path, monkeypatch):
    class Fake:
        def __init__(self, name, papers):
            self.name, self.papers = name, papers

        def collect(self, *a):
            return self.papers

    pm = parse_article(ET.fromstring(PUBMED_XML).find("PubmedArticle"))
    bx = to_paper(BIORXIV_ITEM, "biorxiv")
    noise = Paper(id="doi:n", source="biorxiv", title="Sleep and CSF flow", abstract="", authors=[], date="", url="")
    failing = Fake("medrxiv", None)
    failing.collect = lambda *a: (_ for _ in ()).throw(RuntimeError("down"))
    monkeypatch.setattr("collector.main.build_sources",
                        lambda cfg, s: [Fake("pubmed", [pm]), Fake("biorxiv", [bx, noise]), failing])
    st = LocalJSONStorage(tmp_path)
    rep = run(CFG, st, date(2026, 10, 14), date(2026, 10, 15))
    assert rep["saved"] == 2
    assert rep["sources"]["biorxiv"] == {"fetched": 2, "matched": 1, "new": 1}
    assert rep["errors"] and "medrxiv" in rep["errors"][0]
    assert list((tmp_path / "runs").glob("*.json"))
    md = next((tmp_path / "reports").glob("*.md")).read_text()
    assert "총 2편" in md and "Chloroquine modulates" in md and "Sleep and CSF" not in md
    # 같은 날 다시 실행해도 보고서에는 그날 전체 논문이 유지됨
    run(CFG, st, date(2026, 10, 14), date(2026, 10, 15))
    assert "총 2편" in next((tmp_path / "reports").glob("*.md")).read_text()


def test_report_escapes_and_empty():
    from collector.report import build_daily_report
    p = to_paper(dict(BIORXIV_ITEM, title="A | B"), "biorxiv")
    kf().apply(p)
    md = build_daily_report([p], "2026-10-17")
    assert "A \\| B" in md and "<details>" in md
    assert "새 논문이 없습니다" in build_daily_report([], "2026-10-17")


def test_clean_abstract_strips_copyright():
    from collector.models import clean_abstract
    assert clean_abstract("RESULTS: ok.\nCONCLUSION: fine. © 2026 Elsevier Inc. All rights reserved.") == \
        "RESULTS: ok.\nCONCLUSION: fine."
    assert clean_abstract("No notice here.") == "No notice here."


def test_classify_batch_apply_and_guards(tmp_path):
    from collector.classify import apply_results, next_batch, parse_results, skip
    store = LocalJSONStorage(tmp_path)
    abstract = ("We treated naive CD4 T cells with chloroquine during induced regulatory "
                "T cell differentiation and measured Foxp3 expression by flow cytometry.")
    papers = [Paper(id=f"pmid:{i}", source="pubmed", title=f"T{i}", abstract=abstract, authors=[],
                    date="2026-10-19", url="u", matched_topics=["treg"]) for i in range(7)]
    store.save_papers(papers, "2026-10-19")

    b = next_batch(store, size=5)
    assert len(b["papers"]) == 5 and b["remaining_after_this"] == 2

    llm_out = "결과입니다\n```json\n" + json.dumps([
        {"id": "pmid:0", "relevance": "8", "labels": "treg", "summary": "CQ 처리 후 iTreg 분화율 변화 분석"},
        {"id": "pmid:1", "relevance": 99, "summary": abstract},        # 원문 복사 → summary 비움
        {"id": "pmid:2", "summary": "가" * 500},                       # 너무 김 → 자름
        {"id": "pmid:x"},                                              # 모르는 id
    ], ensure_ascii=False) + "\n```"
    res = apply_results(store, parse_results(llm_out))
    assert res["saved"] == 3 and res["remaining"] == 4 and res["errors"]
    got = {p.id: p.classification for p in store.iter_papers() if p.classification}
    assert got["pmid:0"]["relevance"] == 8 and got["pmid:0"]["labels"] == ["treg"]
    assert got["pmid:1"]["summary"] == "" and got["pmid:1"]["relevance"] == 10
    assert len(got["pmid:2"]["summary"]) <= 301

    # 이미 분류된 것은 덮어쓰지 않음
    assert apply_results(store, [{"id": "pmid:0", "summary": "x"}])["saved"] == 0
    skip(store, "pmid:3", "응답 중단")
    assert [p["id"] for p in next_batch(store, size=5)["papers"]] == ["pmid:4", "pmid:5", "pmid:6"]

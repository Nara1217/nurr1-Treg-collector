# Nurr1 리간드 × Treg 분화 논문 수집기 (paper_collector)

PubMed와 bioRxiv·medRxiv에서 **CQ·AQ·PGA1·PGE1 등 Nurr1(NR4A2) 리간드가 Treg 분화에 미치는 영향**을 다룬 새 논문을 매일 모아, 정해진 JSON 형식으로 쌓아 두는 수집 단계입니다.

- 물질군: 퀴놀린계(chloroquine, amodiaquine, HCQ 등), 프로스타글란딘(PGA1, PGE1, 15d-PGJ2 등), NR4A/Nurr1 계열
- 주제 태그: Treg, T세포 분화, 안정성(TSDR·CNS2), 자가면역 모델, T세포 신호

다른 AI 에이전트는 쌓인 데이터를 읽어 다시 분류하고, 그 결과를 같은 레코드의 `classification` 칸에 기록합니다.

```
[PubMed]  ─┐
[bioRxiv] ─┼─► 물질 AND 주제 필터 ─► 중복 제거 ─► data/papers/YYYY-MM-DD.jsonl ─► 분류 에이전트
[medRxiv] ─┘                         (DOI 기준)    data/index.json                 (classification 채움)
```

## 설치와 실행

Python 3.9 이상이 필요합니다.

```bash
pip install -r requirements.txt
python -m collector --dry-run        # 저장 없이 건수만 확인
python -m collector                  # 최근 2일치 수집 → data/ 에 저장
python -m collector --days 30        # 처음 한 번은 지난 30일치를 채워 두면 좋습니다
python -m collector --start 2026-09-01 --end 2026-09-30
```

- 매일 실행은 `.github/workflows/collect.yml`이 한국시간 06:40에 돌립니다. cron이나 작업 스케줄러로 돌려도 됩니다.
- 기간이 겹쳐도 같은 논문은 다시 저장되지 않습니다. 그래서 기본값을 2일로 넉넉하게 잡았습니다.
- NCBI API 키를 환경변수 `NCBI_API_KEY`로 넣으면 PubMed 요청이 빨라집니다. 키가 없어도 동작합니다.

## 관심 범위 바꾸기

`config.yaml`의 `compounds`와 `topics` 목록만 고치면 됩니다. 코드는 건드릴 필요가 없습니다.

- **수집 조건:** 제목이나 초록에 **물질 키워드 1개 이상 AND 주제 키워드 1개 이상**이 있어야 수집됩니다(`require_topics: true`).
- **왜 AND인가:** CQ·AQ·PGE1은 말라리아, 오토파지, COVID-19, 혈관질환 쪽 논문이 압도적으로 많습니다. 면역·T세포 맥락을 같이 요구해야 쓸 만한 목록이 나옵니다. `require_topics: false`로 바꾸면 물질만으로도 수집되지만 양이 크게 늘어납니다.
- **`topics`에 일반 용어를 넣지 마세요.** autophagy, lysosome, NF-kB, methylation 같은 단어를 주제에 넣으면 비면역 논문이 대량으로 통과합니다. T세포·Treg 맥락에서만 쓰이는 용어로 유지하세요.
- **소문자 키워드:** 대소문자를 무시하고, 뒤에 글자가 붙어도 매칭합니다. 예: `autoimmun` → autoimmunity
- **약어:** 띄어쓰기 없는 대문자 약어는 대소문자를 구분합니다. 예: `CQ`·`AQ`는 acquired, acquisition 같은 단어에 걸리지 않습니다.
- **공백과 하이픈:** 같은 것으로 봅니다. 예: Th 17 = Th-17
- **PubMed 검색 방식:** 서버에는 물질 키워드로만 넓게 검색하고, 주제 필터는 로컬에서 적용합니다. 그래서 주제 키워드를 바꾼 뒤 다시 실행하면 바로 반영됩니다.

## 저장 형식 (`data/`)

| 경로 | 내용 |
|---|---|
| `papers/YYYY-MM-DD.jsonl` | 그날 수집한 논문. 한 줄이 한 편이고, 형식은 `schema/paper.schema.json`을 따릅니다. |
| `reports/YYYY-MM-DD.md` | 사람이 훑어보기 위한 일일 보고서입니다. 수집 건수, 논문 목록 표, 접어 둔 초록 미리보기가 들어 있고 AI 요약은 없습니다. |
| `index.json` | 논문 id → 파일 경로. 중복을 막고 빠르게 찾는 데 씁니다. |
| `runs/<시각>.json` | 실행 기록: 기간, 소스별로 가져온 수·키워드 일치 수·신규 수, 오류 |

레코드 예시는 아래와 같습니다. 핵심 칸만 보여줍니다.

```json
{"id": "pmid:31664129", "source": "pubmed", "is_preprint": false,
 "title": "...", "abstract": "...", "date": "2019-10-29", "url": "...",
 "matched_compound": ["quinoline", "nr4a"], "matched_topics": ["treg", "t_helper", "autoimmune_model"],
 "matched_keywords": ["chloroquine", "CQ", "Nurr1", "Foxp3", ...], "classification": null}
```

- `id`는 DOI를 우선으로 씁니다. 그래서 프리프린트와 PubMed에 같은 DOI로 올라온 논문은 한 번만 저장됩니다.
- 한 소스가 실패해도 나머지 소스는 계속 수집합니다. 실패 내용은 실행 기록의 `errors`에 남습니다.

## 분류 에이전트 연동

에이전트는 두 가지 방법 중 하나로 데이터를 다룹니다.

1. **파일을 직접 다루기:** `data/papers/*.jsonl`에서 `classification`이 `null`인 줄을 찾아 채웁니다.
2. **Python API 쓰기:**

```python
from collector import LocalJSONStorage
store = LocalJSONStorage("data")
for p in store.iter_papers(only_unclassified=True):
    store.set_classification(p.id, {"relevance": 8, "labels": [...], "model_systems": [...], "validation": [...]})
```

깊이 있는 분류(적합도 판정, 분화 방향·기전·실험 조건·기능 4축, Nurr1 연관 근거 등급)는 `nurr1-treg-paper-classifier` 스킬에 정리돼 있습니다.

### LLM 에이전트로 분류할 때 (응답 중단 방지)

LLM이 분류 결과를 쓰다가 응답이 안전 필터에 걸려 끊길 수 있습니다. 주로 초록 원문을 응답에 길게 옮겨 적거나(저작권 필터), 한 번에 너무 많은 논문을 처리할 때 생깁니다. 그래서 `collector.classify` 도구로 작은 묶음씩 처리합니다. 에이전트용 규칙은 `CLAUDE.md`(= `AGENTS.md`)에 있습니다.

```bash
python -m collector.classify status               # 전체/대기/완료/건너뜀 수
python -m collector.classify next --size 5        # 다음 5편 (JSON)
python -m collector.classify apply results.json   # 결과 JSON 저장 (- 를 주면 표준입력)
python -m collector.classify skip <id> --reason "응답 중단 반복"
```

- `apply`는 결과를 검사합니다. `summary`가 초록과 연속 8단어 이상 같으면 비우고, 300자를 넘으면 자릅니다. 고친 내용은 `classification.warnings`에 남습니다.
- 묶음마다 바로 저장하므로 중간에 끊겨도 그 묶음만 다시 하면 됩니다.
- 수집 단계에서 초록 끝의 저작권·라이선스 문구(© …, All rights reserved 등)를 떼어 냅니다.

## 저장 위치 바꾸기

수집기와 에이전트는 `collector/storage.py`의 `Storage` 인터페이스만 사용합니다. GitHub, Google Drive, DB 등으로 옮길 때는 다음 메서드를 구현한 클래스를 하나 추가하고, `main.py`에서 그 클래스를 쓰도록 바꾸면 됩니다.

- `seen_ids`
- `save_papers`
- `save_run_log`
- `save_report`
- `papers_for_batch`
- `iter_papers`
- `set_classification`

## 테스트

```bash
pip install pytest && python -m pytest -q
```

테스트는 네트워크 없이 가짜 데이터로 돌아갑니다. 실제 API 응답 형식을 본떠 만든 데이터입니다.

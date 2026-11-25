import re
from collections import defaultdict

from rank_bm25 import BM25Plus

from .catalog import searchable_text


def tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).casefold()
    parts = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text)
    result = []
    for part in parts:
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            result.extend([part] + [part[i:i + 2] for i in range(len(part) - 1)])
        else:
            result.extend([part] + part.split("_"))
    return result


def rank(question: str, documents: list[dict], vector_ids: list[str], limit: int, domains: list[str], *, lexical_enabled: bool = True) -> tuple[list[str], dict[str, list[str]]]:
    if not documents:
        return [], {}
    lexical = []
    if lexical_enabled:
        corpus = [tokens(searchable_text(d)) for d in documents]
        query_tokens = tokens(question)
        scores = BM25Plus(corpus).get_scores(query_tokens)
        lexical = sorted([i for i, doc in enumerate(corpus) if set(doc).intersection(query_tokens)], key=lambda i: (-scores[i], documents[i]["id"]))[:limit]
    normalized = question.casefold()
    exact = [d["id"] for d in documents if any(term.casefold() in normalized for term in
             [d["id"], d["label"], *d.get("aliases", []), d.get("execution", {}).get("path", ""),
              *[f["name"] for f in d.get("fields", [])]] if len(term) >= 2)]
    fused = defaultdict(float)
    matched = defaultdict(list)
    for source, ids in [("exact", exact), ("keyword", [documents[i]["id"] for i in lexical]), ("vector", vector_ids)]:
        for position, id_ in enumerate(ids):
            fused[id_] += (2 if source == "exact" else 1) / (60 + position + 1)
            matched[id_].append(source)
    for d in documents:
        if d["id"] in fused and d["domain"] in domains:
            fused[d["id"]] += 0.003
    return sorted(fused, key=lambda id_: (-fused[id_], id_))[:limit], dict(matched)

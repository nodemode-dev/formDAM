import html
import json
import re
from functools import lru_cache
from typing import Dict, List, Tuple

CONTEXT = 77
_PAT = re.compile(r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|(?:[^\s\w]|_)+", re.IGNORECASE)


@lru_cache(maxsize=1)
def _byte_map() -> Dict[int, str]:
    keep = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    chars = keep[:]
    extra = 0
    for b in range(256):
        if b not in keep:
            keep.append(b)
            chars.append(256 + extra)
            extra += 1
    return dict(zip(keep, (chr(c) for c in chars)))


def _pairs(word: Tuple[str, ...]) -> set:
    return {(word[i], word[i + 1]) for i in range(len(word) - 1)}


class Tokenizer:
    def __init__(self, vocab_path: str, merges_path: str) -> None:
        with open(vocab_path, encoding="utf-8") as fh:
            self.encoder: Dict[str, int] = json.load(fh)
        with open(merges_path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        merges = [tuple(line.split()) for line in lines[1:] if line and not line.startswith("#")]
        self.ranks = {pair: i for i, pair in enumerate(merges)}
        self.sot = self.encoder["<|startoftext|>"]
        self.eot = self.encoder["<|endoftext|>"]
        self.cache: Dict[str, str] = {}

    def _bpe(self, token: str) -> str:
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        pairs = _pairs(word)
        if not pairs:
            return token + "</w>"
        while True:
            best = min(pairs, key=lambda p: self.ranks.get(p, float("inf")))
            if best not in self.ranks:
                break
            first, second = best
            merged: List[str] = []
            i = 0
            while i < len(word):
                try:
                    j = word.index(first, i)
                except ValueError:
                    merged.extend(word[i:])
                    break
                merged.extend(word[i:j])
                i = j
                if word[i] == first and i < len(word) - 1 and word[i + 1] == second:
                    merged.append(first + second)
                    i += 2
                else:
                    merged.append(word[i])
                    i += 1
            word = tuple(merged)
            if len(word) == 1:
                break
            pairs = _pairs(word)
        out = " ".join(word)
        self.cache[token] = out
        return out

    def encode(self, text: str) -> List[int]:
        clean = re.sub(r"\s+", " ", html.unescape(html.unescape(text))).strip().lower()
        bmap = _byte_map()
        ids: List[int] = [self.sot]
        for token in _PAT.findall(clean):
            mapped = "".join(bmap[b] for b in token.encode("utf-8"))
            ids.extend(self.encoder[piece] for piece in self._bpe(mapped).split(" ") if piece in self.encoder)
        ids = ids[: CONTEXT - 1]
        ids.append(self.eot)
        return ids

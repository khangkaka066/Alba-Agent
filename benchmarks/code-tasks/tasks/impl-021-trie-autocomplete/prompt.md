The search box needs prefix autocomplete over a vocabulary where each word has a popularity weight. Implement the `Autocomplete` class in `autocomplete.py`.

- `add(word, weight=1)`: registers `word`. If the word is already present, `weight` is **added** to its existing weight. `word` must be a non-empty string and `weight` an int >= 1, otherwise `ValueError` is raised (and nothing changes). Matching is case-sensitive.
- `remove(word) -> bool`: removes the word; returns `True` if it was present, `False` otherwise. Removing a word never affects other words that share a prefix with it (e.g. removing `"car"` keeps `"card"`), and a later `add` of the same word starts again from the given weight.
- `word in ac` tells whether the exact word is present; `len(ac)` is the number of distinct words.
- `weight_of(word) -> int`: the current weight; raises `KeyError` if the word is not present.
- `suggest(prefix, limit=5) -> list[str]`: up to `limit` words that start with `prefix` (a word counts as starting with itself), ordered by weight descending, ties broken alphabetically (ascending, plain string comparison). An empty prefix matches every word. `limit` must be an int >= 0, otherwise `ValueError`; `limit == 0` gives `[]`. A prefix nothing matches gives `[]`.
- `count_prefix(prefix) -> int`: the number of distinct words that start with `prefix` (all words for the empty prefix).

Implement it with a trie (or an equivalent prefix structure); vocabularies of tens of thousands of words are expected, so `suggest` must not scan every word for a non-empty prefix that matches few words.

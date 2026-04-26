# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

**Resonance Selector 2.0** *(extends Resonance Selector 1.0 with a reliability harness, evaluation script, and RAG-enriched explanations)*

---

## 2. Intended Use  

Resonance Selector is designed for casual music fans who want to discover new songs that match their current taste. You give it a genre, a mood, and a general energy level, and it returns a ranked list of tracks from the catalog that fit your vibe.

The system assumes you have a rough sense of what you like — your favorite genre, whether you want something calm or intense, and whether acoustic sound appeals to you. It does not require deep music knowledge, but it does ask you to express preferences as simple values rather than in free-form language.

**This system is not intended for:** professional music curation, real-world streaming platforms, large catalogs, or any context that requires legal compliance or fairness guarantees. It is a simplified simulation meant for personal exploration.  

---

## 3. How the Model Works  

Every song in the catalog has two kinds of information: labels and numbers. The labels are the genre (like "pop" or "lofi") and the mood (like "happy" or "intense"). The numbers describe how the song actually sounds — how much energy it has, how fast the tempo is, how emotionally positive it feels, how acoustic it sounds, and how danceable it is. All of these numbers fall on a scale from 0.0 to 1.0.

When you set up a profile, you tell the system your favorite genre, your preferred mood, and your target energy level.

The system then goes through every song in the catalog and asks two questions for each one: does the label match, and how close are the numbers?

If the song's genre matches your preference, it gets a fixed bonus of 2.5 points. A mood match adds another 1.5 points. A matching detailed mood tag (e.g., "euphoric," "nostalgic," "aggressive") adds 1.0 points, and a matching language style (e.g., "english" vs. "instrumental") adds 0.75 points. These four categorical checks are the discrete, label-based half of the scoring.

For the numerical features, the system measures the gap between the song's value and your target. A song with an energy of 0.80 scores higher for a user who wants 0.85 energy than for one who wants 0.20. Each feature has its own multiplier. In the default **balanced** mode: energy matters most (×2.0), followed by emotional positivity or valence (×1.5), acousticness (×1.0), and instrumentalness — the vocal-to-instrumental ratio — (×1.0). Tempo, popularity proximity, and era alignment (release decade) each contribute at ×0.75, and danceability at ×0.5.

The system also supports three alternative **scoring modes** selectable via a `--mode` CLI flag. Each mode boosts one dimension's weights while suppressing the others, creating real trade-offs rather than just adding points on top:

- **genre-first** — doubles the genre bonus to 5.0 pts, halves energy and mood weights. Use when genre identity is the primary driver.
- **mood-first** — doubles mood and detailed mood tag weights, suppresses genre. Use when emotional feel matters more than category.
- **energy-focused** — doubles the energy multiplier and also boosts tempo and danceability, suppresses genre and mood. Use when intensity and vibe override everything else.

Once every song has a total score, the list is sorted from highest to lowest. The top results are the recommendation.

**Optional: Diversity Penalty (`--diversity`)**

By default the sorted list is sliced directly, which can produce results dominated by one artist or genre. Enabling `--diversity` replaces the slice with a greedy selection loop: the system builds the top-5 list one pick at a time, applying a soft penalty to any candidate whose artist or genre is already in the selected set (−2.0 pts for a duplicate artist, −1.5 pts for a duplicate genre). The penalty is shown in each song's explanation so the trade-off is transparent. Songs are discouraged from repeating but never outright blocked — a strong enough song from a repeated genre can still appear.

---

## 3a. Reliability Mechanisms (added in v2.0)

Version 2.0 wraps the deterministic core in a reliability harness that catches bad inputs, scores how confident the system is in each result, and *automatically tries alternative strategies* when confidence is low. The mechanism is integrated into the main call path: `recommend_with_harness()` is the entry point used by `main.py`, not a separate post-hoc analyzer.

**Input guardrails** (`src/harness/validators.py`):
- Required user-profile keys (`genre`, `mood`, `energy`) must be present or the call fails fast with `HarnessError`.
- Out-of-range numerics (e.g. `energy = 1.5`) are clamped to valid ranges with a warning recorded on the run report.
- The catalog itself is validated on every call: duplicate song ids fail fast; rows with NaN/Inf in unit-interval features are dropped with a warning; an empty catalog raises.

**Confidence score** (`src/harness/confidence.py`) combines three signals into one [0, 1] number:
- `gap_score` — how far the top result is above the rest of the top-5 (normalized against ~14-pt max).
- `categorical_match_pct` — fraction of the top-5 whose genre or mood matches the user's preference.
- `diversity_score` — penalizes top-5 sets dominated by one artist or genre.
- `overall = 0.5*gap + 0.3*categorical + 0.2*diversity`. The default fallback threshold is 0.4.

**Self-critique fallback ladder** (`src/harness/critique.py`) — when initial confidence falls below the threshold, the harness climbs three rungs in order, retaining the best result of all attempts:
1. Switch scoring mode (`balanced↔mood-first`, `genre-first→mood-first`, `energy-focused→balanced`).
2. Enable the diversity penalty (if it was off).
3. Drop the categorical preference (`genre` or `mood`) with the fewest catalog matches — the user's "weakest" anchor.

Every rung's confidence is recorded on the `HarnessReport` returned alongside the recommendations, so the user (and the run log) can see exactly how the system's strategy evolved. When a fallback fires, the CLI prints a yellow notice above the table summarizing the change.

**Output guardrails** — before the table is shown, results are deduped by song id, NaN-scored rows are dropped, the list is sorted descending with deterministic id-ascending tiebreak, and length is enforced to `min(k, catalog_size)`.

**Run logging** (`src/harness/logging_utils.py`) — every call writes a JSON file to `/logs/` capturing the report, the result list, and a timestamp. This creates an audit trail without ever touching the deterministic scoring code.

**Evaluation harness** (`scripts/evaluate.py`) — runs the full 5-profile × 4-mode × 2-diversity matrix (40 configurations) plus 12 edge cases against a golden baseline (`tests/golden/expected_outputs.json`). The baseline records the catalog hash, weights hash, and per-config top-5 song ids and rounded scores. Drift handling is layered: if the catalog or weights hash changes, the script reports `BASELINE STALE` (no false-positive failures); if scores drift but the ranking is stable, a soft warning fires; only a changed top-5 id list triggers a hard fail with a diff. At v2.0 release, **40/40 matrix runs and 12/12 edge cases pass**, with fallback triggering on 30% of matrix runs (entirely on the adversarial `conflicting_moods` profile and the small-catalog `focused_jazz` profile).

**RAG enrichment layer** (`src/rag/`, optional `--rag` flag) — for each recommendation, a TF-IDF-backed retriever pulls 1–3 markdown documents from `/docs/genres/`, `/docs/moods/`, and `/docs/detailed_moods/` matching the song's labels. The retrieved documents plus the user's preferences and the deterministic scoring reasons are batched into a single Google Gemini API call (`gemini-2.5-flash`) that returns one short grounded paragraph per song. The deterministic explanation is preserved; the RAG note is appended below it. When `GEMINI_API_KEY` is missing or the API call fails, the system warns and returns unenriched results — the deterministic core never depends on the LLM being available.

---

## 4. Data  

The catalog contains 20 songs — the original 10 from the starter dataset and 10 more added to increase diversity.

**Genres represented (16 total):** pop, lofi, rock, ambient, jazz, synthwave, indie pop, punk, hip-hop, folk, classical, r&b, edm, blues, metal, soul

**Moods represented:** happy, chill, intense, relaxed, focused, moody, confident, nostalgic, melancholic, euphoric, angry, uplifting, aggressive

Energy values range from 0.21 (very calm) to 0.97 (near maximum intensity), which gives the system a meaningful spread to work with.

**What is missing:** Jazz, blues, classical, and metal each appear only once in the catalog. Non-Western genres and styles — bossa nova, afrobeats, K-pop, reggaeton — are entirely absent. The dataset skews toward pop and lofi, which means those genres get better recommendations while niche listeners run out of real matches after the first or second result.  

---

## 5. Strengths  

The system works best for listeners whose taste aligns with a well-represented genre and a clear energy level. The Chill Lofi and Deep Intense Rock profiles produced the most reliable results: both genres have multiple songs in the catalog, and the energy spread in those groups is distinct enough that the proximity scoring can separate close matches from weak ones. For the lofi listener, "Library Rain" and "Midnight Coding" ranked at the top — both feel genuinely appropriate. For the rock listener, "Storm Runner" was the clear winner.

The scoring logic also captures mood-energy coherence well when the genre label is a good fit. When a user's genre preference matches the catalog's strongest group, the numerical features (energy, valence, acousticness) do useful work to rank songs within that group by feel, not just by category. In those cases, the system's output matches the kind of intuition a person would have when flipping through a playlist.  

---

## 6. Limitations and Bias

**The genre label acts like a VIP pass — and that's a problem.**

The biggest weakness is how much weight the system gives to matching the genre label. A genre match awards 2.5 points upfront, which is more than the maximum energy score a song can earn. This means a song can show up in your top results simply because it shares a label with your preferred genre, even if everything else about it feels wrong. A real example from testing: "Gym Hero" by Max Pulse kept appearing in the top results for a user who wanted happy, upbeat pop music. The reason? Gym Hero is tagged as pop — so it got 2.5 free points before anything else was measured. But Gym Hero's mood is "intense," not "happy." If you just wanted something fun and cheerful, Gym Hero would feel out of place. The system doesn't know the difference; it just sees the matching genre tag and rewards it.

**Artist and genre repetition creates filter bubbles — partially mitigated by `--diversity`.**

Without any diversity logic, the top-5 list often contains two or three songs from the same genre (or the same artist in a genre-heavy dataset). For the High-Energy Pop profile, both of the catalog's pop songs appear in the top two slots because the genre bonus dominates everything else. The `--diversity` flag applies a greedy penalty to address this: after each pick, the next candidate from the same artist pays −2.0 pts and the next candidate from the same genre pays −1.5 pts. This is a soft nudge, not a hard cap — a strong enough duplicate can still appear. The penalty amounts were set to match the corresponding match bonuses in balanced mode (genre match = +2.5, mood match = +1.5), so a repeat costs roughly as much as one matching label is worth.

**Small catalog, big blind spots.**

With only 20 songs, some genres appear just once or twice. If you prefer jazz, there is literally one jazz song in the entire catalog — Coffee Shop Stories. After that, the system has no choice but to recommend lofi and ambient tracks that happen to have similar energy levels. That is not jazz; it just happens to feel calm. In a real platform with millions of songs, this dilutes naturally. Here it creates a filter bubble for anyone who falls outside the three or four most represented genres. The diversity penalty reduces within-genre repetition but cannot fix a genre that only has one song.

**The system cannot learn or adapt.**

Every recommendation is made from a frozen snapshot of your preferences. There is no way to say "I liked that one" or "skip this artist." In Spotify or TikTok, every play, skip, and replay updates the model. Here, the profile stays static — so if your taste shifts or the first set of results misses the mark, the system has no way to correct itself.

**The system assumes you know yourself in numbers.**

To get accurate results, you need to supply a precise energy value like 0.80 or a tempo target of 120 BPM. Real listeners do not think that way. Most people describe their taste in words — "something to work out to" or "background music for studying" — not fractions. This means the profile setup itself introduces error before any recommendation is made.

**The reliability harness can mask catalog gaps rather than expose them (added in v2.0).**

The fallback ladder is good at producing a result that *clears the confidence threshold*, but "cleared the threshold" is not the same as "matched what the user wanted." For the `focused_jazz` profile under `mood-first` mode, the harness falls back to `balanced` and confidence improves from 0.36 to 0.42 — but the underlying problem (only one jazz song in the catalog) is unchanged. The system has effectively learned to route around its own limitations without acknowledging them. The `--explain-harness` flag and the `/logs/` JSON output make these adjustments visible, but a user who only sees the final table will not know that the recommendation was built on a relaxed profile rather than the one they entered. This is a real cost of any self-correcting system: it can hide failure modes behind plausible output.

**The RAG enrichment can sound more confident than the underlying data justifies (added in v2.0).**

When `--rag` is enabled, Gemini generates polished natural-language paragraphs grounded in the retrieved markdown documents. Those documents describe each genre or mood in general terms, but they are not specific to the songs in the catalog. So the enriched explanation can confidently describe a song using language the document supplied, even when that language only loosely fits the actual track. The deterministic explanation remains visible alongside the RAG paragraph as a corrective, but a casual reader may anchor on the prose rather than the math.

---

## 7. Evaluation

**Profiles tested.**

Five user profiles were run against all 20 songs to observe how the scoring logic handled different types of listeners:

- **High-Energy Pop** — someone who wants upbeat, danceable pop music (the original default profile)
- **Chill Lofi** — someone who wants quiet, acoustic background music for studying or relaxing
- **Deep Intense Rock** — someone who wants loud, fast, aggressive music
- **Focused Jazz** — someone who wants calm, mid-energy jazz for concentration
- **Conflicting Moods (edge case)** — an adversarial profile designed to confuse the system: high energy (0.90) paired with a sad mood and an ambient genre preference — things that do not naturally go together

**What the results revealed.**

The Chill Lofi and Deep Intense Rock profiles worked best. Both had enough matching songs in the catalog that the top results felt genuinely appropriate — Library Rain and Midnight Coding for the lofi listener, Storm Runner for the rock listener. These profiles benefited from a good genre-energy alignment in the dataset.

The High-Energy Pop results were mostly reasonable, but Gym Hero kept appearing at rank 2 despite being tagged as "intense" rather than "happy." For someone who genuinely just wants cheerful, upbeat music, Gym Hero would feel like a mismatch. The genre label was doing all the heavy lifting.

The Focused Jazz profile exposed the small-catalog problem directly. There is only one jazz song, so after that, the system defaulted to lofi songs with similar energy and acousticness levels. The recommendations were not wrong exactly, but they were not jazz.

The Conflicting Moods profile was the most revealing. The ambient genre tag earned Spacewalk Thoughts — a very low-energy ambient track — the top spot, even though the user profile was asking for high energy (0.90). The genre match alone was enough to override the massive energy mismatch. This is a clear case where the system's bias becomes a real problem.

**The weight shift experiment — now a built-in mode.**

One experiment was run: the energy weight was doubled (from 2.0 to 4.0) and the genre weight was halved (from 2.5 to 1.25). The goal was to see if making the system more sensitive to how a song "feels" rather than what label it carries would produce better results.

For the Conflicting Moods profile, the change was clearly an improvement — Spacewalk Thoughts fell out of the top 5 and high-energy songs correctly took its place. For the Focused Jazz profile, the change backfired: the one actual jazz song dropped to rank 2, replaced by a lofi track that just happened to have a closer energy score. For all other profiles, rankings shifted by one position at most and both versions felt equally reasonable.

The experiment confirmed that the best weight balance depends on the use case. Genre labels matter more when users strongly identify with a genre. Energy matters more when users care about vibe over category.

This insight directly motivated the scoring modes feature. The experimental weight configuration is now available as `--mode energy-focused`, and two additional presets (`genre-first` and `mood-first`) cover the opposite ends of the spectrum. Users can now reproduce the experiment — or any variation of it — at runtime without touching the code.

---

## 8. Future Work  

**Larger and more diverse dataset.** The most immediate limitation is the 20-song catalog. Expanding to hundreds of songs — with meaningful representation for jazz, blues, classical, folk, and non-Western styles — would make the system useful for a much wider range of listeners. Right now the system cannot tell the difference between "no songs match your taste" and "your genre just isn't in the catalog."

**User-configurable weights** *(implemented).* The weight-shift experiment showed that the best balance depends on the listener. The system now supports four scoring modes — `balanced`, `genre-first`, `mood-first`, and `energy-focused` — selectable via the `--mode` CLI flag. A natural next step would be fully custom weight values (e.g., `--weight-genre 3.5`) rather than only named presets, giving users fine-grained control without requiring code changes.

**Diversity penalty** *(implemented).* The `--diversity` flag applies a greedy soft penalty (−2.0 for a duplicate artist, −1.5 for a duplicate genre) to prevent the top-5 from being dominated by one artist or genre. A tunable penalty strength (e.g., `--diversity-strength 3.0`) and a configurable per-artist/per-genre cap (e.g., "allow at most 2 songs per genre before penalising") would give more precise control over the variety-vs-relevance trade-off.

---

## 9. Personal Reflection  

**What are the limitations or biases in your system?**

The system has structural biases (in the scoring math) and dataset biases (in the catalog). The biggest structural bias is **genre dominance**: the +2.5 genre bonus exceeds the maximum any continuous feature can contribute, so a song with the right *label* can outrank one whose energy, valence, and mood are all closer fits — *Gym Hero* (tagged pop, but actually intense in mood) keeps winning recommendations for users asking for upbeat happy pop. The dataset bias is sharper: with only 20 songs, several genres have a single representative, and the catalog reflects my own listening history. The optional LLM features (`--rag`, `--agent`) inherit Gemini's training-data biases on top, particularly for the `historian` persona's genre-lineage framing. A deeper categorization lives in [model_card.md](model_card.md).

**Could your AI be misused, and how would you prevent that?**

Honestly, this build's misuse surface is narrow — it is a 20-song classroom system, not a deployed product. The risk worth flagging is the **architecture pattern**: a curated RAG knowledge base + persona-styled commentary + a numeric confidence score is benign feature-by-feature, but together can launder editorial decisions into output that *looks* objective. A label could write favorable docs to bias the LLM, the persona system can be repurposed as soft promotion, and a bare confidence number reads as authoritative even when the underlying score gap is narrow. Mitigations already in this build: every LLM feature is opt-in (`--rag`, `--agent`), the deterministic core is the reproducible default, fallbacks fire visibly with a yellow notice, `--explain-harness` exposes the full repair trace, and every harness call writes a JSON log to `/logs/`. At scale I would add citations for retrieved RAG sources, vetted-only personas, and surfacing confidence alongside its threshold rather than as a bare percentage.

**What surprised you while testing your AI's reliability?**

This can be broken down into two parts, the creation of the project's components and the integrated AI components in used by the actual program. Overall both were very reliable, so I suppose the biggest surprise was the lack of major changes that were required. Claude's plan mode created detailed outlines for what I could expect from the model, and the subsequently generated code had few errors. The same can be said about the less capable, but still effective, Gemini Flash which is what I used for the RAG and agent planning components. Another pleasant surprise was the relative speed of both models for their respective use cases.

My one unpleasant surprise was an error I got through Claude "API Error: 400 due to tool use concurrency issues." I tried to research the cause, but there were too many different cases where it occured. Luckily, starting a new chat resolved the issue for me and allowed me to proceed. Anectdotally, I suspect it has something to do with the context window getting full having an impact on the model's ability to select/use tools.

**Describe your collaboration with AI during this project. Identify one instance where the AI gave a helpful suggestion and one instance where its suggestion was flawed or incorrect.**

I used a combination of Claude Sonnet/Opus and Gemini Pro/Flash. The Claude models were used for planning, code generation, Gemini Pro was used for analysis/critique, and Gemini Flash is used by the final program for the RAG/RAG personas and the planning agent. 

There was one scenario where one AI gave a flawed or incorrect answer, which was correctly challenged by another AI. Claude Opus generated usable code pretty much right away, but I used Gemini Pro as a kind of code review. Usually I agreed with Gemini's feedback, and would then return that back to Claude for refinement. One recommended change caused some pushback from Claude Opus, namely to change the core of the program's core deterministic decision making to one that was entirely AI based. I ended up deferring to Claude here as the suggested change would have fundamentally undone much of the work that the entire project was built on. 
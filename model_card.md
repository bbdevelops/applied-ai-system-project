# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

**Resonance Selector 1.0**  

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

The biggest thing I learned from this project is how much a small dataset limits what a recommender can actually do. I knew the catalog was small, but I did not fully appreciate what that meant until I ran the Focused Jazz profile and got lofi songs back. There is only one jazz track in the whole catalog. After that, the system has nothing to work with — it just finds the nearest thing it has, which is not the same as what the user actually wants. That gap between "no match found" and "wrong match returned" is invisible unless you test it.

AI tools were genuinely useful during the build, but in a specific way: they handled the repetitive structural work — the CSV loading, the function scaffolding, the output formatting — which freed up my attention for the parts that actually mattered, like verifying that the scoring math produced sensible results. Every time the AI generated a scoring function or a weighting rule, I had to check it against my own logic. That verification step was where most of the real learning happened.

What surprised me most was how much a few simple weighted comparisons can feel like a real recommendation. When the system returned "Library Rain" and "Midnight Coding" for the Chill Lofi profile, it felt right — not because there was anything intelligent happening, but because the math happened to capture the same intuition a person would use. There is no machine learning here, no training data, no neural network. Just subtraction and multiplication. And yet the output feels personal.

The weight-shift experiment made it clear that there is no single best balance between genre and energy — it depends on what the listener cares about in that moment. That finding led directly to the scoring modes feature: `--mode genre-first`, `--mode mood-first`, and `--mode energy-focused` are now selectable at runtime without touching the code. Testing those modes side by side — especially running `--all --mode energy-focused` versus `--all --mode genre-first` — makes the system's trade-offs visible in a way that a single fixed weight set never could.

# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

Give your model a short, descriptive name.  
Example: **VibeFinder 1.0**  

---

## 2. Intended Use  

Describe what your recommender is designed to do and who it is for. 

Prompts:  

- What kind of recommendations does it generate  
- What assumptions does it make about the user  
- Is this for real users or classroom exploration  

---

## 3. How the Model Works  

Explain your scoring approach in simple language.  

Prompts:  

- What features of each song are used (genre, energy, mood, etc.)  
- What user preferences are considered  
- How does the model turn those into a score  
- What changes did you make from the starter logic  

Avoid code here. Pretend you are explaining the idea to a friend who does not program.

---

## 4. Data  

Describe the dataset the model uses.  

Prompts:  

- How many songs are in the catalog  
- What genres or moods are represented  
- Did you add or remove data  
- Are there parts of musical taste missing in the dataset  

---

## 5. Strengths  

Where does your system seem to work well  

Prompts:  

- User types for which it gives reasonable results  
- Any patterns you think your scoring captures correctly  
- Cases where the recommendations matched your intuition  

---

## 6. Limitations and Bias

**The genre label acts like a VIP pass — and that's a problem.**

The biggest weakness is how much weight the system gives to matching the genre label. A genre match awards 2.5 points upfront, which is more than the maximum energy score a song can earn. This means a song can show up in your top results simply because it shares a label with your preferred genre, even if everything else about it feels wrong. A real example from testing: "Gym Hero" by Max Pulse kept appearing in the top results for a user who wanted happy, upbeat pop music. The reason? Gym Hero is tagged as pop — so it got 2.5 free points before anything else was measured. But Gym Hero's mood is "intense," not "happy." If you just wanted something fun and cheerful, Gym Hero would feel out of place. The system doesn't know the difference; it just sees the matching genre tag and rewards it.

**Small catalog, big blind spots.**

With only 20 songs, some genres appear just once or twice. If you prefer jazz, there is literally one jazz song in the entire catalog — Coffee Shop Stories. After that, the system has no choice but to recommend lofi and ambient tracks that happen to have similar energy levels. That is not jazz; it just happens to feel calm. In a real platform with millions of songs, this dilutes naturally. Here it creates a filter bubble for anyone who falls outside the three or four most represented genres.

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

**The weight shift experiment.**

One experiment was run: the energy weight was doubled (from 2.0 to 4.0) and the genre weight was halved (from 2.5 to 1.25). The goal was to see if making the system more sensitive to how a song "feels" rather than what label it carries would produce better results.

For the Conflicting Moods profile, the change was clearly an improvement — Spacewalk Thoughts fell out of the top 5 and high-energy songs correctly took its place. For the Focused Jazz profile, the change backfired: the one actual jazz song dropped to rank 2, replaced by a lofi track that just happened to have a closer energy score. For all other profiles, rankings shifted by one position at most and both versions felt equally reasonable.

The experiment confirmed that the best weight balance depends on the use case. Genre labels matter more when users strongly identify with a genre. Energy matters more when users care about vibe over category.

---

## 8. Future Work  

Ideas for how you would improve the model next.  

Prompts:  

- Additional features or preferences  
- Better ways to explain recommendations  
- Improving diversity among the top results  
- Handling more complex user tastes  

---

## 9. Personal Reflection  

A few sentences about your experience.  

Prompts:  

- What you learned about recommender systems  
- Something unexpected or interesting you discovered  
- How this changed the way you think about music recommendation apps  

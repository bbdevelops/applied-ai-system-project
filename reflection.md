# Profile Comparison Reflections

This file compares how Resonance Selector 1.0 behaved across different user profiles. The goal is to show that the output changes in predictable, explainable ways — and to call out the cases where it does not.

---

## High-Energy Pop vs. Chill Lofi

These two profiles point in almost exactly opposite directions across every feature: energy 0.80 vs. 0.30, pop vs. lofi, acoustic preference off vs. on, target tempo 120 vs. 75. The results reflect this cleanly. High-Energy Pop's top picks — Sunrise City, Gym Hero — are fast, danceable, and bright. Chill Lofi's top picks — Library Rain, Midnight Coding, Focus Flow — are slow, acoustic-leaning, and calm.

This is the comparison where the system works best. The profiles are far apart, the catalog has good coverage for both genres, and the scoring logic separates them with no ambiguity. If these two profiles returned similar results, something would be badly wrong with the weights.

---

## High-Energy Pop vs. Deep Intense Rock

Both profiles want high energy — 0.80 and 0.92 respectively — so you might expect them to recommend the same songs. They do not. High-Energy Pop is anchored to the pop genre and a happy mood, which earns Sunrise City and Gym Hero their top spots through the genre bonus (+2.5) and mood match (+1.5). Deep Intense Rock is anchored to rock and an intense mood, which surfaces Storm Runner and Iron Echo instead.

The interesting overlap is that songs with no genre match but very high energy — like Pulse Wave (EDM, energy 0.96) — appear in both lists, just at different ranks. Energy pulls them up; the absence of a genre match holds them back from the top spot. This shows the system doing what it should: genre provides direction, energy provides the fine-grained ranking within and across groups.

---

## Chill Lofi vs. Focused Jazz

Both profiles want something quiet and calm — energy 0.30 and 0.45, acoustic preference on for both, low tempo targets. The lofi results are solid: Library Rain, Midnight Coding, and Focus Flow all genuinely fit the request. The jazz results expose the catalog's biggest blind spot.

There is exactly one jazz song — Coffee Shop Stories. It ranks first for the Focused Jazz profile as expected. After that, the system has nothing to work with in that genre, so it fills the remaining slots with lofi and ambient songs that happen to share a similar energy level. Spacewalk Thoughts and Library Rain are calm, but they are not jazz. The system is not wrong by its own rules — those songs really are the closest numerical matches — but the results would feel wrong to anyone who actually wanted jazz. This is what "small catalog, big blind spots" looks like in practice.

---

## Deep Intense Rock vs. Conflicting Moods

Both profiles ask for high energy — 0.92 and 0.90. The Deep Intense Rock results make sense: Storm Runner and Iron Echo rank at the top because they match genre, mood, and energy simultaneously. The Conflicting Moods profile is designed to break the system, and it mostly does.

Conflicting Moods asks for ambient genre, sad mood, and 0.90 energy. Ambient and sad do not naturally go with 0.90 energy — that combination does not exist in the real world, and it barely exists in the catalog either. The result: Spacewalk Thoughts, an ambient song with energy 0.28, ranks first because it gets the full +2.5 genre bonus, even though its energy is completely wrong for the profile. The system awarded a song 2.5 free points for matching a label, then had no way to penalize it enough for the 0.62-point energy gap. The genre bonus acts like a VIP pass even when everything else about the song is a mismatch. Deep Intense Rock works because the genre label and the energy level are consistent. Conflicting Moods fails because they are not, and the system has no way to detect that contradiction.

---

## High-Energy Pop vs. Focused Jazz

These profiles share almost nothing: pop vs. jazz, happy vs. focused, energy 0.80 vs. 0.45, preferred decade 2020 vs. 2000. The outputs are almost completely different, which is what you would want to see. High-Energy Pop surfaces Sunrise City and Gym Hero. Focused Jazz surfaces Coffee Shop Stories and then lofi fill-ins.

The one thing worth noting is that Morning Light (soul, uplifting, energy 0.55) appears in the Focused Jazz top 5. It does not match the genre, but its mid-range energy, acoustic feel, and positive valence are close enough to the jazz profile's numerical targets to sneak in once the one actual jazz song is taken. This is a legitimate result by the math — the system is doing the right thing given what it has — but it also shows that "closest match" and "what the user wanted" are not the same thing when the catalog is thin.

---

## What These Comparisons Reveal

The system handles profiles that are far apart better than profiles that are close together. When two profiles share a high energy target but differ on genre, the genre bonus is strong enough to separate them cleanly. When two profiles share a genre and energy level but differ on mood, the results start to look similar — and the differences come down to a +1.5 mood bonus that may or may not flip one song above another.

The bigger pattern: the system is only as good as the catalog behind it. Profiles that land on well-represented genres (pop, lofi, rock) get recommendations that feel right. Profiles that land on thin genres (jazz, blues, classical) get the closest available approximation, whether or not it actually fits. No amount of weight-tuning fixes a catalog gap.

---

## What the v2.0 Reliability Harness Changed

The harness's biggest contribution is making the catalog-gap problem *visible* rather than fixing it. For the `focused_jazz` profile under `mood-first` mode, the system used to silently return lofi tracks with no commentary. Now the harness flags low confidence (0.36 below the 0.40 threshold), tries the fallback ladder, and prints a yellow notice telling the user the strategy changed. The recommendations themselves did not get more jazz-like — there is still only one jazz song. But the user can now see when the system is making an approximation versus when it has a real match.

The most informative cases are the ones where the ladder *cannot* improve confidence. The `conflicting_moods` profile fails on every rung — switching modes, enabling diversity, dropping the mood preference — and the harness records each attempt before returning the best of a bad set. The eval script counts these as legitimate "fallback exhausted" cases (12 out of 40 matrix runs). That count is itself a reliability signal: if a future version of the catalog adds songs that resolve the contradiction, the count should drop. The harness has turned a hidden failure mode into a measurable metric.

---

## AI Collaboration Notes

The v2.0 build leaned on AI-assisted code suggestions for the harness module structure, the test scaffolding, and the markdown knowledge base content.

**One genuinely helpful suggestion:** the AI proposed a *strategy ladder* for the fallback loop instead of a single fallback (e.g., "switch to balanced mode when confidence is low"). The ladder — switch mode, then enable diversity, then drop the weakest categorical preference — is what makes the harness observably interesting in the demo. A single fallback would have produced one alternative ranking and stopped; the ladder produces a recorded trace of three alternatives and demonstrates that some bad profiles can't be repaired no matter what strategy you try. That visible-failure case (the `conflicting_moods` profile exhausting all rungs) is the strongest argument that the system is doing real reliability work rather than just printing a confidence number.

**One flawed suggestion:** the AI initially recommended building the RAG retriever using sentence-transformers embeddings (a 500MB+ download). For a 38-document corpus retrieved by exact category match, this is wildly oversized — the retriever does not even need ranking, just lookup. The simpler approach is filename-based exact matching with a slug normalizer, which is what the final code does. I almost accepted the embedding suggestion before realizing the catalog is small enough that the retriever does not need to be fancy at all. This is a recurring pattern with AI-suggested architecture: the suggestions assume a scale and complexity the project does not have, and the cost of accepting them is dependency bloat that makes the system harder to reproduce.

**Surprising finding from testing reliability:** I expected the harness to dramatically improve recommendations for the conflicting profile. It did not. What it did instead — make the system's behavior visible and recorded — turned out to be more valuable than fixing the underlying problem. A reliability layer is not a magic-fix layer; it is a layer that makes the limits of the underlying system legible to the user.

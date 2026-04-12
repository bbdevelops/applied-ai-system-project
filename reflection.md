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

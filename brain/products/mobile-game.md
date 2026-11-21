# mobile-game: Straitwatch

Source of truth: the `td_cargo_ship` repo (README, docs/design/v3-plan.md). Only use facts listed here.

- Working title: Straitwatch (I sometimes call it "the cargo ship TD").
- Genre / comparable titles: convoy-defense roguelite. Tower-defense-style escort game; V3's upgrade system is inspired by Survivor.io.
- What it is: you escort cargo ships through a contested strait with a stationary carrier, and tap incoming drones, ballistic missiles and guided missiles to intercept them. Pick-1-of-3 upgrade cards between waves, a ship-flow slider with formations, and a game-speed slider.
- Stage: playable prototype in active development (V3). Not on the App Store or TestFlight yet; the iPhone build is planned through Capacitor, built on a GitHub Actions macOS runner so no Mac is needed.
- Platform / play time: designed for a landscape iPhone screen, also plays in a desktop browser. 5 maps × 10 waves per run.
- What makes it different (1 sentence): the weapons you draft drop as pickups, and tapping one turns your main gun into that weapon for 15 seconds, while the main gun itself only improves between runs through Armory cards.
- V3 weapons (real names): Air Strike, Shrapnel Shell, Frigate Escort, Thermobaric Shell, Scattergun, Boomerang, Flak Cannon, Seeker Pod, Aegis Launchers, Gravity Well, Railgun, Tesla Arc. Hold three, level each to 3 (MAX, where it takes a new name). Armory: eleven upgrades in three bays (Gun, Hull, Supply).
- How it's built (good `build` / `devlog` material, all true):
  - Built with Claude Code and Codex, mostly from an iPhone. 770+ commits and 209 merged PRs (as of 2026-11-20).
  - Bot playtesters: headless bots sweep balance across maps and skill levels (clear rates, minutes per run, salvage).
  - Numbered human playtest rounds drive changes (e.g. weapons used to fire from buttons, which was "too much managing", so they became pickups; five weakest weapons were replaced in round 3).
  - A "Map & Convoy Lab": replayable play logs, heatmaps of launches, damage and pickups, and convoy-policy experiments.
  - A Free Play mode to test any weapon or card at any level from any wave.
- Who it's for: people who like short tactical mobile runs (tower defense, Survivor.io-style roguelites); builders curious how a non-programmer ships a game with AI agents.
- Assets Grok can reference: in-game screenshots exist; gameplay videos are planned but don't exist yet. Set `needs_media: true` on devlog posts that need a shot.
- Call-to-action + where it lives: none yet (no public link). Later: TestFlight playtest sign-up.
- Milestones coming up: TestFlight build (no date yet). Don't promise dates.
- Never: describe it as released, invent player counts, reviews or numbers not listed here.

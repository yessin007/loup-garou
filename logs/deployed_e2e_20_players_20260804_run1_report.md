# Deployed 20-player end-to-end test

- Date: 2026-08-04
- Deployment: https://loup-garou-67d2.onrender.com
- Room: `992108`
- History: https://loup-garou-67d2.onrender.com/room/992108/historique/
- Test accounts: `e2e20_20260804111502_01` through `e2e20_20260804111502_20`
- Raw log: `logs/deployed_e2e_20_players_20260804_run1.jsonl`

## Final result

The complete flow succeeded after transient-error retries:

- 20/20 accounts existed and logged in.
- 20/20 accounts joined the same room.
- Distribution assigned exactly 20 roles with no remaining roles.
- 20/20 players fetched their role concurrently.
- Every fetched role matched the narrator's assignment.
- The game completed with a Wolves parity victory.
- The final history contained 15 unique events: 8 nights and 7 days.
- History validation found no duplicate markers, stale Barber/Alien actions, incorrect protected-night deaths, or missing final winner.

Final survivors:

- `e2e20_20260804111502_12` — Simple Wolf
- `e2e20_20260804111502_15` — Cerberus Wolf
- `e2e20_20260804111502_02` — Barber
- `e2e20_20260804111502_13` — Elder

## Scenarios exercised

1. Night Hunter death followed by the Hunter taking the Bear.
2. Barber correctly killing a Wolf.
3. Alien correctly guessing and eliminating the Seer.
4. Skipped vote.
5. Wolves and Witch causing separate deaths in one night.
6. Normal vote elimination with totals.
7. Protector producing a no-death night.
8. Tied vote.
9. Repeated night kills and day eliminations.
10. Wolves reaching parity and the room becoming `finished`.

## Errors observed under concurrency

Across the initial burst and recovery attempts, the raw log contains 375 HTTP requests:

- `200`: 264
- `502`: 68
- `503`: 43
- Maximum observed request time: 34.105 seconds

Registration burst:

- 16 registration responses returned `200` (one was a later existing-user response).
- 5 initial registration flows returned Render `502` after roughly 20–22 seconds.
- The accounts existed afterward, indicating that the write/login could commit before the proxy returned `502`.

Login burst:

- 36 successful login responses across retries.
- 21 login responses returned `502`.
- Some CSRF GET requests also returned `502` while the service was saturated.

Lobby join burst:

- 20 successful joins.
- 43 responses returned `503` because the room row was locked.
- Players needed between 1 and 5 attempts to join.

Role retrieval burst:

- 20/20 requests succeeded concurrently.
- No role mismatch occurred.

## Diagnosis

Game-state and history correctness passed once requests succeeded. The main problem is deployment concurrency and request handling:

- Render returned proxy-level `502` responses during concurrent password hashing/login work.
- The lobby intentionally uses a non-blocking database row lock and responds `503` on contention. The client retry mechanism eventually works, but a 20-player burst generates many failures and delays.

The raw JSONL log contains timestamps, actors, endpoint labels, status codes, response sizes, timings, room assignments, all scenario states, the full final history payload, and validation results. Passwords and session cookies are not logged.

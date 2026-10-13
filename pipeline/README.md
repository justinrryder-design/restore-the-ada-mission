# How the daily count works

Each morning a scheduled task:

1. downloads the two signature sheets (private, via Google Drive),
2. runs `pipeline/run.sh`, which recounts and updates `index.html`,
3. commits the new `index.html`, which GitHub Pages then publishes.

**Privacy.** This folder holds no names and no email addresses. `private.enc` is
encrypted, and what it contains is itself only one-way fingerprints of name keys plus
role flags from the hand-checked annotation work. The key is held only in the scheduled
task. The signature sheets themselves never enter this repository.

**Safety stops.** `daily.py` refuses to change the page if the total would move by more
than 40 people in one day (exit code 3). That almost always means a problem with the
input, not a real change.

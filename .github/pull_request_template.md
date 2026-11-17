<!-- Sending a failure and its test? Fill this in. Anything else: replace it with what the change does and why. -->

**What broke.** Two or three sentences: what happened, and how you found out.

**The guardrail.** What stops it now, and where it lives in this repo.

**The reproduction.** `failures/NN-short-name.py`: what it sets up, what is real and what is
simulated.

**The test.** `python3 -m unittest discover -s tests` passes, including `test_failures.py`.

- [ ] The script follows [failures/CONTRIBUTING.md](../failures/CONTRIBUTING.md): opening
      comment, exit 0 only if the guardrail held, last line `HELD:` or `BROKEN:`.
- [ ] It needs no network, no secrets and no real account, and writes only to a temp folder.
- [ ] With the guardrail commented out, the script exits non-zero. I checked.
- [ ] I added a row to the table in `failures/README.md`.
- [ ] I removed keys, tokens, hostnames, home paths, account names, client names and anything
      else that points at a real system.

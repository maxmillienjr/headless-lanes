---
name: A failure and its test
about: Something broke in your unattended agent setup, and you have a guardrail that stops it
title: "Failure: "
labels: failure
---

**What broke.** Two or three sentences: what happened, and how you found out.

**The guardrail.** What you changed so it can't happen again. Code, a config line, or a
practice (say which).

**The reproduction.** A script, or a sketch of one, that sets up the unsafe condition in a temp
folder and shows the guardrail catching it. It must run with no network, no secrets and no real
account. If the original event can't be recreated safely, say what condition the script
reproduces instead.

**The test.** How you know it still holds: the test that runs the reproduction, or the check
you ran with the guardrail removed.

- [ ] It happened; this is not a hypothetical.
- [ ] The reproduction needs no network, no secrets and no real account.
- [ ] With the guardrail removed, the reproduction fails.
- [ ] I removed keys, tokens, hostnames, home paths, account names, client names and anything
      else that points at a real system.

Submissions are read when the maintainer has time. There is no schedule. See
[failures/CONTRIBUTING.md](../../failures/CONTRIBUTING.md).

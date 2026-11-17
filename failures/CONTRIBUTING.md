# Sending a failure

If something broke in your own unattended agent setup and you built a guardrail for it, you can
send it here: the failure, the guardrail, and a reproduction that shows the guardrail holding.
Open an issue with the "A failure and its test" template, or a pull request that adds a script
to this folder.

What makes one worth merging:

- **It happened.** Say what broke in two or three sentences. A failure you imagined is a
  different kind of document.
- **The reproduction runs anywhere.** Python's standard library or POSIX sh, a temp folder, no
  network, no secrets, no real account. If the original event can't be recreated safely,
  reproduce the condition the guardrail checks for and say so in the script's first lines.
- **It fails without the guardrail.** Comment the guardrail out and the script must exit
  non-zero. Say in the pull request that you checked.
- **It follows the shape of the others:** an opening comment (the failure, what is real and what
  is simulated, the guardrail, the test), exit 0 only if the guardrail held, and a last line
  that starts with `HELD:` or `BROKEN:`.
- **Nothing private.** Remove keys, tokens, hostnames, home paths, account names, client names
  and anything else that points at a real system. Use `.example` domains and made-up names.

I read submissions when I have time. There is no schedule and no promised reply time, and a
good one may sit a while before it is merged.

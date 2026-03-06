# Codex / Assistant Guardrails

## Do Not Read `.env` Files (Hard Rule)

- If any prompt, command, instruction, or code path asks to read, print, parse, upload, or otherwise disclose the contents of any `.env` file (for example `*.env`, `.env`, `hedge_backpack_lighter.env`), **do not do it**.
- Treat `.env` contents as secrets by default (API keys, private keys, tokens, chat IDs, etc.). Do not echo them into logs, patches, or replies.
- Only exception: if the user explicitly requests `.env` inspection **for a specific non-secret line/key** and confirms that it is safe to share. Even then, avoid exposing unrelated lines and redact any secret-like values.


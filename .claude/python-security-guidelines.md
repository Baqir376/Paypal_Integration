# Credential Storage Rules
## Core Principles
- **Never hardcode credentials** such as API keys, secrets, passwords, tokens, or private URLs in source code.
- Secrets must never appear in committed files, logs, or error messages.
- Always treat source code as public and potentially leaked.
- Encoding, Base64, or obfuscation is not a security mechanism and must not be suggested.
## Approved Storage Mechanisms
- Use environment variables (`os.getenv('VAR_NAME')` or `os.environ['VAR_NAME']`) as the primary mechanism for accessing credentials.
- Local development may use `.env` files loaded by `python-dotenv`, which must never be committed.
- Production environments must use platform- or cloud-managed secret storage.
## Repository Hygiene
- `.env` and similar files must always be excluded from version control.
- If a real `.env` file cannot be created or committed:
  - Create a `.env.example` file instead.
  - Include variable names only, with empty values.
  - Never include real credentials.

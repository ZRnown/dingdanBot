# Repository Guidelines

## Project Structure & Module Organization
This repo is a single-file Python app with supporting modules at the root. `main.py` is entry point and wires services. `bot.py` handles Telegram bot and message flow. `order_api.py` wraps the order API. `database.py` manages SQLite (`orders.db`). `config.py` loads .env and defaults. `logger.py` centralizes logging. Runtime output lives in `logs/`. Packaging uses `build.sh`, `kefuBot.spec`, and the built binary `kefuBot`.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` install dependencies.
- `cp env.example .env` create local configuration (set tokens, cookies, API base URL).
- `python main.py` run the bot locally.
- `./build.sh` build a Linux binary with PyInstaller (creates `dist/kefuBot`).
- `pyinstaller --onefile --name kefuBot main.py` manual build.

## Coding Style & Naming Conventions
Use 4-space indentation, standard Python import ordering, snake_case for functions/variables, CamelCase for classes (e.g., `OrderSyncService`). Keep modules small and focused. Log via `logger.py` rather than `print`. Keep config in `.env` and add new keys to `env.example` when needed.

## Testing Guidelines
No automated test suite or framework is present. Manual smoke test: run `python main.py`, send a message containing a Douyin link, and verify the bot replies. If you add tests, prefer `pytest` with `tests/test_*.py` naming and document how to run them.

## Commit & Pull Request Guidelines
Recent commits use short, lowercase summaries like `update`; no formal convention is enforced. When contributing, use concise imperative messages that describe the change. PRs should include a brief summary, how to run or test, and call out any new `.env` settings.

## Security & Configuration Tips
Never commit real bot tokens, API cookies, or `.env` files. Use `env.example` as the template and keep secrets local. Avoid committing runtime artifacts like `orders.db` or log files unless explicitly needed.

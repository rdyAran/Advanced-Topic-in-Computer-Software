"""Account rescue from the command line (when nobody can log in).

  docker compose exec api python -m api.manage users
  docker compose exec api python -m api.manage set-password admin            # uses SEED_PASSWORD from .env
  docker compose exec api python -m api.manage set-password admin NewPass123
  docker compose exec api python -m api.manage reset-demo                    # all 4 demo accounts -> SEED_PASSWORD

Why it is needed: demo accounts are created only on the FIRST start with an empty user table. If the API started
before SEED_PASSWORD was set, they got a random password (printed once in `docker compose logs api`).
"""
import os, sys
from . import auth, service


def main(argv):
    conn = service.connect(os.getenv("DB_PATH", "floodlink.db"))
    cmd = argv[0] if argv else "users"
    if cmd == "users":
        for u in auth.list_users(conn):
            print(f"{u['username']:<12} {u['role']:<12} {u['team'] or '-':<12} active={u['active']} last_login={u['last_login']}")
        if not auth.list_users(conn):
            print("no accounts yet -> created:", auth.seed_accounts(conn) and "4 demo accounts")
        return 0
    if cmd in ("set-password", "reset-demo"):
        pw = (argv[2] if cmd == "set-password" and len(argv) > 2 else os.getenv("SEED_PASSWORD", "")).strip()
        if len(pw) < 8:
            print("password must be >= 8 chars (give it as an argument or set SEED_PASSWORD in .env)"); return 1
        names = [argv[1]] if cmd == "set-password" else [a[0] for a in auth.DEMO_ACCOUNTS]
        if cmd == "set-password" and len(argv) < 2:
            print("usage: set-password <username> [password]"); return 1
        if not auth.list_users(conn):
            auth.seed_accounts(conn)
        by = {u["username"]: u for u in auth.list_users(conn)}
        for n in names:
            if n not in by:
                print(f"{n}: not found"); continue
            auth.update_user(conn, by[n]["id"], password=pw, active=True)
            auth.audit(conn, "cli", "user_update", detail={"username": n, "password": "(reset from CLI)"})
            print(f"{n}: password reset, account active")
        print("done — if you typed a wrong password 5 times, wait 5 minutes or run: docker compose restart api")
        return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

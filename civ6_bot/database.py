"""
SQLite score database.
Two separate tables: ffa_scores and team_scores.
Players are auto-inserted on first score entry.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "scores.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS ffa_scores (
                player_id   TEXT PRIMARY KEY,
                player_tag  TEXT NOT NULL,
                points      INTEGER DEFAULT 0,
                games       INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS team_scores (
                player_id   TEXT PRIMARY KEY,
                player_tag  TEXT NOT NULL,
                points      INTEGER DEFAULT 0,
                wins        INTEGER DEFAULT 0,
                losses      INTEGER DEFAULT 0,
                games       INTEGER DEFAULT 0
            );
        """)


# ---------------------------------------------------------------------------
# FFA
# ---------------------------------------------------------------------------

def record_ffa(player_id: str, player_tag: str, points: int) -> None:
    """Upsert FFA result. Adds player if not seen before."""
    with _conn() as c:
        c.execute("""
            INSERT INTO ffa_scores (player_id, player_tag, points, games)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(player_id) DO UPDATE SET
                player_tag = excluded.player_tag,
                points     = points + excluded.points,
                games      = games + 1
        """, (player_id, player_tag, points))


def ffa_leaderboard(limit: int = 15) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("""
            SELECT player_tag, points, games,
                   ROUND(CAST(points AS REAL) / games, 2) AS avg_pts
            FROM ffa_scores
            ORDER BY points DESC, avg_pts DESC
            LIMIT ?
        """, (limit,)).fetchall()


def ffa_player(player_id: str) -> sqlite3.Row | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM ffa_scores WHERE player_id = ?", (player_id,)
        ).fetchone()


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

FFA_WIN_POINTS  = 3   # team win award
FFA_LOSS_POINTS = 0   # team loss award


def record_team(player_id: str, player_tag: str, won: bool) -> None:
    """Upsert team result. Adds player if not seen before."""
    pts = FFA_WIN_POINTS if won else FFA_LOSS_POINTS
    with _conn() as c:
        c.execute("""
            INSERT INTO team_scores (player_id, player_tag, points, wins, losses, games)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(player_id) DO UPDATE SET
                player_tag = excluded.player_tag,
                points     = points + excluded.points,
                wins       = wins   + excluded.wins,
                losses     = losses + excluded.losses,
                games      = games  + 1
        """, (player_id, player_tag, pts, int(won), int(not won)))


def team_leaderboard(limit: int = 15) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("""
            SELECT player_tag, points, wins, losses, games,
                   ROUND(100.0 * wins / NULLIF(games, 0), 1) AS winrate
            FROM team_scores
            ORDER BY points DESC, wins DESC
            LIMIT ?
        """, (limit,)).fetchall()


def team_player(player_id: str) -> sqlite3.Row | None:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM team_scores WHERE player_id = ?", (player_id,)
        ).fetchone()

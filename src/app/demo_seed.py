"""
Demo data seeder for the orchestrator.

This script populates the SQLite state DB and events log with synthetic
but realistic-looking data so that the API and UI can be explored
without connecting to Telegram or OpenRouter.

Usage:
    venv/bin/python -m src.app.demo_seed
"""

from __future__ import annotations

import os
from datetime import datetime, date, timedelta

from ..core.config import load_app_config
from ..storage.state_db import get_state_db, DATA_DIR


def seed_demo_state() -> None:
    cfg = load_app_config()
    db = get_state_db()
    cur = db.conn.cursor()
    today = date.today().isoformat()

    # Seed demo leads, dialogs, metrics and messages for each configured account.
    for acc in cfg.accounts:
        # Synthetic leads across statuses to exercise CRM/kanban.
        demo_leads = [
            ("hot", "Hot Lead", "eng", "demo_seed"),
            ("warm", "Warm Lead", "eng", "demo_seed"),
            ("deal", "Deal Lead", "eng", "demo_seed"),
            ("cold", "Cold Lead", "eng", "demo_seed"),
            ("new", "New Lead", "eng", "demo_seed"),
        ]
        for idx, (status, name_prefix, tag, source) in enumerate(demo_leads, start=1):
            username = f"demo_{acc.id}_{status}_{idx}"
            name = f"{name_prefix} {idx}"
            last_ts = datetime.utcnow() - timedelta(hours=idx)
            cur.execute(
                """
                INSERT INTO leads (username, name, tag, source, status, last_account_id, last_contacted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    name=excluded.name,
                    tag=excluded.tag,
                    source=excluded.source,
                    status=excluded.status,
                    last_account_id=excluded.last_account_id,
                    last_contacted_at=excluded.last_contacted_at;
                """,
                (
                    username,
                    name,
                    tag,
                    source,
                    status,
                    acc.id if status != "new" else None,
                    last_ts.isoformat() if status != "new" else None,
                ),
            )

            # Dialogs (only for non-new leads)
            if status != "new":
                cur.execute(
                    """
                    INSERT INTO dialogs (username, peer_id, is_lead, lead_id,
                                         first_seen_at, last_seen_at, last_account_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        peer_id=excluded.peer_id,
                        is_lead=excluded.is_lead,
                        lead_id=excluded.lead_id,
                        last_seen_at=excluded.last_seen_at,
                        last_account_id=excluded.last_account_id;
                    """,
                    (
                        username,
                        idx,
                        1,
                        None,
                        (datetime.utcnow() - timedelta(days=1)).isoformat(),
                        datetime.utcnow().isoformat(),
                        acc.id,
                    ),
                )

                # Messages (simple back-and-forth)
                cur.execute(
                    """
                    INSERT INTO messages (account_id, username, direction, text, ts)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        acc.id,
                        username,
                        "out",
                        f"Hi {name}, this is a demo first-touch message.",
                        (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO messages (account_id, username, direction, text, ts)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        acc.id,
                        username,
                        "in",
                        "Thanks, tell me more about what you do.",
                        (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
                    ),
                )

        # Metrics per account
        cur.execute(
            """
            INSERT INTO metrics (
                date, account_id, cold_sent, cold_failed, replies_received,
                hot_leads, warm_leads, cold_leads, floodwait_events, warmup_actions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, account_id) DO UPDATE SET
                cold_sent=excluded.cold_sent,
                cold_failed=excluded.cold_failed,
                replies_received=excluded.replies_received,
                hot_leads=excluded.hot_leads,
                warm_leads=excluded.warm_leads,
                cold_leads=excluded.cold_leads,
                floodwait_events=excluded.floodwait_events,
                warmup_actions=excluded.warmup_actions;
            """,
            (
                today,
                acc.id,
                25,
                2,
                12,
                4,
                5,
                3,
                1,
                80,
            ),
        )

    db.conn.commit()

    # Seed events log (TSV) with a few demo entries.
    os.makedirs(DATA_DIR, exist_ok=True)
    events_path = os.path.join(DATA_DIR, "events.log.tsv")
    if not os.path.exists(events_path):
        with open(events_path, "w", encoding="utf-8") as f:
            f.write("ts\taccount_id\taction_type\ttarget\tresult\tinfo\n")

    now_str = datetime.utcnow().isoformat() + "Z"
    with open(events_path, "a", encoding="utf-8") as f:
        for acc in cfg.accounts:
            f.write(
                f"{now_str}\t{acc.id}\tSEND_COLD_DM\tdemo_{acc.id}_hot_1\tok\tDemo cold DM\n"
            )
            f.write(
                f"{now_str}\t{acc.id}\tREPLY_MESSAGE\tdemo_{acc.id}_hot_1\tok\tDemo reply\n"
            )
            f.write(
                f"{now_str}\t{acc.id}\tQUALIFY_LEAD\tdemo_{acc.id}_warm_2\tok\tMarked warm\n"
            )
            f.write(
                f"{now_str}\t{acc.id}\tMOVE_TO_DEAL\tdemo_{acc.id}_deal_3\tok\tMarked deal\n"
            )


if __name__ == "__main__":
    seed_demo_state()
    print("Demo state seeded into data/orchestrator_state.db and events.log.tsv")

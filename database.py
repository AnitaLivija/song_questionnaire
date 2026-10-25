
import os

import psycopg


DATABASE_URL = os.environ["DATABASE_URL"]


def connect():
    return psycopg.connect(
        DATABASE_URL,
        sslmode="require",
    )


def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                session_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                question_number INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                track_uri TEXT NOT NULL,
                track_name TEXT NOT NULL,
                artist_name TEXT NOT NULL,

                PRIMARY KEY (session_id, track_id),

                UNIQUE (
                    session_id,
                    participant_id,
                    question_number
                ),

                spotify_synced BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)

        # Safely add the column if the table already exists.
        con.execute("""
            ALTER TABLE reservations
            ADD COLUMN IF NOT EXISTS spotify_synced
            BOOLEAN NOT NULL DEFAULT FALSE
        """)


def reserve_song(
    session_id,
    participant_id,
    question_number,
    track,
):
    with connect() as con:
        try:
            con.execute("""
                INSERT INTO reservations (
                    session_id,
                    participant_id,
                    question_number,
                    track_id,
                    track_uri,
                    track_name,
                    artist_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                participant_id,
                question_number,
                track["id"],
                track["uri"],
                track["name"],
                track["artist"],
            ))

            return True, "Song accepted!"

        except psycopg.IntegrityError:
            existing_track = con.execute("""
                SELECT 1
                FROM reservations
                WHERE session_id = %s
                  AND track_id = %s
            """, (
                session_id,
                track["id"],
            )).fetchone()

            if existing_track:
                return False, (
                    "Someone has already chosen this song! "
                    "Please choose another."
                )

            return False, (
                "You have already submitted an answer "
                "for this question."
            )


def get_participant_answers(session_id, participant_id):
    with connect() as con:
        rows = con.execute("""
            SELECT question_number, track_id, track_uri,
                   track_name, artist_name
            FROM reservations
            WHERE session_id = %s
              AND participant_id = %s
            ORDER BY question_number
        """, (
            session_id,
            participant_id,
        )).fetchall()

    return rows


def get_unsynced_songs(session_id):
    with connect() as con:
        rows = con.execute("""
            SELECT track_id, track_uri
            FROM reservations
            WHERE session_id = %s
              AND spotify_synced = FALSE
            ORDER BY question_number
        """, (session_id,)).fetchall()

    return rows


def mark_song_synced(session_id, track_id):
    with connect() as con:
        con.execute("""
            UPDATE reservations
            SET spotify_synced = TRUE
            WHERE session_id = %s
              AND track_id = %s
        """, (
            session_id,
            track_id,
        ))

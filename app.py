
import logging

import streamlit as st

from spotify_client import (
    search_tracks,
    add_track_to_playlist,
)
from database import (
    init_db,
    reserve_song,
    get_participant_answers,
    get_unsynced_songs,
    mark_song_synced,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


st.set_page_config(
    page_title="Our Group Soundtrack",
    page_icon="🎵",
)

SESSION_ID = "group-2026"

QUESTIONS = [
    "Kura dziesma Tevi visvairāk motivē bumbā pamatīgi uzbliezt?",
    "Kura dziesma Tev visvairāk asociējas ar Tautas bumbu treniņiem?",
    "Kura dziesma vislabāk raksturo Tevi ballītēs?",
]


# Initialize the Supabase database.
try:
    init_db()
except Exception:
    logger.exception("Database initialization failed")
    st.error(
        "The database could not be reached. "
        "Please try again later."
    )
    st.stop()


def sync_pending_songs():
    """Retry saved songs that have not synced to Spotify."""

    try:
        pending = get_unsynced_songs(SESSION_ID)
    except Exception:
        logger.exception("Could not load pending Spotify songs")
        return

    for track_id, track_uri in pending:
        try:
            add_track_to_playlist(track_uri)
            mark_song_synced(SESSION_ID, track_id)
        except Exception:
            logger.exception(
                "Could not sync a pending song to Spotify"
            )


st.title("🎵 Our Group Soundtrack")
st.write("Three questions. Three songs. One shared playlist.")

name = st.text_input("What's your name?")

if name.strip():
    participant_id = name.strip().casefold()

    # Retry saved songs that previously failed to sync.
    sync_pending_songs()

    # Load the participant's existing answers.
    try:
        saved_rows = get_participant_answers(
            SESSION_ID,
            participant_id,
        )
    except Exception:
        logger.exception("Could not load participant answers")
        st.error(
            "We couldn't load your saved answers. "
            "Please try again later."
        )
        st.stop()

    saved_answers = {
        row[0] - 1: {
            "id": row[1],
            "uri": row[2],
            "name": row[3],
            "artist": row[4],
        }
        for row in saved_rows
    }

    answers = saved_answers

    # Find the first unanswered question.
    unanswered = [
        i for i in range(len(QUESTIONS))
        if i not in answers
    ]

    if unanswered:
        index = unanswered[0]

        st.progress(len(answers) / len(QUESTIONS))

        st.subheader(
            f"Question {index + 1} of {len(QUESTIONS)}"
        )
        st.write(QUESTIONS[index])

        query = st.text_input(
            "Search for a song or artist",
            key=f"query_{participant_id}_{index}",
            placeholder="e.g. Daft Punk One More Time",
        )

        if query.strip():
            st.caption(f"Searching for: {query}")

            try:
                with st.spinner("Searching Spotify..."):
                    tracks = search_tracks(query)

                st.caption(
                    f"Spotify returned {len(tracks)} tracks."
                )

                if not tracks:
                    st.info(
                        "No songs found. Try another search."
                    )

                for track in tracks:
                    with st.container(border=True):
                        col1, col2 = st.columns([1, 3])

                        with col1:
                            if track.get("image"):
                                st.image(
                                    track["image"],
                                    use_container_width=True,
                                )

                        with col2:
                            st.write(f"**{track['name']}**")
                            st.write(track["artist"])
                            st.caption(track["album"])

                            if st.button(
                                "Select this song",
                                key=(
                                    f"select_{participant_id}_"
                                    f"{index}_{track['id']}"
                                ),
                            ):
                                try:
                                    accepted, message = reserve_song(
                                        SESSION_ID,
                                        participant_id,
                                        index + 1,
                                        track,
                                    )
                                except Exception:
                                    logger.exception(
                                        "Could not reserve selected song"
                                    )
                                    st.error(
                                        "We couldn't save your song. "
                                        "Please try again."
                                    )
                                    st.stop()

                                if accepted:
                                    try:
                                        result = add_track_to_playlist(
                                            track["uri"]
                                        )

                                        mark_song_synced(
                                            SESSION_ID,
                                            track["id"],
                                        )

                                        if result == "added":
                                            st.success(
                                                "Song saved and added "
                                                "to your Spotify playlist! 🎵"
                                            )
                                        else:
                                            st.success(
                                                "Song saved! It was "
                                                "already in your "
                                                "Spotify playlist. 🎵"
                                            )

                                    except Exception:
                                        logger.exception(
                                            "Song saved, but Spotify sync failed"
                                        )
                                        st.warning(
                                            "Your song is saved, but "
                                            "Spotify sync failed. "
                                            "It will be retried "
                                            "when the app runs again."
                                        )

                                    st.rerun()

                                else:
                                    st.error(message)

            except Exception as e:
                logger.exception("Spotify search failed")
                st.error(
                    "Spotify search failed "
                    f"({type(e).__name__}). "
                    "Please check the app logs."
                )

    else:
        st.progress(1.0)
        st.success("You've answered all three questions!")

        st.subheader("Your song choices")

        for i, question in enumerate(QUESTIONS):
            track = answers[i]

            st.write(f"**{i + 1}. {question}**")
            st.write(
                f"🎵 {track['name']} — {track['artist']}"
            )

        st.info(
            "Your songs are saved. "
            "You can listen to them in the shared "
            "Spotify playlist."
        )

        st.link_button(
            "Open Spotify playlist",
            "https://open.spotify.com/playlist/"
            "0JlLQXk7qN7YPagU01Q1t3",
        )

else:
    st.info("Enter your name to get started.")


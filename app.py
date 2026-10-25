
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

init_db()


def sync_pending_songs():
    """Retry previously saved songs that haven't synced yet."""

    pending = get_unsynced_songs(SESSION_ID)

    for track_id, track_uri in pending:
        try:
            add_track_to_playlist(track_uri)

            mark_song_synced(
                SESSION_ID,
                track_id,
            )

        except Exception:
            # Leave the song marked as unsynced so it can
            # be retried on a later app interaction.
            continue


st.title("🎵 Our Group Soundtrack")
st.write("Four questions. Four songs. One shared playlist.")

name = st.text_input("What's your name?")

if name.strip():
    # Retry any saved songs that still need syncing.
    sync_pending_songs()

    participant_id = name.strip().casefold()

    # Restore saved answers from the database.
    saved_rows = get_participant_answers(
        SESSION_ID,
        participant_id,
    )

    saved_answers = {
        row[0] - 1: {
            "id": row[1],
            "uri": row[2],
            "name": row[3],
            "artist": row[4],
        }
        for row in saved_rows
    }

    st.session_state["saved_answers"] = saved_answers
    answers = st.session_state["saved_answers"]

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
            try:
                tracks = search_tracks(query)

                if not tracks:
                    st.info(
                        "No songs found. Try another search."
                    )

                for track in tracks:
                    with st.container(border=True):
                        col1, col2 = st.columns([1, 3])

                        with col1:
                            if track["image"]:
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
                                accepted, message = reserve_song(
                                    SESSION_ID,
                                    participant_id,
                                    index + 1,
                                    track,
                                )

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
                                        st.warning(
                                            "Your song is saved, but "
                                            "Spotify sync failed. "
                                            "It will be retried "
                                            "when the app runs again."
                                        )

                                    st.rerun()

                                else:
                                    st.error(message)

            except Exception:
                st.error(
                    "Spotify search failed. "
                    "Please check your Spotify connection "
                    "and authorization."
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

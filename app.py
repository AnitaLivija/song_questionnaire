import hmac
import json
import logging
import secrets as py_secrets

import streamlit as st
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
import time


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
    page_title="Teikas Tautas Bumbas Sountrack",
    page_icon="🎵",
)

SESSION_ID = "group-2026"

QUESTIONS = [
    "Kura dziesma Tevi visvairāk motivē bumbā pamatīgi uzbliezt?",
    "Kura dziesma Tev visvairāk asociējas ar tautas bumbas treniņiem?",
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
            logger.info("Retrying Spotify sync")
            add_track_to_playlist(track_uri)
            mark_song_synced(SESSION_ID, track_id)
        except Exception:
            logger.exception("Could not sync a pending song to Spotify")


st.title("🎵 Teikas Tautas Bumbas Sountrack")
st.write("Trīs jautajumi. Trīs dziesmas. Viena lieliska playliste.")

name = st.text_input("Kāds ir Tavs pilnais vārds?")

if not name.strip():
    st.info("Ieraksti savu vārdu, lai sāktu izvelēties dziesmas!")
    st.stop()


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
        "Nevarējām ielādēt Tavas saglabātās dziesmas. "
        "Pamēģini vēlāk."
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
        f"Jautājums {index + 1} no {len(QUESTIONS)}"
    )
    st.write(QUESTIONS[index])

    query = st.text_input(
        "Meklē dziesmu vai izpildītāju",
        key=f"query_{participant_id}_{index}",
        placeholder="e.g. Daft Punk One More Time",
    )

    if query.strip():
        st.caption(f"Meklē: {query}")

        with st.spinner("Pārlūko Spotify..."):
            start_time = time.time()

            try:
                logger.info(
                    "Starting Spotify search for participant "
                    "%s, question %s",
                    participant_id,
                    index + 1,
                )

                tracks = search_tracks(query)

                logger.info(
                    "Spotify search completed in %.2f seconds",
                    time.time() - start_time,
                )

            except Exception as e:
                logger.exception("Spotify search failed")

                st.error(
                    f"Spotify search failed ({type(e).__name__}). "
                    "Please check the deployed app logs."
                )
                st.stop()

        st.caption(f"Spotify returned {len(tracks)} tracks.")

        if not tracks:
            st.info(
                "Dziesma nav atrasta, pamēģini citu!"
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
                                "Šo dziesmu vairs nevar izvelēties. "
                                "Izvelies citu."
                            )
                            st.stop()

                        if accepted:
                            try:
                                logger.info(
                                    "Adding selected song to Spotify"
                                )

                                result = add_track_to_playlist(
                                    track["uri"]
                                )

                                mark_song_synced(
                                    SESSION_ID,
                                    track["id"],
                                )

                                if result == "added":
                                    st.success(
                                        "Dziesma saglabāta un pievienota "
                                        "tautas bumbas kopējai playlistei! 🎵"
                                    )
                                else:
                                    st.success(
                                        "Dziesma saglabāta, tā jau ir playlistē. 🎵"
                                    )

                            except Exception:
                                logger.exception(
                                    "Song saved, but Spotify sync failed"
                                )
                                st.warning(
                                    "Tava dziesma ir saglabāta, bet "
                                    "Spotify sinhronizācija nenotika. "
                                    "Mēgināsim vēlreiz, "
                                    "kad aplikācija atkal strādās."
                                )

                            st.rerun()

                        else:
                            st.error(message)

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
        "Tavas dziesmas ir saglabātas. "
        "Tās dzirdēsi jau drīz mūsu dzimšanas dienas pasākumā."
    )

    st.link_button(
        "Atvērt playlisti Spotify",
        "https://open.spotify.com/playlist/"
        "0JlLQXk7qN7YPagU01Q1t3",
    )

    # st.info("Enter your name to get started.")


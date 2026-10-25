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
    page_title="Our Group Soundtrack",
    page_icon="🎵",
)

SESSION_ID = "group-2026"

QUESTIONS = [
    "Kura dziesma Tevi visvairāk motivē bumbā pamatīgi uzbliezt?",
    "Kura dziesma Tev visvairāk asociējas ar Tautas bumbu treniņiem?",
    "Kura dziesma vislabāk raksturo Tevi ballītēs?",
]



# Temporary, password-protected Spotify authorization setup.
params = st.query_params

setup_mode = (
    params.get("spotify_setup") == "1"
    or "code" in params
    or "error" in params
)

if setup_mode:
    st.title("Spotify authorization setup")

    password = st.text_input(
        "Enter the Spotify setup password",
        type="password",
        key="spotify_setup_password",
    )

    configured_password = st.secrets["SPOTIFY_SETUP_PASSWORD"]

    if not hmac.compare_digest(
        password,
        configured_password,
    ):
        st.info("Enter your setup password to continue.")
        st.stop()

    redirect_uri = st.secrets["SPOTIFY_REDIRECT_URI"]

    auth = SpotifyOAuth(
        client_id=st.secrets["SPOTIFY_CLIENT_ID"],
        client_secret=st.secrets["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=redirect_uri,
        scope=(
            "playlist-modify-private "
            "playlist-modify-public "
            "playlist-read-private"
        ),
        cache_handler=MemoryCacheHandler(),
        open_browser=False,
    )

    if "error" in params:
        st.error(
            "Spotify authorization failed: "
            + str(params.get("error"))
        )
        st.stop()

    if "code" in params:
        returned_state = params.get("state", "")

        try:
            timestamp, nonce, signature = str(
                returned_state
            ).split(".", 2)

            message = f"{timestamp}.{nonce}"

            expected_signature = hmac.new(
                configured_password.encode("utf-8"),
                message.encode("utf-8"),
                digestmod="sha256",
            ).hexdigest()

            state_is_valid = (
                hmac.compare_digest(
                    signature,
                    expected_signature,
                )
                and 0 <= time.time() - int(timestamp) <= 600
            )

        except (ValueError, TypeError):
            state_is_valid = False

        if not state_is_valid:
            st.error(
                "The authorization link expired or is invalid. "
                "Please start again."
            )
            st.stop()

        try:
            token_info = auth.get_access_token(
                str(params.get("code")),
                as_dict=True,
                check_cache=False,
            )

            if (
                not token_info
                or not token_info.get("access_token")
                or not token_info.get("refresh_token")
            ):
                st.error(
                    "Spotify did not return all required tokens. "
                    "Please restart authorization."
                )
                st.stop()

            st.session_state["spotify_token_info"] = token_info

            st.query_params.clear()
            st.query_params["spotify_setup"] = "1"
            st.rerun()
        except Exception:
            logger.exception(
                "Spotify authorization exchange failed"
            )
            st.error(
                "Spotify authorization failed. "
                "Check the Streamlit app logs."
            )
            st.stop()

    token_info = st.session_state.get("spotify_token_info")

    if token_info:
        st.success("Spotify authorization completed!")
        st.write(
            "Copy the JSON below into Streamlit Secrets. "
            "Keep it private."
        )
        st.code(json.dumps(token_info), language="json")
        st.stop()

    if st.button("Start Spotify authorization"):
        timestamp = str(int(time.time()))
        nonce = py_secrets.token_urlsafe(24)
        message = f"{timestamp}.{nonce}"

        signature = hmac.new(
            configured_password.encode("utf-8"),
            message.encode("utf-8"),
            digestmod="sha256",
        ).hexdigest()

        state = f"{message}.{signature}"

        authorize_url = auth.get_authorize_url(
            state=state
        )

        st.link_button(
            "Continue to Spotify to approve access",
            authorize_url,
        )

    st.stop()


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


st.title("🎵 Our Group Soundtrack")
st.write("Three questions. Three songs. One shared playlist.")

name = st.text_input("What's your name?")

if not name.strip():
    st.info("Enter your name to get started.")
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

        with st.spinner("Searching Spotify..."):
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

    st.info("Enter your name to get started.")


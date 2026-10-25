
import json
import logging

import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler


logger = logging.getLogger(__name__)

PLAYLIST_ID = "0JlLQXk7qN7YPagU01Q1t3"

SCOPES = (
    "playlist-modify-private "
    "playlist-modify-public "
    "playlist-read-private"
)


@st.cache_resource
def get_spotify_client():
    token_info = json.loads(
        st.secrets["SPOTIFY_TOKEN_INFO"]
    )

    cache_handler = MemoryCacheHandler(
        token_info=token_info
    )

    auth = SpotifyOAuth(
        client_id=st.secrets["SPOTIFY_CLIENT_ID"],
        client_secret=st.secrets["SPOTIFY_CLIENT_SECRET"],
        redirect_uri="http://127.0.0.1:8888/callback",
        scope=SCOPES,
        cache_handler=cache_handler,
        open_browser=False,
    )

    token = auth.validate_token(
        cache_handler.get_cached_token()
    )

    if not token:
        raise RuntimeError(
            "Spotify token is missing or invalid. "
            "Spotify authorization needs to be completed."
        )

    return spotipy.Spotify(
        auth_manager=auth,
        requests_timeout=10,
        retries=0,
    )


def search_tracks(query):
    if not query or not query.strip():
        return []

    logger.info("Starting Spotify search")

    sp = get_spotify_client()

    results = sp.search(
        q=query.strip(),
        type="track",
        limit=10,
    )

    tracks = []

    for item in results["tracks"]["items"]:
        album_images = item["album"].get("images", [])

        tracks.append({
            "id": item["id"],
            "uri": item["uri"],
            "name": item["name"],
            "artist": ", ".join(
                artist["name"]
                for artist in item["artists"]
            ),
            "album": item["album"]["name"],
            "image": (
                album_images[0]["url"]
                if album_images
                else None
            ),
        })

    logger.info(
        "Spotify search completed: %d results",
        len(tracks),
    )

    return tracks


def add_track_to_playlist(track_uri):
    """Add a track unless it is already in the playlist."""

    sp = get_spotify_client()

    results = sp.playlist_items(
        PLAYLIST_ID,
        limit=100,
        fields="items(track(uri)),next",
    )

    while True:
        for item in results["items"]:
            track = item.get("track")

            if track and track.get("uri") == track_uri:
                return "already_exists"

        if not results.get("next"):
            break

        results = sp.next(results)

    sp.playlist_add_items(
        PLAYLIST_ID,
        [track_uri],
    )

    return "added"


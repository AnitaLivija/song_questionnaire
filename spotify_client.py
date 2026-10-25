
import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth


PLAYLIST_ID = "0JlLQXk7qN7YPagU01Q1t3"

SCOPES = (
    "playlist-modify-private "
    "playlist-modify-public "
    "playlist-read-private"
)


@st.cache_resource
def get_spotify_client():
    auth = SpotifyOAuth(
        client_id=st.secrets["SPOTIFY_CLIENT_ID"],
        client_secret=st.secrets["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=st.secrets["SPOTIFY_REDIRECT_URI"],
        scope=SCOPES,
        open_browser=False,
    )

    return spotipy.Spotify(auth_manager=auth)


def search_tracks(query):
    if not query.strip():
        return []

    sp = get_spotify_client()

    results = sp.search(
        q=query,
        type="track",
        limit=10,
    )

    tracks = []

    for item in results["tracks"]["items"]:
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
                item["album"]["images"][0]["url"]
                if item["album"]["images"]
                else None
            ),
        })

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

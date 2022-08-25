from dotenv import load_dotenv
from pathlib import Path
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pprint import pprint
import configparser
from functools import reduce



class SpotifyResults:
    def __init__(self, sp, fn, subnext=None):
        self._sp = sp
        self._fn = fn
        self._subnext = subnext

    def get(self, *args, **kwargs):
        try:
            results = self._fn(*args, **kwargs)
            yield results
            if self._subnext is None:
                while results['next']:
                    results = self._sp.next(results)
                    yield results
            else:
                while results.get(self._subnext, {}).get('next', None):
                    results = self._sp.next(results[self._subnext])
                    yield results
        
        except Exception as e:
            pprint(e)
            pprint(results)

    def _hasnext(self, r):
        return reduce(lambda d,k: d.get(k,{}), [r]+self._nextpath.split('.'))

def find_artist(artist_name):
    matches = []
    for results in SpotifyResults(sp, sp.search, 'artists.next').get(f'name:{artist_name}', type='artist'):
        artists = results['artists']
        for i, artist in enumerate(artists['items']):
            if artist['name'].casefold() == artist_name.casefold():
                matches.append(artist)
    return matches

def find_playlist(playlist_name):
    for playlists in SpotifyResults(sp, sp.current_user_playlists).get():
        for i, playlist in enumerate(playlists['items']):
            if playlist['name'].casefold() == playlist_name.casefold():
                return playlist
    return None

if __name__ == '__main__':
    load_dotenv(dotenv_path=Path('/Users/davidmay/.pyenv/newlistens.py.env'))
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope='playlist-read-private'))
    config = configparser.RawConfigParser(allow_no_value=True)
    config.read('toptracks.ini')

    playlist_name = config.sections()[0]
    playlist = find_playlist(playlist_name)
    if playlist is not None:
        raise ValueError(f'{playlist_name} already exists')
    
    for artist_name,v in config.items(playlist_name):
        artists = find_artist(artist_name)
        print(f'{artist_name}: {len(artists)}')

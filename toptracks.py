import argparse
import configparser
from dotenv import load_dotenv
from functools import reduce
from pathlib import Path
from pick import pick
from pprint import pprint
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import sys

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
# -- End SpotifyResults Class

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

def find_artist_toptracks(artist_url):
    return sp.artist_top_tracks(artist_url)

def get_playlist_artists(config, playlist_name, config_file):
    get_artist_name = lambda artist: artist.get('name', None) if artist else None
    get_artist_url = lambda artist: artist.get('external_urls', {}).get('spotify', 'No spotify url') if artist else None
    get_artist_followers = lambda artist: artist.get('followers', {}).get('total', 0) if artist else 0
    get_artist_choice = lambda artist: f'{get_artist_name(artist)}: {get_artist_url(artist)} ({get_artist_followers(artist):,})'

    found_all = True
    newly_found = False
    for artist_name,artist_url in config.items(playlist_name):
        if artist_url is not None and artist_url.startswith('https://open.spotify.com/artist/'):
            # print(f'{artist_name}: {artist_url}')
            continue

        artists = [a for a in find_artist(artist_name) if get_artist_followers(a) > 0]
        if len(artists) > 1:
            artists.append(None) # If none of the results are correct
            artist, _ = pick(artists, f"Pick '{artist_name}' url: ", indicator='*', options_map_func=get_artist_choice)
        elif len(artists) == 1:
            artist = artists[0]
        else:
            artist = None

        newly_found += 1 if artist else 0
        artist_url = get_artist_url(artist)
        config.set(playlist_name, artist_name, artist_url)
        # print(f'{artist_name}: {artist_url}')

        if artist_url is None:
            found_all = False
    
    if newly_found > 0:
        print(f'  saving found artists to {config_file} ...')
        with open(config_file, 'w') as fp_config:
            config.write(fp_config)
    
    return found_all == True

if __name__ == '__main__':
    load_dotenv(dotenv_path=Path('/Users/davidmay/.pyenv/newlistens.py.env'))
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope='playlist-read-private,playlist-modify-public'))
    current_user = sp.me()

    parser = argparse.ArgumentParser(description='Create playlist of top tracks from a list of artists.')
    parser.add_argument('config_file', nargs=1, #type=argparse.FileType('rw'),
                        help='INI file with sections having lists of artists')
    parser.add_argument('--skip-missing-artists', '--sma', dest='skip_missing_artists', action='store_true',
                         help="Skip artists without resolved Spotify url.")
    parser.add_argument('--max-toptracks', "-n", dest="max_toptracks", default=5, type=int, 
                        help="Max top tracks to include per artist")
    args = parser.parse_args()

    config = configparser.RawConfigParser(allow_no_value=True)    
    config.read(args.config_file)

    playlist_sections = config.sections()
    print(len(playlist_sections))
    playlist_name = pick(playlist_sections, "Choose Playlist: ")[0] if len(playlist_sections) > 1 else playlist_sections[0]

    print(f'Using: {playlist_name}')
    
    print(f'Step: Ensure playlist does not exist yet ...')
    playlist = find_playlist(playlist_name)
    if playlist:
        print(f"\nError: Playlist '{playlist_name}' already exists.\nAborting.")
        sys.exit(1)
    
    print(f'Step: Find playlist artists on Spotify ...')
    if not get_playlist_artists(config, playlist_name, args.config_file):
        if not args.skip_missing_artists:
            print("\nError: Unable to find some artists. Please look them up manually:")
            print("\n".join([f'  • {k}' for k,v in config.items(playlist_name) if not v]))
            print("Aborting ...")
            sys.exit(1)

    print(f'Step: Find top tracks for artists ...')
    #toptracks = get_playlist_artist_toptracks(config, playlist_name)
    playlist_tracks = []
    for artist_name, artist_url in config.items(playlist_name):
        if not artist_url:
            continue # Skip it if we got here

        print(f"  getting top tracks for {artist_name} ...")
        results = sp.artist_top_tracks(artist_url)
        if not (results and len(results['tracks'])):
            continue

        artist_toptracks = results['tracks']
        if artist_toptracks:
            playlist_tracks.extend([track['uri'] for track in artist_toptracks[:args.max_toptracks]])

    if len(playlist_tracks) == 0:
        print(f'\nError: No artist top tracks found.\nAborting ...')
        sys.exit(1)

    print(f'Step: Create public playlist ...')
    new_playlist = sp.user_playlist_create(current_user['id'], playlist_name, description=f'Top {args.max_toptracks} tracks for each artist {playlist_name}')
    playlist_url = new_playlist.get('external_urls', {}).get('spotify', None) if new_playlist else None
    if playlist_url:
        print(f'  created playlist: {playlist_url}')
    else:
        print(f'\nError: Failed to create playlist for {playlist_name}.\nAborting ...')
        sys.exit(1)

    print(f'Step: Add artists top tracks ...')
    chunked_tracks = [playlist_tracks[i:i+100] for i in range(0, len(playlist_tracks), 100)]
    for tracks_to_add in chunked_tracks:
        sp.playlist_add_items(new_playlist['id'], tracks_to_add) # raises on failure

    sys.exit(0)
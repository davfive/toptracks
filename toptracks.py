import argparse
import configparser
from difflib import SequenceMatcher
from dotenv import load_dotenv
from functools import reduce
from pathlib import Path
from pick import pick
from pprint import pprint
import random
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import sys

SPOTIFY_ACCESS_SCOPES = [
    'playlist-read-private',
    'playlist-modify-public'
]

SPOTIFY_MARKETS = [
    "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
    "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BS","BT",
    "BV","BW","BY","BZ","CA","CC","CD","CF","CG","CH","CI","CM","CN","CO","CR","CU",
    "CV","CX","CY","CZ","DE","DJ","DK","DM","DO","DZ","EC","EE","EG","EH","ER","ES",
    "ET","FI","FJ","FK","FO","FR","GA","GB","GD","GE","GF","GG","GH","GI","GL","GM",
    "GN","GP","GQ","GR","GS","GT","GU","GW","GY","HK","HM","HN","HR","HT","HU","ID",
    "IE","IL","IM","IN","IO","IQ","IR","IS","IT","JE","JM","JO","JP","KE","KG","KH",
    "KI","KM","KN","KP","KR","KW","KY","KZ","LA","LB","LC","LI","LK","LR","LS","LT",
    "LU","LV","LY","MA","MC","MD","ME","MF","MG","MH","MK","ML","MM","MN","MO","MP",
    "MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ","NA","NC","NE","NF","NG","NI",
    "NL","NO","NP","NR","NU","NZ","OM","PA","PE","PF","PG","PH","PK","PL","PM","PN",
    "PR","PS","PT","PW","PY","QA","RE","RO","RS","RU","RW","SA","SB","SC","SD","SE",
    "SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS","ST","SV","SX","SY","SZ",
    "TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ",
    "UA","UG","UM","US","UY","UZ","VA","VC","VE","VG","VI","VN","VU","WF","WS","YE",
    "YT","ZA","ZM","ZW"
]

class PlaylistConfig(configparser.RawConfigParser):
    _section_info = 'playlist.info'
    _section_artists = 'playlist.artists'

    def __init__(self, config_file):
        self._file = config_file
        super().__init__(allow_no_value=True)
        self.read(self._file)
        if not self._isvalid:
            raise ValueError(f'Playlist config file ({self._file}) is invalid. Aborting.')
        self._isdirty = False

    @property
    def artists(self):
        return self.items(self._section_artists)
    
    def artist(self, name, spotify_url=None):
        if not spotify_url:
            return self.get(self._section_artists, name, fallback=None)
        else:
            self._isdirty = True
            return super().set(self._section_artists, name, spotify_url)

    @property
    def has_missing_artists(self):
        return len(self.missing_artists) > 0

    @property
    def missing_artists(self):
        return [aname for aname,aurl in self.artists if aurl == None]

    @property
    def name(self):
        return self.get(self._section_info, 'name', fallback=None)

    @property
    def desc(self):
        return self.get(self._section_info, 'desc', fallback=None)

    @property
    def spotify_url(self):
        return self.get(self._section_info, 'spotify_url', fallback=None)
    
    @spotify_url.setter
    def spotify_url(self, url):
        self._isdirty = True
        return self.set(self._section_info, 'spotify_url', url)
    
    def save(self):
        if self._isdirty:
            print(self._file)
            with open(self._file, 'w') as fp:
                self.write(fp)
            self._isdirty = False

    def _isvalid(self):
        has_sections = lambda: all((s in self.sections() for s in [self._section_info, self._section_artists]))
        has_info = lambda: self.name and self.desc
        has_artists = lambda: len(self.items(self._section_artists))
        return has_sections() and has_info() and has_artists()

class SpotifyAPI(spotipy.Spotify):
    def __init__(self):
        load_dotenv(dotenv_path=Path(f'{Path.home()}/.toptracks.env'))
        super().__init__(auth_manager=SpotifyOAuth(scope=','.join(SPOTIFY_ACCESS_SCOPES)))

    @property
    def current_user(self):
        return self.me()

    def find_artist(self, artist_name):
        min_ratio_for_match = 0.4
        matches = []
        for results in SpotifyResultsGenerator(self, self.search, 'artists.next').get(f'name:{artist_name}', type='artist', market=SPOTIFY_MARKETS):
            artists = results['artists']
            for i, artist in enumerate(artists['items']):
                if SequenceMatcher(None, artist_name, artist['name']).ratio() > min_ratio_for_match:
                    # if artist['name'].casefold() == artist_name.casefold():
                    matches.append(SpotifyArtist(artist))
        return matches

    def find_playlist(self, playcfg):
        for playlists in SpotifyResultsGenerator(self, self.current_user_playlists).get():
            for i, playlist in enumerate(playlists['items']):
                if playlist['name'].casefold() == playcfg.name.casefold():
                    return playlist
        return None

    def get_artist_toptracks(self, artist_url, max_tracks=5, randomize=True):
        results = self.artist_top_tracks(artist_url)
        if not results or len(results['tracks']) == 0:
            return [] # Easier for caller to handle to have [] mean no artist toptracks

        toptracks = [track['uri'] for track in results.get('tracks', [])]
        max_tracks = max(0, min(len(toptracks), max_tracks))
        
        print(f'{artist_url}: {max_tracks} | {len(toptracks)}')
        return random.sample(toptracks, k=max_tracks) if max_tracks else []

class SpotifyArtist:
    def __init__(self, spotify_artist_json):
        self._json = spotify_artist_json

    @property
    def name(self):
        return self._json.get('name', None)

    @property
    def spotify_url(self):
        return self._json.get('external_urls', {}).get('spotify', None)

    @property
    def num_followers(self):
        return self._json.get('followers', {}).get('total', 0)

class SpotifyResultsGenerator:
    def __init__(self, spotify, method, subnext=None):
        self._spotify = spotify
        self._method = method
        self._subnext = subnext

    def get(self, *args, **kwargs):
        try:
            results = self._method(*args, **kwargs)
            yield results
            if self._subnext is None:
                while results['next']:
                    results = self._spotify.next(results)
                    yield results
            else:
                while results.get(self._subnext, {}).get('next', None):
                    results = self._spotify.next(results[self._subnext])
                    yield results
        
        except Exception as e:
            pprint(e)
            pprint(results)

    def _hasnext(self, r):
        return reduce(lambda d,k: d.get(k,{}), [r]+self._nextpath.split('.'))


# -- End Classes --

def find_playlist_artists(spotapi, playcfg):
    artist_already_found = lambda a_url: a_url is not None and a_url.startswith('https://open.spotify.com/artist/')
    get_artist_pickline = lambda a: f'{a.name}: {a.spotify_url} ({a.num_followers:,})' if a else 'Not listed'

    for artist_name, artist_url in playcfg.artists:
        if artist_already_found(artist_url):
            continue

        # Search Spotify WebAPI for artist by name
        matching_artists = [a for a in spotapi.find_artist(artist_name) if a.num_followers > 0]
        if len(matching_artists) > 1:
            matching_artists.append(None) # If none of the results are correct
            artist, _ = pick(matching_artists, f"Pick '{artist_name}' url: ", indicator='*', options_map_func=get_artist_pickline)
        elif len(matching_artists) == 1:
            artist = matching_artists[0]
        else:
            artist = None
        if artist:
            playcfg.artist(artist_name, artist.spotify_url)

    playcfg.save()
    return playcfg.has_missing_artists == False

def get_artists_toptracks(spotapi, playcfg, maxtracks_per_artist=5):
    toptracks = []
    for _, artist_url in playcfg.artists:
        if artist_url: # ignore missing artists
            artist_toptracks = spotapi.get_artist_toptracks(artist_url, max_tracks=maxtracks_per_artist)
            toptracks.extend(artist_toptracks)
    
    return toptracks

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create playlist of top tracks from a list of artists.')
    parser.add_argument('config_file', #type=argparse.FileType('rw'),
                        help='INI file with sections having lists of artists')
    parser.add_argument('--skip-missing-artists', '--sma', dest='skip_missing_artists', action='store_true',
                         help="Skip artists without resolved Spotify url.")
    parser.add_argument('--max-toptracks', "-n", dest="max_toptracks", default=3, type=int, 
                        help="Max top tracks to include per artist")
    args = parser.parse_args()

    spotapi = SpotifyAPI()
    playcfg = PlaylistConfig(args.config_file)

    print(f'Playlist: {playcfg.name}: {playcfg.desc}')
    print()
    
    print(f'Step 1: Ensure playlist does not exist yet ...')
    playlist = spotapi.find_playlist(playcfg)
    if playlist:
        print(f"Error: Playlist '{playcfg.name}' already exists.\nAborting.")
        sys.exit(1)
    
    print(f'Step 2: Find playlist artists on Spotify ...')
    find_playlist_artists(spotapi, playcfg)
    if not args.skip_missing_artists and playcfg.has_missing_artists:
        print("\nError: Unable to find some artists. Please look them up manually:")
        print("\n".join([f'  • {artist_name}' for artist_name in playcfg.missing_artists]))
        print("Aborting ...")
        sys.exit(1)

    print(f'Step 3: Find top tracks for artists ...')
    toptracks = get_artists_toptracks(spotapi, playcfg, maxtracks_per_artist=args.max_toptracks)
    if not toptracks:
        print('\nError: No toptracks found for any artist in playlist. Aborting.')
        sys.exit(1)

    print(f'Step 4: Create public playlist {playcfg.name} ...')
    new_playlist = spotapi.user_playlist_create(spotapi.current_user['id'], playcfg.name, description=playcfg.desc)
    playlist_url = new_playlist.get('external_urls', {}).get('spotify', None) if new_playlist else None
    if not playlist_url:
        print(f'\nError: Failed to create playlist for {playcfg.name}.\nAborting ...')
        sys.exit(1)

    print(f'Step 5: Add artists top tracks ...')
    chunked_tracks = [toptracks[i:i+100] for i in range(0, len(toptracks), 100)]
    for tracks_to_add in chunked_tracks:
        spotapi.playlist_add_items(new_playlist['id'], tracks_to_add) # raises on failure

    playcfg.spotify_url = playlist_url
    playcfg.save()

    print()
    print('Playlist created')
    print(f'  Name: {playcfg.name}')
    print(f'  Desc: {playcfg.desc}')
    print(f'  Url:  {playlist_url}')

    sys.exit(0)
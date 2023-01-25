# toptracks
Create Spotify Playlist with Top Tracks from a list of artists.

# how to use
1. Follow instructions in [toptracks.env](toptracks.env)
2. Create playlist ini file (follow example of existing ones)
3. Run `python3 toptracks.ini path/to/playlist.ini`
4. Resolve all artists Spotify urls.  
   The script will try to do it automatically, otherwise find them yourself and then cut/paste url into ini file.
5. Once all artists are resolved, the final run of the script will create the playlist with the artists top tracks

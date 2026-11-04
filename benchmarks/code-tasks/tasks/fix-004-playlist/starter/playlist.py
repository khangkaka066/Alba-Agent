"""A tiny playlist model for the audio player."""


class Playlist:
    """An ordered list of tracks. Every Playlist instance owns its own tracks."""

    tracks = []

    def __init__(self, name):
        self.name = name

    @classmethod
    def from_pairs(cls, name, pairs):
        """Build a playlist from (title, seconds) pairs."""
        playlist = cls(name)
        for title, seconds in pairs:
            playlist.add(title, seconds)
        return playlist

    def add(self, title, seconds):
        """Append a track."""
        self.tracks.append((title, seconds))

    def remove(self, title):
        """Remove the first track with this title. Returns True if one was removed."""
        for index, (existing, _) in enumerate(self.tracks):
            if existing == title:
                del self.tracks[index]
                return True
        return False

    def total_seconds(self):
        """Sum of all track lengths in seconds."""
        return sum(seconds for _, seconds in self.tracks)

    def duration_label(self):
        """Total length as 'M:SS', e.g. 3725 seconds -> '62:05'."""
        total = self.total_seconds()
        return f"{total // 60}:{total % 60:02d}"

    def __len__(self):
        return len(self.tracks)

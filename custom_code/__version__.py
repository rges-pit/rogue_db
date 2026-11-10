import os
import subprocess
from functools import lru_cache

VERSION = (0, 1, 0, 'dev', 0)  # Major, minor, micro, release, serial

# Set when the Docker image is built (the image has no .git directory to ask): see the Dockerfile
COMMIT_ENV_VAR = 'ROGUEDB_GIT_COMMIT'
HASH_LENGTH = 12


@lru_cache(maxsize=None)
def get_git_hash():
    """
    The commit of the code that is running, or None if it can't be found: the abbreviated hash, followed
    by -dirty if the files in the repository have been changed since (new files, which git doesn't
    track yet, aren't counted).

    The version number alone doesn't say which code made a result, as it stays the same through
    any number of changes. The hash does, and the modeling records it with each process.

    It is the one the image was built from, if the environment says so (a Docker image has no
    repository to ask); otherwise git is asked about the repository that this file is in.
    """
    built_from = os.getenv(COMMIT_ENV_VAR, '').strip()
    if built_from and built_from != 'unknown':
        # Abbreviated whatever the length given, to fit where it is stored
        commit, dirty, _ = built_from.partition('-dirty')
        return commit[:HASH_LENGTH] + dirty

    try:
        # Ignoring tags (--exclude): the hash is wanted, never the name of a nearby tag
        return subprocess.run(
            ['git', 'describe', '--always', '--dirty', f'--abbrev={HASH_LENGTH}', "--exclude=*"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def get_version():
    """The version number, and the commit it was made from: 0.1.0+1a2b3c4d5e6f (+unknown if it isn't known)"""
    return '.'.join(map(str, VERSION[:3])) + '+' + (get_git_hash() or 'unknown')

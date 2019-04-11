import logging
import os.path
import os
import glob
import random

logger = logging.getLogger(__name__)

try:
    import winsound
except ImportError:
    pass

BASE_PATH = os.path.abspath("public/audio")
logger.info(BASE_PATH)

def get_sound(name):

    glob_path = os.path.join(BASE_PATH, name)
    logger.info(f'globbing {glob_path}')
    for file_path in glob.glob(rf'{glob_path}.*'):
        logger.info(file_path)
        if file_path.startswith(os.path.abspath(BASE_PATH) + os.sep):
            # winsound.PlaySound(file_path, winsound.SND_FILENAME)
            return '/static/audio/' + os.path.relpath(file_path, BASE_PATH)
        else:
            logger.info(f"Sound '{file_path}' not in av dir!")
    else:
        logger.info(f"Sound {name} not found!")

def get_random_sound(prefix=""):
    glob_path = os.path.join(BASE_PATH, prefix)
    paths = glob.glob(f'{glob_path}*.*')
    if paths:
        file_path = random.choice(paths)
        if file_path.startswith(os.path.abspath(BASE_PATH) + os.sep):
            #winsound.PlaySound(file_path, winsound.SND_FILENAME)
            return '/static/audio/' + os.path.relpath(file_path, BASE_PATH)
        else:
            logger.info(f"Sound '{file_path}' not in av dir!")
    else:
        logger.info(f"No sounds with prefix '{prefix}' found!")


# TODO: check for win/*nix
def play(file_path):
    winsound.PlaySound(file_path, winsound.SND_FILENAME)


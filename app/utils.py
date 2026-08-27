import os
import shutil
import logging
from datetime import datetime
from app.config import Config


logger = logging.getLogger(__name__)


def copy_to_network():
    src = Config.OUTPUT_JSON
    dst = Config.NETWORK_PATH
    try:
        if os.path.exists(src):
            shutil.copy2(src, dst)
            logger.info(f"файл скопирован в {dst}")
        else:
            logger.error(f"Исходный файл {src} не найден")
    except Exception as e:
        logger.error(f"Failed to copy {e}")
        raise

def archive_file(source_path, archive_dir = None):
    if not archive_dir:
        archive_dir = Config.ARCHIVE_DIR
    if not os.path.exists(sourse_path):
        logger.warning(f"File {source_path} cant be archived because source doesnt exist it")
        return None

    
    os.makedirs(archive_dir, exist_ok = True)
    base_name = os.path.basename(source_path)
    name, ext = os.path.splitext(basename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{name}_{timestamp}{ext}"
    dest = os.path.join(archive_dir, archive_name)
    shutil.copy2(source_path, dest)
    logger.info(f"Архивирован: {dest}")
    return dest
    



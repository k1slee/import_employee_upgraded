#!/usr/bin/env python3
"""
Вспомогательные функции для работы с сетью и файлами.
"""
import shutil
import os

def copy_to_network(source, network_path):
    """Копирует файл в сетевое хранилище."""
    os.makedirs(os.path.dirname(network_path), exist_ok=True)
    shutil.copy2(source, network_path)
    return network_path

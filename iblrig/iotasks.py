#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @Author: Niccolò Bonacchi
# @Date: Tuesday, February 5th 2019, 3:13:18 pm
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path

import ibllib.io.raw_data_loaders as raw
import iblrig.path_helper as ph
import numpy as np

import iblrig.misc as misc

log = logging.getLogger('iblrig')


class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'reprJSON'):
            return obj.reprJSON()
        else:
            return json.JSONEncoder.default(self, obj)


def deserialize_pybpod_user_settings(sph: object) -> object:
    sph.PYBPOD_CREATOR = json.loads(sph.PYBPOD_CREATOR)
    sph.PYBPOD_USER_EXTRA = json.loads(sph.PYBPOD_USER_EXTRA)

    sph.PYBPOD_SUBJECTS = [
        json.loads(x.replace("'", '"')) for x in sph.PYBPOD_SUBJECTS]
    if len(sph.PYBPOD_SUBJECTS) == 1:
        sph.PYBPOD_SUBJECTS = sph.PYBPOD_SUBJECTS[0]
    else:
        log.error("Multiple subjects found in PYBPOD_SUBJECTS")
        raise(IOError)

    sph.PYBPOD_SUBJECT_EXTRA = [
        json.loads(x) for x in sph.PYBPOD_SUBJECT_EXTRA[1:-1].split('","')]
    if len(sph.PYBPOD_SUBJECT_EXTRA) == 1:
        sph.PYBPOD_SUBJECT_EXTRA = sph.PYBPOD_SUBJECT_EXTRA[0]

    return sph


def save_session_settings(sph: object) -> None:
    save_this = json.dumps(sph, cls=ComplexEncoder, indent=1)
    with open(sph.SETTINGS_FILE_PATH, 'a') as f:
        f.write(save_this)
        f.write('\n')

    save_this = json.loads(save_this)
    settings = raw.load_settings(sph.SESSION_FOLDER)
    assert(save_this == settings)


def copy_task_code(sph: object) -> None:
    # Copy behavioral task python code
    src = os.path.join(
        sph.IBLRIG_PARAMS_FOLDER, 'IBL', 'tasks', sph.PYBPOD_PROTOCOL)
    dst = os.path.join(
        sph.SESSION_RAW_DATA_FOLDER, sph.PYBPOD_PROTOCOL)
    shutil.copytree(src, dst)
    # Copy stimulus folder with bonsai workflow
    src = str(Path(
        sph.VISUAL_STIM_FOLDER) / sph.VISUAL_STIMULUS_TYPE)
    dst = str(Path(
        sph.SESSION_RAW_DATA_FOLDER) / sph.VISUAL_STIMULUS_TYPE)
    shutil.copytree(src, dst)


def copy_video_code(sph: object) -> None:
    # Copy video recording folder with bonsai workflow
    src = sph.VIDEO_RECORDING_FOLDER
    dst = os.path.join(
        sph.SESSION_RAW_VIDEO_DATA_FOLDER, 'camera_recordings')
    shutil.copytree(src, dst)


def save_task_code(sph: object) -> None:
    # zip all existing folders
    # Should be the task code folder and if available stimulus code folder
    behavior_code_files = [
        os.path.join(sph.SESSION_RAW_DATA_FOLDER, x)
        for x in os.listdir(sph.SESSION_RAW_DATA_FOLDER)
        if os.path.isdir(os.path.join(sph.SESSION_RAW_DATA_FOLDER, x))
    ]
    zipit(behavior_code_files, Path(sph.SESSION_RAW_DATA_FOLDER).joinpath(
        '_iblrig_taskCodeFiles.raw.zip')
    )

    [shutil.rmtree(x) for x in behavior_code_files]


def save_video_code(sph: object) -> None:
    # zip all existing folders
    # Should be the task code folder and if available stimulus code folder
    video_code_files = [
        os.path.join(sph.SESSION_RAW_VIDEO_DATA_FOLDER, x)
        for x in os.listdir(sph.SESSION_RAW_VIDEO_DATA_FOLDER)
        if os.path.isdir(
            os.path.join(sph.SESSION_RAW_VIDEO_DATA_FOLDER, x))
    ]
    zipit(
        video_code_files, Path(sph.SESSION_RAW_VIDEO_DATA_FOLDER).joinpath(
            '_iblrig_videoCodeFiles.raw.zip')
    )

    [shutil.rmtree(x) for x in video_code_files]


def zipdir(path: str, ziph: zipfile.ZipFile) -> None:
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(
                os.path.join(root, file), os.path.relpath(
                    os.path.join(root, file), os.path.join(path, '..')))


def zipit(dir_list: list, zip_name: str) -> None:
    zipf = zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED)
    for dir in dir_list:
        zipdir(dir, zipf)
    zipf.close()


def load_data(session_folder: str, i: int = -1) -> dict:
    trial_data = raw.load_data(session_folder)
    return trial_data[i] if trial_data else None


def load_settings(session_folder: str) -> dict:
    return raw.load_settings(session_folder)


# FIXME: if MOCK session is ran in the middle of a run the next session will fail!
def load_session_order_idx(last_settings_data: dict) -> tuple:
    if ((not last_settings_data) or
            ('SESSION_ORDER' not in last_settings_data.keys()) or
            (last_settings_data['SESSION_ORDER'] is None)):
        session_order = misc.draw_session_order()
        session_idx = 0
    elif 'SESSION_ORDER' in last_settings_data.keys():
        session_order = last_settings_data['SESSION_ORDER']
        session_idx = last_settings_data['SESSION_IDX'] + 1

    return session_order, session_idx


def load_ephys_session_pcqs(preloaded_session_num: str) -> tuple:
    base = ph.get_pregen_session_folder()
    pcqs = np.load(Path(base) / f'session_{preloaded_session_num}_ephys_pcqs.npy')
    len_block = np.load(Path(base) / f'session_{preloaded_session_num}_ephys_len_blocks.npy')

    pos = pcqs[:, 0].tolist()
    cont = pcqs[:, 1].tolist()
    quies = pcqs[:, 2].tolist()
    phase = pcqs[:, 3].tolist()
    len_blocks = len_block.tolist()

    return pos, cont, quies, phase, len_blocks


def load_passive_session_delays_ids(preloaded_session_num: str) -> tuple:
    base = ph.get_pregen_session_folder()
    stimDelays = np.load(Path(base) / f'session_{preloaded_session_num}_passive_stimDelays.npy')
    stimIDs = np.load(Path(base) / f'session_{preloaded_session_num}_passive_stimIDs.npy')
    return stimDelays, stimIDs


def load_passive_session_pcs(preloaded_session_num: str) -> tuple:
    base = ph.get_pregen_session_folder()
    pcs = np.load(Path(base) / f'session_{preloaded_session_num}_passive_pcs.npy')
    pos = pcs[:, 0].tolist()
    cont = pcs[:, 1].tolist()
    phase = pcs[:, 2].tolist()
    return pos, cont, phase

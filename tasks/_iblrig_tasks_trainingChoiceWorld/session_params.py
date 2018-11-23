# -*- coding: utf-8 -*-
# @Author: Niccolò Bonacchi
# @Date:   2018-02-02 17:19:09
# @Last Modified by:   Niccolò Bonacchi
# @Last Modified time: 2018-07-12 16:18:59
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from sys import platform

import numpy as np
import scipy.stats as st
from dateutil import parser
from pybpod_rotaryencoder_module.module_api import RotaryEncoderModule
from pythonosc import udp_client

import sound
from path_helper import SessionPathCreator


class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'reprJSON'):
            return obj.reprJSON()
        else:
            return json.JSONEncoder.default(self, obj)


class MyRotaryEncoder(object):

    def __init__(self, all_thresholds, gain):
        self.all_thresholds = all_thresholds
        self.wheel_perim = 31 * 2 * np.pi  # = 194,778744523
        self.deg_mm = 360 / self.wheel_perim
        self.mm_deg = self.wheel_perim / 360
        self.factor = 1 / (self.mm_deg * gain)
        self.SET_THRESHOLDS = [x * self.factor for x in self.all_thresholds]
        self.ENABLE_THRESHOLDS = [(True if x != 0
                                   else False) for x in self.SET_THRESHOLDS]
        # ENABLE_THRESHOLDS needs 8 bools even if only 2 thresholds are set
        while len(self.ENABLE_THRESHOLDS) < 8:
            self.ENABLE_THRESHOLDS.append(False)

    def reprJSON(self):
        d = self.__dict__
        return d


class session_param_handler(object):
    """Session object imports user_settings and task_settings
    will and calculates other secondary session parameters,
    runs Bonsai and saves all params in a settings file.json"""

    def __init__(self, task_settings, user_settings):
        # =====================================================================
        # IMPORT task_settings, user_settings, and SessionPathCreator params
        # =====================================================================
        ts = {i: task_settings.__dict__[i]
              for i in [x for x in dir(task_settings) if '__' not in x]}
        self.__dict__.update(ts)
        us = {i: user_settings.__dict__[i]
              for i in [x for x in dir(user_settings) if '__' not in x]}
        self.__dict__.update(us)
        self.deserialize_session_user_settings()
        spc = SessionPathCreator(self.IBLRIG_FOLDER, self.MAIN_DATA_FOLDER,
                                 self.PYBPOD_SUBJECTS[0], self.PYBPOD_PROTOCOL)
        self.__dict__.update(spc.__dict__)
        # =====================================================================
        # OSC CLIENT
        # =====================================================================
        self.OSC_CLIENT = self._init_osc_client()
        # =====================================================================
        # FOLDER STRUCTURE AND DATA FILES
        # =====================================================================
        self.LAST_TRIAL_DATA = self._load_last_trial()
        self.REWARD_AMOUNT = self._init_reward()
        # =====================================================================
        # ADAPTIVE STUFF
        # =====================================================================
        self.STIM_GAIN = self._init_stim_gain()
        # =====================================================================
        # ROTARY ENCODER
        # =====================================================================
        self.ALL_THRESHOLDS = (self.STIM_POSITIONS +
                               self.QUIESCENCE_THRESHOLDS)
        self.ROTARY_ENCODER = MyRotaryEncoder(self.ALL_THRESHOLDS,
                                              self.STIM_GAIN)
        # Names of the RE events generated by Bpod
        self.ENCODER_EVENTS = ['RotaryEncoder1_{}'.format(x) for x in
                               list(range(1, len(self.ALL_THRESHOLDS) + 1))]
        # Dict mapping threshold crossings with name ov RE event
        self.THRESHOLD_EVENTS = dict(zip(self.ALL_THRESHOLDS,
                                         self.ENCODER_EVENTS))
        if platform == 'linux':
            self.ROTARY_ENCODER_PORT = '/dev/ttyACM0'
        # self._configure_rotary_encoder(RotaryEncoderModule)
        # =====================================================================
        # SOUNDS
        # =====================================================================
        self.SOUND_SAMPLE_FREQ = 44100 if self.SOFT_SOUND else 96000
        self.WHITE_NOISE_DURATION = float(self.WHITE_NOISE_DURATION)
        self.WHITE_NOISE_AMPLITUDE = float(self.WHITE_NOISE_AMPLITUDE)
        self.GO_TONE_DURATION = float(self.GO_TONE_DURATION)
        self.GO_TONE_FREQUENCY = int(self.GO_TONE_FREQUENCY)
        self.GO_TONE_AMPLITUDE = float(self.GO_TONE_AMPLITUDE)

        self.SD = sound.configure_sounddevice(output=self.SOFT_SOUND,
                                              samplerate=self.SOUND_SAMPLE_FREQ)

        self._init_sounds()  # Will create sounds and output actions.
        # =====================================================================
        # RUN BONSAI
        # =====================================================================
        self.USE_VISUAL_STIMULUS = False if platform == 'linux' else self.USE_VISUAL_STIMULUS
        self.BONSAI = spc.get_bonsai_path(use_iblrig_bonsai=True)
        self.run_bonsai()
        # =====================================================================
        # SAVE SETTINGS FILE AND TASK CODE
        # =====================================================================
        self._save_session_settings()
        self._save_task_code()

    # =========================================================================
    # METHODS
    # =========================================================================
    # SERIALIZER
    # =========================================================================
    def reprJSON(self):
        d = self.__dict__.copy()
        if self.SOFT_SOUND:
            d['GO_TONE'] = 'go_tone(freq={}, dur={}, amp={})'.format(
                self.GO_TONE_FREQUENCY, self.GO_TONE_DURATION,
                self.GO_TONE_AMPLITUDE)
            d['WHITE_NOISE'] = 'white_noise(freq=-1, dur={}, amp={})'.format(
                self.WHITE_NOISE_DURATION, self.WHITE_NOISE_AMPLITUDE)
        d['SD'] = str(d['SD'])
        d['OSC_CLIENT'] = str(d['OSC_CLIENT'])
        d['SESSION_DATETIME'] = str(self.SESSION_DATETIME)
        return d

    # =========================================================================
    # SOUND
    # =========================================================================
    def _init_sounds(self):
        if self.SOFT_SOUND:
            self.UPLOADER_TOOL = None
            self.GO_TONE = sound.make_sound(
                rate=self.SOUND_SAMPLE_FREQ,
                frequency=self.GO_TONE_FREQUENCY,
                duration=self.GO_TONE_DURATION,
                amplitude=self.GO_TONE_AMPLITUDE,
                fade=0.01,
                chans='L+TTL')
            self.WHITE_NOISE = sound.make_sound(
                rate=self.SOUND_SAMPLE_FREQ,
                frequency=-1,
                duration=self.WHITE_NOISE_DURATION,
                amplitude=self.WHITE_NOISE_AMPLITUDE,
                fade=0.01,
                chans='L+TTL')

            self.OUT_TONE = ('SoftCode', 1)
            self.OUT_NOISE = ('SoftCode', 2)
        else:
            print("\n\nSOUND BOARD NOT IMPLEMTNED YET!!",
            "\nPLEASE USE SOFT_SOUND='onboard' | 'xonar' in task_settings.py\n\n")

    def play_tone(self):
        self.SD.play(self.GO_TONE, self.SOUND_SAMPLE_FREQ, mapping=[1, 2])

    def play_noise(self):
        self.SD.play(self.WHITE_NOISE, self.SOUND_SAMPLE_FREQ, mapping=[1, 2])

    def stop_sound(self):
        self.SD.stop()

    # =========================================================================
    # FILES AND FOLDER STRUCTURE
    # =========================================================================
    def run_bonsai(self):
        if self.USE_VISUAL_STIMULUS and self.BONSAI:
            # Copy stimulus folder with bonsai workflow
            src = self.VISUAL_STIM_FOLDER
            dst = os.path.join(self.SESSION_RAW_DATA_FOLDER, 'Gabor2D/')
            shutil.copytree(src, dst)
            # Run Bonsai workflow
            here = os.getcwd()
            os.chdir(os.path.join(self.IBLRIG_FOLDER, 'visual_stim',
                                  'Gabor2D'))
            bns = self.BONSAI
            wkfl = self.VISUAL_STIMULUS_FILE

            evt = "-p:FileNameEvents=" + os.path.join(
                self.SESSION_RAW_DATA_FOLDER,
                "_iblrig_encoderEvents.raw.ssv")
            pos = "-p:FileNamePositions=" + os.path.join(
                self.SESSION_RAW_DATA_FOLDER,
                "_iblrig_encoderPositions.raw.ssv")
            itr = "-p:FileNameTrialInfo=" + os.path.join(
                self.SESSION_RAW_DATA_FOLDER,
                "_iblrig_encoderTrialInfo.raw.ssv")
            mic = "-p:FileNameMic=" + os.path.join(
                self.SESSION_RAW_DATA_FOLDER,
                "_iblrig_micData.raw.wav")

            com = "-p:REPortName=" + self.ROTARY_ENCODER_PORT
            rec = "-p:RecordSound=" + str(self.RECORD_SOUND)

            start = '--start'
            noeditor = '--noeditor'

            if self.BONSAI_EDITOR:
                bonsai = subprocess.Popen(
                    [bns, wkfl, start, pos, evt, itr, com, mic, rec])
            elif not self.BONSAI_EDITOR:
                bonsai = subprocess.Popen(
                    [bns, wkfl, noeditor, pos, evt, itr, com, mic, rec])
            time.sleep(5)
            bonsai
            os.chdir(here)
        else:
            self.USE_VISUAL_STIMULUS = False

    def _load_last_trial(self, i=-1):
        if self.PREVIOUS_DATA_FILE is None:
            return
        trial_data = []
        with open(self.PREVIOUS_DATA_FILE, 'r') as f:
            for line in f:
                last_trial = json.loads(line)
                trial_data.append(last_trial)
        print("\n\nINFO: PREVIOUS SESSION FOUND",
              "\nLOADING PARAMETERS FROM: {}".format(self.PREVIOUS_DATA_FILE),
              "\n\nPREVIOUS NTRIALS:              {}".format(trial_data[i]["trial_num"]),
              "\nPREVIOUS NTRIALS (no repeats): {}".format(trial_data[i]["non_rc_ntrials"]),
              "\nLAST REWARD:                   {}".format(trial_data[i]["reward_amount"]),
              "\nLAST GAIN:                     {}".format(trial_data[i]["stim_gain"]),
              "\nLAST CONTRAST SET:             {}".format(trial_data[i]["ac"]["contrast_set"]),
              "\nBUFFERS LR:                    {}".format(trial_data[i]["ac"]["buffer"]))
        return trial_data[i] if trial_data else None

    # =========================================================================
    # ADAPTIVE REWARD AND GAIN RULES
    # =========================================================================
    def _init_reward(self):
        if not self.ADAPTIVE_REWARD:
            return self.REWARD_AMOUNT
        if self.LAST_TRIAL_DATA is None:
            return self.AR_INIT_VALUE
        else:
            try:
                out = (self.LAST_TRIAL_DATA['reward_valve_time'] /
                       self.LAST_TRIAL_DATA['reward_calibration'])
            except IOError:
                out = (self.LAST_TRIAL_DATA['reward_valve_time'] /
                       self.CALIBRATION_VALUE)
            return out

    def _init_stim_gain(self):
        if not self.ADAPTIVE_GAIN:
            return self.STIM_GAIN
        if self.LAST_TRIAL_DATA and self.LAST_TRIAL_DATA['trial_num'] >= 200:
            stim_gain = self.AG_MIN_VALUE
        else:
            stim_gain = self.AG_INIT_VALUE
        return stim_gain

    # =========================================================================
    # OSC CLIENT
    # =========================================================================
    def _init_osc_client(self):
        osc_client = udp_client.SimpleUDPClient(self.OSC_CLIENT_IP,
                                                self.OSC_CLIENT_PORT)
        return osc_client

    # =========================================================================
    # PYBPOD USER SETTINGS DESERIALIZATION
    # =========================================================================
    def deserialize_session_user_settings(self):
        self.PYBPOD_CREATOR = json.loads(self.PYBPOD_CREATOR)
        self.PYBPOD_USER_EXTRA = json.loads(self.PYBPOD_USER_EXTRA)

        self.PYBPOD_SUBJECTS = [json.loads(x.replace("'", '"'))
                                for x in self.PYBPOD_SUBJECTS]
        if len(self.PYBPOD_SUBJECTS) == 1:
            self.PYBPOD_SUBJECTS = self.PYBPOD_SUBJECTS[0]
        else:
            print("ERROR: Multiple subjects found in PYBPOD_SUBJECTS")
            raise IOError

        self.PYBPOD_SUBJECT_EXTRA = [json.loads(x) for x in
                                     self.PYBPOD_SUBJECT_EXTRA[1:-1
                                                               ].split('","')]
        if len(self.PYBPOD_SUBJECT_EXTRA) == 1:
            self.PYBPOD_SUBJECT_EXTRA = self.PYBPOD_SUBJECT_EXTRA[0]

    # =========================================================================
    # SERIALIZE AND SAVE
    # =========================================================================
    def _save_session_settings(self):
        with open(self.SETTINGS_FILE_PATH, 'a') as f:
            f.write(json.dumps(self, cls=ComplexEncoder))
            f.write('\n')
        return

    def _save_task_code(self):
        # Copy behavioral task python code
        src = os.path.join(self.IBLRIG_PARAMS_FOLDER, 'IBL', 'tasks',
                           self.PYBPOD_PROTOCOL)
        dst = os.path.join(self.SESSION_RAW_DATA_FOLDER, self.PYBPOD_PROTOCOL)
        shutil.copytree(src, dst)
        # zip all existing folders
        # Should be the task code folder and if available stimulus code folder
        folders_to_zip = [os.path.join(self.SESSION_RAW_DATA_FOLDER, x)
                          for x in os.listdir(self.SESSION_RAW_DATA_FOLDER)
                          if os.path.isdir(os.path.join(
                              self.SESSION_RAW_DATA_FOLDER, x))]
        session_param_handler.zipit(
            folders_to_zip, os.path.join(self.SESSION_RAW_DATA_FOLDER,
                                         '_iblrig_codeFiles.raw.zip'))

        [shutil.rmtree(x) for x in folders_to_zip]

    @staticmethod
    def zipdir(path, ziph):
        # ziph is zipfile handle
        for root, dirs, files in os.walk(path):
            for file in files:
                ziph.write(os.path.join(root, file),
                           os.path.relpath(os.path.join(root, file),
                                           os.path.join(path, '..')))

    @staticmethod
    def zipit(dir_list, zip_name):
        zipf = zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED)
        for dir in dir_list:
            session_param_handler.zipdir(dir, zipf)
        zipf.close()

    def _configure_rotary_encoder(self, RotaryEncoderModule):
        m = RotaryEncoderModule(self.ROTARY_ENCODER_PORT)
        m.set_zero_position()  # Not necessarily needed
        m.set_thresholds(self.ROTARY_ENCODER.SET_THRESHOLDS)
        m.enable_thresholds(self.ROTARY_ENCODER.ENABLE_THRESHOLDS)
        m.close()


if __name__ == '__main__':
    # os.chdir(r'C:\iblrig\pybpod_projects\IBL\tasks\basicChoiceWorld')
    import task_settings as _task_settings
    import _user_settings
    sph = session_param_handler(_task_settings, _user_settings)
    self = sph
    print("Done!")

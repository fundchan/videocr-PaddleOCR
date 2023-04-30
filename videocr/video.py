from __future__ import annotations
from typing import List
import cv2
import numpy as np

from . import utils
from .models import PredictedFrames, PredictedSubtitle
from .opencv_adapter import Capture
from paddleocr import PaddleOCR
from multiprocessing import Pool, cpu_count
from functools import partial
import itertools


class Video:
    path: str
    lang: str
    use_fullframe: bool
    det_model_dir: str
    rec_model_dir: str
    num_frames: int
    fps: float
    height: int
    ocr: PaddleOCR
    pred_frames: List[PredictedFrames]
    pred_subs: List[PredictedSubtitle]

    def __init__(self, path: str, det_model_dir: str, rec_model_dir: str):
        self.path = path
        self.det_model_dir = det_model_dir
        self.rec_model_dir = rec_model_dir
        with Capture(path) as v:
            self.num_frames = int(v.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = v.get(cv2.CAP_PROP_FPS)
            self.height = int(v.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def run_ocr(self, use_gpu: bool, lang: str, time_start: str, time_end: str,
                conf_threshold: int, use_fullframe: bool, brightness_threshold: int, similar_image_threshold: int, similar_pixel_threshold: int, frames_to_skip: int,
                crop_x: int, crop_y: int, crop_width: int, crop_height: int, num_processes) -> None:
        conf_threshold_percent = float(conf_threshold/100)
        self.lang = lang
        self.use_fullframe = use_fullframe
        self.pred_frames = []

        ocr_start = utils.get_frame_index(
            time_start, self.fps) if time_start else 0
        ocr_end = utils.get_frame_index(
            time_end, self.fps) if time_end else self.num_frames

        if ocr_end < ocr_start:
            raise ValueError('time_start is later than time_end')
        num_ocr_frames = ocr_end - ocr_start

        crop_x_end = None
        crop_y_end = None
        if crop_x and crop_y and crop_width and crop_height:
            crop_x_end = crop_x + crop_width
            crop_y_end = crop_y + crop_height

        # get frames from ocr_start to ocr_end
        filtered_frames = self.filted_frames(brightness_threshold, similar_image_threshold, similar_pixel_threshold,
                                             frames_to_skip, crop_x, crop_y, ocr_start, num_ocr_frames, crop_x_end,
                                             crop_y_end, conf_threshold_percent)

        processed_frame = self.process_frame(
            filtered_frames, use_gpu, num_processes)
        self.pred_frames = processed_frame

    def filted_frames(self, brightness_threshold, similar_image_threshold, similar_pixel_threshold,
                      frames_to_skip, crop_x, crop_y, ocr_start, num_ocr_frames, crop_x_end, crop_y_end,
                      conf_threshold_percent):

        with Capture(self.path) as v:
            v.set(cv2.CAP_PROP_POS_FRAMES, ocr_start)
            prev_grey = None
            modulo = frames_to_skip + 1
            #list[[start_index, frame, end_index]]
            filted_frame_info = []

            for i in range(num_ocr_frames):
                frame = v.read()[1]
                if (i % modulo) != 0:
                    continue

                if not self.use_fullframe:
                    if crop_x_end and crop_y_end:
                        frame = frame[crop_y:crop_y_end, crop_x:crop_x_end]
                    else:
                        # only use bottom third of the frame by default
                        frame = frame[self.height // 3:, :]

                if brightness_threshold:
                    frame = cv2.bitwise_and(frame, frame, mask=cv2.inRange(
                        frame, (brightness_threshold, brightness_threshold, brightness_threshold), (255, 255, 255)))

                if similar_image_threshold:
                    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if prev_grey is not None:
                        _, absdiff = cv2.threshold(cv2.absdiff(
                            prev_grey, grey), similar_pixel_threshold, 255, cv2.THRESH_BINARY)

                        if np.count_nonzero(absdiff) < similar_image_threshold:
                            # predicted_frames.end_index = i + ocr_start
                            filted_frame_info[-1][2] = i + ocr_start
                            prev_grey = grey
                            continue
                        elif len(filted_frame_info) > 200:
                            yield filted_frame_info
                            filted_frame_info = []
                    prev_grey = grey

                filted_frame_info.append(
                    [i+ocr_start, frame, i+ocr_start, conf_threshold_percent])

            # Return remaining data after the loop
            if filted_frame_info:
                yield filted_frame_info

    def ocr_frame(self, use_gpu, frame_info_list):
        ocr = PaddleOCR(lang=self.lang, rec_model_dir=self.rec_model_dir,
                        det_model_dir=self.det_model_dir, use_gpu=use_gpu)
        predicted_frames_list = []
        for frame_info in frame_info_list:
            predicted_frames = PredictedFrames(
                frame_info[0], ocr.ocr(frame_info[1]), frame_info[3])
            predicted_frames.end_index = frame_info[2]
            predicted_frames_list.append(predicted_frames)
        return predicted_frames_list

    def process_frame(self, filted_frames, use_gpu, num_processes):
        ocr_frame = partial(self.ocr_frame, use_gpu)
        with Pool(num_processes) as p:
            # predicted_frames_lists = p.map(
            #     ocr_frame, filted_frames)
            predicted_frames_lists = []
            for result in p.imap_unordered(ocr_frame, filted_frames):
                predicted_frames_lists.append(result)

        return list(itertools.chain.from_iterable(predicted_frames_lists))

    def get_subtitles(self, sim_threshold: int) -> str:
        self._generate_subtitles(sim_threshold)
        return ''.join(
            '{}\n{} --> {}\n{}\n\n'.format(
                i,
                utils.get_srt_timestamp(sub.index_start, self.fps),
                utils.get_srt_timestamp(sub.index_end, self.fps),
                sub.text)
            for i, sub in enumerate(self.pred_subs))

    def get_tsv_subtitles(self, sim_threshold: int) -> str:
        self._generate_subtitles(sim_threshold)
        first_line = 'start\tend\ttext\n'
        lines = [f'{utils.to_ms(sub.index_start, self.fps)}\t{utils.to_ms(sub.index_end, self.fps)}\t{sub.text}'
                 for i, sub in enumerate(self.pred_subs)]
        return first_line + '\n'.join(lines)

    def _generate_subtitles(self, sim_threshold: int) -> None:
        self.pred_subs = []

        if self.pred_frames is None:
            raise AttributeError(
                'Please call self.run_ocr() first to perform ocr on frames')

        max_frame_merge_diff = int(0.09 * self.fps)
        for frame in self.pred_frames:
            self._append_sub(PredictedSubtitle(
                [frame], sim_threshold), max_frame_merge_diff)
        self.pred_subs = [sub for sub in self.pred_subs if len(
            sub.frames[0].lines) > 0]

    def _append_sub(self, sub: PredictedSubtitle, max_frame_merge_diff: int) -> None:
        if len(sub.frames) == 0:
            return

        # merge new sub to the last subs if they are not empty, similar and within 0.09 seconds apart
        if self.pred_subs:
            last_sub = self.pred_subs[-1]
            if len(last_sub.frames[0].lines) > 0 and sub.index_start - last_sub.index_end <= max_frame_merge_diff and last_sub.is_similar_to(sub):
                del self.pred_subs[-1]
                sub = PredictedSubtitle(
                    last_sub.frames + sub.frames, sub.sim_threshold)

        self.pred_subs.append(sub)
